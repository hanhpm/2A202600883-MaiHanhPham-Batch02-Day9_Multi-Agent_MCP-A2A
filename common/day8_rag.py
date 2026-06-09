"""Lightweight Day 8 RAG retrieval for Day 9 agents.

The Day 8 project already contains cleaned Vietnamese legal/news markdown.
This module reuses that corpus without requiring Elasticsearch, pgvector, or
external embedding services, so the Day 9 multi-agent demo can run locally.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path
from typing import TypedDict


class RagResult(TypedDict):
    content: str
    score: float
    metadata: dict[str, str]


DAY8_PROJECT_NAME = "2A202600883-MaiHanhPham-Day08_RAG_pipeline_cohort2"
TOKEN_RE = re.compile(r"[\w\-]+", re.UNICODE)


def day8_project_dir() -> Path:
    """Return the sibling Day 8 project directory."""
    return Path(__file__).resolve().parents[2] / DAY8_PROJECT_NAME


def retrieve_day8_context(query: str, top_k: int = 4) -> list[RagResult]:
    """Retrieve relevant Day 8 markdown chunks with a BM25-like score."""
    query_terms = _tokenize(query)
    if not query_terms:
        return []

    corpus = _load_corpus()
    if not corpus:
        return []

    doc_freq: dict[str, int] = {}
    tokenized_docs: list[list[str]] = []
    for item in corpus:
        tokens = _tokenize(item["content"])
        tokenized_docs.append(tokens)
        for term in set(tokens):
            doc_freq[term] = doc_freq.get(term, 0) + 1

    total_docs = len(corpus)
    avg_len = sum(len(tokens) for tokens in tokenized_docs) / max(total_docs, 1)
    scored: list[RagResult] = []
    for item, tokens in zip(corpus, tokenized_docs):
        score = _bm25_score(query_terms, tokens, doc_freq, total_docs, avg_len)
        if score <= 0:
            continue
        scored.append({
            "content": item["content"],
            "score": float(score),
            "metadata": item["metadata"],
        })

    scored.sort(key=lambda row: row["score"], reverse=True)
    return scored[:top_k]


def format_context(results: list[RagResult]) -> str:
    """Format retrieval results for an LLM prompt or tool response."""
    if not results:
        return "No Day 8 RAG context found."

    blocks = []
    for index, item in enumerate(results, 1):
        metadata = item["metadata"]
        source = metadata.get("source", "unknown")
        doc_type = metadata.get("doc_type", "unknown")
        score = item["score"]
        content = " ".join(item["content"].split())
        blocks.append(f"[S{index}] {source} | {doc_type} | score={score:.3f}\n{content}")
    return "\n\n---\n\n".join(blocks)


def search_day8_rag(query: str, top_k: int = 4) -> str:
    """Convenience wrapper used by LangChain tools."""
    return format_context(retrieve_day8_context(query=query, top_k=top_k))


@lru_cache(maxsize=1)
def _load_corpus() -> list[dict]:
    base_dir = day8_project_dir() / "data" / "standardized"
    if not base_dir.exists():
        return []

    docs: list[dict] = []
    for path in sorted(base_dir.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        doc_type = _doc_type(path)
        for chunk_index, chunk in enumerate(_chunk_text(text)):
            docs.append({
                "content": chunk,
                "metadata": {
                    "source": path.name,
                    "path": str(path),
                    "doc_type": doc_type,
                    "chunk_index": str(chunk_index),
                },
            })
    return docs


def _chunk_text(text: str, max_chars: int = 1600, overlap: int = 250) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if not current:
            current = paragraph
        elif len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}"
        else:
            chunks.append(current[:max_chars])
            tail = current[-overlap:] if overlap else ""
            current = f"{tail}\n\n{paragraph}" if tail else paragraph

    if current:
        chunks.append(current[:max_chars])
    return chunks


def _bm25_score(
    query_terms: list[str],
    doc_terms: list[str],
    doc_freq: dict[str, int],
    total_docs: int,
    avg_len: float,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    if not doc_terms:
        return 0.0
    term_counts: dict[str, int] = {}
    for term in doc_terms:
        term_counts[term] = term_counts.get(term, 0) + 1

    score = 0.0
    doc_len = len(doc_terms)
    for term in query_terms:
        freq = term_counts.get(term, 0)
        if freq == 0:
            continue
        df = doc_freq.get(term, 0)
        idf = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))
        denom = freq + k1 * (1 - b + b * doc_len / max(avg_len, 1))
        score += idf * (freq * (k1 + 1)) / denom
    return score


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def _doc_type(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    if "clean_legal_text" in parts or "legal_text" in parts:
        return "legal_text"
    if "cleaned_news" in parts or "uncleaned_news" in parts or "news" in parts:
        return "news"
    return "unknown"
