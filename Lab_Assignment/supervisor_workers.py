"""Day 8 RAG Agent improved with a Supervisor-Workers pattern.

Workers:
1. QueryPlannerWorker: classifies the question and creates search variants.
2. RetrievalWorker: retrieves evidence from the Day 8 RAG pipeline.
3. EvidenceWorker: filters and formats evidence for grounded generation.
4. AnswerWorker: generates a cited Vietnamese answer.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from dotenv import load_dotenv

DAY9_PROJECT_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = DAY9_PROJECT_DIR.parent
DAY8_PROJECT_DIR = WORKSPACE_DIR / "2A202600883-MaiHanhPham-Day08_RAG_pipeline_cohort2"
if str(DAY8_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(DAY8_PROJECT_DIR))

load_dotenv(DAY8_PROJECT_DIR / ".env")
load_dotenv(DAY9_PROJECT_DIR / ".env", override=False)

TOKEN_RE = re.compile(r"[\w\-]+", re.UNICODE)


@dataclass
class AgentState:
    question: str
    intent: str = "mixed"
    search_queries: list[str] = field(default_factory=list)
    retrieved: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    answer: str = ""
    trace: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class Worker(Protocol):
    name: str

    def run(self, state: AgentState) -> AgentState:
        ...


class QueryPlannerWorker:
    name = "query_planner"

    def run(self, state: AgentState) -> AgentState:
        query = _normalize_text(state.question)
        legal_terms = {"luat", "dieu", "hinh phat", "ma tuy", "cai nghien", "nghi dinh", "bo luat"}
        news_terms = {"nghe si", "ca si", "dien vien", "bi bat", "tin tuc", "dantri", "thanhnien"}

        legal_hit = any(term in query for term in legal_terms)
        news_hit = any(term in query for term in news_terms)
        if legal_hit and news_hit:
            state.intent = "mixed"
        elif legal_hit:
            state.intent = "legal"
        elif news_hit:
            state.intent = "news"
        else:
            state.intent = "general"

        variants = [state.question]
        if state.intent in {"legal", "mixed", "general"}:
            variants.append(f"{state.question} quy dinh phap luat hinh phat ma tuy")
        if state.intent in {"news", "mixed"}:
            variants.append(f"{state.question} nghe si tin tuc ma tuy")

        state.search_queries = _dedupe_strings(variants)
        return state


class RetrievalWorker:
    name = "retrieval_worker"

    def __init__(self, top_k: int = 5) -> None:
        self.top_k = top_k

    def run(self, state: AgentState) -> AgentState:
        results: list[dict[str, Any]] = []
        for query in state.search_queries or [state.question]:
            results.extend(_retrieve_from_day8(query, top_k=self.top_k))

        state.retrieved = _dedupe_results(results)[: self.top_k * 2]
        return state


class EvidenceWorker:
    name = "evidence_worker"

    def __init__(self, top_k: int = 5) -> None:
        self.top_k = top_k

    def run(self, state: AgentState) -> AgentState:
        evidence = []
        for index, item in enumerate(state.retrieved[: self.top_k], 1):
            metadata = item.get("metadata", {}) or {}
            source = metadata.get("source") or item.get("source") or f"source_{index}"
            evidence.append({
                "id": f"S{index}",
                "source": source,
                "score": round(float(item.get("score", 0.0)), 4),
                "content": " ".join(str(item.get("content", "")).split())[:1100],
                "citation": _citation_label(source),
            })
        state.evidence = evidence
        return state


class AnswerWorker:
    name = "answer_worker"

    def run(self, state: AgentState) -> AgentState:
        if not state.evidence:
            state.answer = "Mình chưa tìm thấy bằng chứng đủ rõ trong corpus Day 8 để trả lời có citation."
            return state

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if api_key and api_key != "your_key_here":
            try:
                state.answer = self._llm_answer(state, api_key)
                return state
            except Exception as exc:
                state.trace.append({
                    "worker": self.name,
                    "status": "fallback",
                    "detail": f"LLM generation failed, using extractive answer: {exc}",
                })

        state.answer = self._extractive_answer(state)
        return state

    def _llm_answer(self, state: AgentState, api_key: str) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        context = _format_evidence(state.evidence)
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Bạn là Supervisor Agent tổng hợp câu trả lời từ các worker RAG. "
                        "Chỉ dùng evidence được cung cấp. Trả lời tiếng Việt, rõ ràng, "
                        "mỗi ý quan trọng phải có citation dạng [S1], [S2]. "
                        "Nếu evidence không đủ, nói rõ chưa thể xác minh."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Câu hỏi: {state.question}\n\nEvidence:\n{context}",
                },
            ],
            temperature=0.2,
            top_p=0.9,
        )
        return response.choices[0].message.content or ""

    def _extractive_answer(self, state: AgentState) -> str:
        parts = [
            "Dưới đây là câu trả lời tổng hợp theo mô hình Supervisor - Workers:",
            f"- Supervisor phân loại câu hỏi là: {state.intent}.",
            "- Các worker đã truy xuất và lọc các nguồn liên quan trong corpus Day 8.",
            "",
        ]
        for item in state.evidence[:3]:
            excerpt = item["content"][:360].rstrip()
            parts.append(f"{excerpt} [{item['id']}].")
        parts.append("")
        parts.append("Nguồn:")
        for item in state.evidence:
            parts.append(f"- [{item['id']}] {item['source']} | score={item['score']}")
        return "\n".join(parts)


class SupervisorAgent:
    """Coordinates workers and records per-worker latency."""

    def __init__(self, workers: list[Worker] | None = None) -> None:
        self.workers = workers or [
            QueryPlannerWorker(),
            RetrievalWorker(top_k=5),
            EvidenceWorker(top_k=5),
            AnswerWorker(),
        ]

    def run(self, question: str) -> dict[str, Any]:
        state = AgentState(question=question)
        started = time.perf_counter()

        for worker in self.workers:
            step_started = time.perf_counter()
            try:
                state = worker.run(state)
                status = "ok"
                detail = self._step_detail(worker.name, state)
            except Exception as exc:
                status = "error"
                detail = str(exc)
                state.trace.append({
                    "worker": worker.name,
                    "status": status,
                    "detail": detail,
                    "latency_ms": round((time.perf_counter() - step_started) * 1000, 2),
                })
                raise

            state.trace.append({
                "worker": worker.name,
                "status": status,
                "detail": detail,
                "latency_ms": round((time.perf_counter() - step_started) * 1000, 2),
            })

        state.metrics = {
            "total_latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "workers": len(self.workers),
            "retrieved": len(state.retrieved),
            "evidence": len(state.evidence),
            "intent": state.intent,
        }
        return {
            "question": state.question,
            "answer": state.answer,
            "intent": state.intent,
            "search_queries": state.search_queries,
            "evidence": state.evidence,
            "trace": state.trace,
            "metrics": state.metrics,
        }

    @staticmethod
    def _step_detail(worker_name: str, state: AgentState) -> str:
        if worker_name == "query_planner":
            return f"intent={state.intent}, search_queries={len(state.search_queries)}"
        if worker_name == "retrieval_worker":
            return f"retrieved={len(state.retrieved)} chunks"
        if worker_name == "evidence_worker":
            return f"selected={len(state.evidence)} evidence chunks"
        if worker_name == "answer_worker":
            return f"answer_chars={len(state.answer)}"
        return "completed"


def _retrieve_from_day8(query: str, top_k: int) -> list[dict[str, Any]]:
    use_full_pipeline = os.getenv("ASSIGNMENT_USE_DAY8_PIPELINE", "0").strip().lower()
    if use_full_pipeline not in {"1", "true", "yes", "on"}:
        return _local_markdown_retrieve(query, top_k=top_k)

    try:
        from src.task9_retrieval_pipeline import retrieve

        return retrieve(query, top_k=top_k)
    except Exception:
        return _local_markdown_retrieve(query, top_k=top_k)


def _local_markdown_retrieve(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    docs = _load_markdown_chunks()
    query_terms = _tokenize(query)
    if not query_terms:
        return []

    scored = []
    for doc in docs:
        tokens = _tokenize(doc["content"])
        score = _simple_bm25(query_terms, tokens)
        if score <= 0:
            continue
        scored.append({
            "content": doc["content"],
            "metadata": doc["metadata"],
            "score": score,
            "source": "local_markdown_fallback",
        })
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def _load_markdown_chunks() -> list[dict[str, Any]]:
    base_dir = DAY8_PROJECT_DIR / "data" / "standardized"
    chunks = []
    for path in sorted(base_dir.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for index, chunk in enumerate(_chunk_text(text)):
            chunks.append({
                "content": chunk,
                "metadata": {
                    "source": path.name,
                    "path": str(path.relative_to(DAY8_PROJECT_DIR)),
                    "chunk_index": index,
                    "type": _doc_type(path),
                },
            })
    return chunks


def _chunk_text(text: str, max_chars: int = 1400) -> list[str]:
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}".strip()
        else:
            if current:
                chunks.append(current)
            current = paragraph[:max_chars]
    if current:
        chunks.append(current)
    return chunks


def _simple_bm25(query_terms: list[str], doc_terms: list[str]) -> float:
    if not doc_terms:
        return 0.0
    counts: dict[str, int] = {}
    for term in doc_terms:
        counts[term] = counts.get(term, 0) + 1
    score = 0.0
    doc_len = len(doc_terms)
    for term in query_terms:
        freq = counts.get(term, 0)
        if freq:
            score += (freq * 2.2) / (freq + 1.2 * (0.25 + 0.75 * doc_len / 300))
    return float(score)


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(_normalize_text(text))]


def _normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFD", text.lower())
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return value.replace("đ", "d")


def _dedupe_strings(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        key = value.strip().lower()
        if key and key not in seen:
            seen.add(key)
            output.append(value)
    return output


def _dedupe_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for item in sorted(results, key=lambda row: float(row.get("score", 0.0)), reverse=True):
        content = str(item.get("content", ""))
        key = content[:180]
        if key and key not in seen:
            seen.add(key)
            output.append(item)
    return output


def _format_evidence(evidence: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"[{item['id']}] Source: {item['source']} | Score: {item['score']}\n{item['content']}"
        for item in evidence
    )


def _citation_label(source: str) -> str:
    stem = Path(source).stem.replace("_", " ").replace("-", " ").strip()
    year = next((part for part in stem.split() if part.isdigit() and len(part) == 4), "")
    return f"{stem}, {year}" if year else stem


def _doc_type(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    if "news" in parts or "cleaned_news" in parts or "uncleaned_news" in parts:
        return "news"
    if "legal_text" in parts or "clean_legal_text" in parts:
        return "legal_text"
    return "unknown"


def save_result(result: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
