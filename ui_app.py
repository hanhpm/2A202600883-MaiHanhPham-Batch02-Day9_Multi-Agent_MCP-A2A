"""Interactive UI for the Day 9 A2A multi-agent demo."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from common.a2a_client import delegate

load_dotenv()

CUSTOMER_AGENT_URL = os.getenv("CUSTOMER_AGENT_URL", "http://localhost:10100")
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:10000")

app = FastAPI(title="Day 9 A2A Multi-Agent UI")
PROJECT_DIR = Path(__file__).resolve().parent
DOCS_DIR = PROJECT_DIR / "docs" / "slide_bai_giang"
if DOCS_DIR.exists():
    app.mount("/diagram-assets", StaticFiles(directory=str(DOCS_DIR)), name="diagram-assets")

TRACE_EVENTS: dict[str, list[dict[str, Any]]] = {}
TRACE_ANSWERS: dict[str, dict[str, Any]] = {}


class AskRequest(BaseModel):
    question: str
    trace_id: str | None = None
    language: str = "vi"


class TraceEvent(BaseModel):
    trace_id: str
    context_id: str = ""
    agent: str
    event: str
    detail: str = ""
    tool: str = ""
    status: str = "running"
    ts: float | None = None
    data: dict[str, Any] = {}


MODES = [
    {
        "id": "02_a2a_vs_traditional",
        "title": "A2A vs Traditional",
        "asset": "02_a2a_vs_traditional.svg",
        "focus": "So sánh agent gọi nhau qua giao thức chuẩn A2A với kiểu gọi function/service cứng.",
        "takeaway": "A2A giúp loose coupling: agent chỉ cần biết Agent Card và message schema.",
    },
    {
        "id": "03_a2a_protocol",
        "title": "A2A Protocol",
        "asset": "03_a2a_protocol.svg",
        "focus": "Các endpoint, message, task, artifact, và cách client gửi request tới agent.",
        "takeaway": "Trong demo này UI gửi message tới Customer Agent, các agent còn lại cũng trao đổi qua A2A.",
    },
    {
        "id": "04_system_architecture",
        "title": "System Architecture",
        "asset": "04_a2a_system_architecture.svg",
        "focus": "Registry, Customer, Law, Tax, Compliance Agent và các port đang chạy.",
        "takeaway": "Registry làm service discovery, không hardcode URL giữa các agent.",
    },
    {
        "id": "05_law_agent_graph",
        "title": "Law Agent Graph",
        "asset": "05_law_agent_graph.svg",
        "focus": "StateGraph của Law Agent: analyze, route, parallel delegates, aggregate.",
        "takeaway": "Law Agent là orchestrator: quyết định có gọi Tax/Compliance hay không.",
    },
    {
        "id": "06_request_flow",
        "title": "Request Flow",
        "asset": "06_request_flow.svg",
        "focus": "Trace propagation từ UI/Customer qua Law đến các specialist.",
        "takeaway": "Mỗi request có trace_id để UI gom events thành một flow dễ đọc.",
    },
    {
        "id": "07_a2a_intro",
        "title": "A2A Intro",
        "asset": "07_a2a_intro.svg",
        "focus": "Lý do cần A2A khi nhiều agent thuộc nhiều runtime/provider khác nhau.",
        "takeaway": "A2A là lớp giao tiếp chung, không phải một model hay một prompt.",
    },
    {
        "id": "08_a2a_core_concepts",
        "title": "Core Concepts",
        "asset": "08_a2a_core_concepts.svg",
        "focus": "Agent Card, Skills, Tasks, Messages, Parts, Artifacts.",
        "takeaway": "UI đọc Agent Card để biết agent có skill gì; response về dưới dạng artifact text.",
    },
    {
        "id": "09_a2a_interaction_flow",
        "title": "Interaction Flow",
        "asset": "09_a2a_interaction_flow.svg",
        "focus": "Trình tự interaction khi một agent gọi agent khác qua A2A client.",
        "takeaway": "Live timeline bên trái cho thấy cùng flow đó khi bạn nhập câu hỏi thật.",
    },
]


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return HTML


@app.get("/api/modes")
async def modes() -> dict:
    return {"modes": MODES}


@app.get("/api/agents")
async def agents() -> dict:
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{REGISTRY_URL}/agents")
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        return {"agents": [], "error": str(exc)}


@app.post("/api/trace")
async def trace_event(event: TraceEvent) -> dict:
    payload = event.model_dump()
    payload["ts"] = payload["ts"] or time.time()
    events = TRACE_EVENTS.setdefault(event.trace_id, [])
    events.append(payload)
    if len(events) > 250:
        del events[:-250]
    return {"ok": True}


@app.get("/api/traces/{trace_id}")
async def trace_events(trace_id: str) -> dict:
    events = TRACE_EVENTS.get(trace_id, [])
    return {
        "trace_id": trace_id,
        "events": events,
        "answer": TRACE_ANSWERS.get(trace_id),
        "metrics": _trace_metrics(events),
    }


@app.post("/api/ask")
async def ask(request: AskRequest) -> JSONResponse:
    question = request.question.strip()
    if not question:
        return JSONResponse({"error": "Question is required"}, status_code=400)

    trace_id = request.trace_id or str(uuid4())
    context_id = str(uuid4())
    TRACE_EVENTS[trace_id] = []
    TRACE_ANSWERS.pop(trace_id, None)
    await trace_event(TraceEvent(
        trace_id=trace_id,
        context_id=context_id,
        agent="UI",
        event="request.start",
        detail="User submitted a question",
        tool="FastAPI /api/ask",
    ))

    try:
        routed_question = _localized_question(question, request.language)
        answer = await delegate(
            endpoint=CUSTOMER_AGENT_URL,
            question=routed_question,
            context_id=context_id,
            trace_id=trace_id,
            depth=0,
        )
        TRACE_ANSWERS[trace_id] = {
            "ok": True,
            "question": question,
            "answer": answer,
            "trace_id": trace_id,
            "context_id": context_id,
            "language": request.language,
        }
        await trace_event(TraceEvent(
            trace_id=trace_id,
            context_id=context_id,
            agent="UI",
            event="request.complete",
            detail="Answer rendered in UI",
            tool="FastAPI /api/ask",
            status="done",
            data={"chars": len(answer)},
        ))
        return JSONResponse(TRACE_ANSWERS[trace_id])
    except Exception as exc:
        TRACE_ANSWERS[trace_id] = {
            "ok": False,
            "question": question,
            "error": str(exc),
            "trace_id": trace_id,
            "context_id": context_id,
            "language": request.language,
        }
        await trace_event(TraceEvent(
            trace_id=trace_id,
            context_id=context_id,
            agent="UI",
            event="request.error",
            detail=str(exc),
            tool="FastAPI /api/ask",
            status="error",
        ))
        return JSONResponse(TRACE_ANSWERS[trace_id], status_code=500)


def _localized_question(question: str, language: str) -> str:
    if language == "vi":
        return (
            f"{question}\n\n"
            "Output language: Vietnamese. Hãy trả lời bằng tiếng Việt rõ ràng, "
            "thân thiện với người học. Giữ các thuật ngữ kỹ thuật quan trọng như "
            "A2A, Agent Card, Registry, StateGraph, tool call nếu cần, nhưng giải thích ngắn gọn."
        )
    return (
        f"{question}\n\n"
        "Output language: English. Explain clearly for a learner and keep important "
        "A2A workflow terms visible."
    )


def _trace_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        return {"duration_ms": 0, "agents": 0, "tool_calls": 0, "a2a_calls": 0, "events": 0}

    agents = {
        item.get("agent", "")
        for item in events
        if item.get("agent") and item.get("agent") not in {"UI", "A2A Client"}
    }
    tools = [item for item in events if item.get("tool")]
    a2a_calls = [
        item for item in events
        if item.get("event") == "delegate.start" or "A2A" in str(item.get("tool", ""))
    ]
    started = min(float(item.get("ts", 0) or 0) for item in events)
    ended = max(float(item.get("ts", 0) or 0) for item in events)
    return {
        "duration_ms": int(max(0, ended - started) * 1000),
        "agents": len(agents),
        "tool_calls": len(tools),
        "a2a_calls": len(a2a_calls),
        "events": len(events),
    }


HTML = r"""
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>A2A Multi-Agent Workflow</title>
  <style>
    :root {
      --bg: #f7f8fa;
      --panel: #ffffff;
      --ink: #1d2733;
      --muted: #667085;
      --line: #dde3ea;
      --soft: #f1f4f7;
      --blue: #245f99;
      --green: #24745a;
      --red: #b42318;
      --amber: #a15c00;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }
    header {
      min-height: 64px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 12px 20px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 { font-size: 18px; margin: 0 0 3px; letter-spacing: 0; }
    .subtitle { color: var(--muted); font-size: 13px; }
    .status { display: flex; gap: 10px; align-items: center; color: var(--muted); font-size: 13px; }
    .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--amber); }
    main {
      display: grid;
      grid-template-columns: minmax(390px, 0.9fr) minmax(540px, 1.1fr);
      gap: 12px;
      padding: 12px;
      height: calc(100vh - 58px);
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      min-width: 0;
      overflow: hidden;
    }
    .left, .right { display: grid; grid-template-rows: auto 1fr; min-height: 0; }
    .toolbar {
      padding: 14px;
      border-bottom: 1px solid var(--line);
      display: grid;
      gap: 10px;
    }
    label { font-size: 12px; font-weight: 700; color: #344054; }
    textarea {
      width: 100%;
      min-height: 106px;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 12px;
      font: inherit;
      line-height: 1.45;
    }
    select {
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 10px;
      background: white;
      color: var(--ink);
    }
    button {
      border: 1px solid var(--blue);
      background: var(--blue);
      color: white;
      height: 36px;
      border-radius: 6px;
      padding: 0 13px;
      font-weight: 650;
      cursor: pointer;
    }
    button.secondary { background: white; color: var(--blue); }
    button:disabled { opacity: 0.55; cursor: wait; }
    .actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .trace-id { color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .content { min-height: 0; overflow: auto; padding: 12px; }
    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(80px, 1fr));
      gap: 8px;
      margin-bottom: 12px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 9px;
      background: var(--soft);
    }
    .metric strong { display: block; font-size: 18px; }
    .metric span { display: block; color: var(--muted); font-size: 12px; margin-top: 2px; }
    .flow {
      display: grid;
      grid-template-columns: repeat(3, minmax(100px, 1fr));
      gap: 8px;
      margin-bottom: 12px;
    }
    .node {
      border: 1px solid var(--line);
      border-radius: 8px;
      min-height: 72px;
      padding: 9px;
      display: grid;
      align-content: center;
      gap: 5px;
      background: #fbfcfe;
    }
    .node strong { font-size: 13px; overflow-wrap: anywhere; }
    .node span { color: var(--muted); font-size: 12px; }
    .node.running { border-color: var(--amber); box-shadow: inset 0 0 0 2px rgba(154,103,0,.08); }
    .node.done { border-color: var(--green); box-shadow: inset 0 0 0 2px rgba(27,127,90,.08); }
    .node.error { border-color: var(--red); }
    .timeline { display: grid; gap: 8px; }
    .event {
      border-left: 4px solid var(--line);
      padding: 8px 10px;
      background: #fbfcfe;
      border-radius: 5px;
    }
    .event.is-noise { display: none; }
    .event.running { border-left-color: var(--amber); }
    .event.done { border-left-color: var(--green); }
    .event.error { border-left-color: var(--red); }
    .event-head { display: flex; justify-content: space-between; gap: 8px; font-size: 13px; font-weight: 700; }
    .event small { color: var(--muted); display: block; margin-top: 4px; line-height: 1.35; }
    .answer {
      white-space: pre-wrap;
      line-height: 1.55;
      border-top: 1px solid var(--line);
      padding-top: 12px;
      margin-top: 12px;
    }
    .answer h3, .panel-title { margin: 0 0 8px; font-size: 15px; }
    .tabs {
      display: flex;
      gap: 6px;
      overflow-x: auto;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
    }
    .tab {
      border: 1px solid var(--line);
      color: var(--ink);
      background: white;
      white-space: nowrap;
      height: 32px;
      font-size: 12px;
    }
    .tab.active { border-color: var(--blue); color: white; background: var(--blue); }
    .mode-grid {
      display: grid;
      grid-template-columns: minmax(260px, 0.55fr) minmax(300px, 1fr);
      gap: 12px;
      align-items: start;
    }
    .mode-copy {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfe;
    }
    .mode-copy h2 { margin: 0 0 8px; font-size: 17px; }
    .mode-copy p { margin: 8px 0; color: var(--muted); line-height: 1.45; }
    .hint {
      margin-top: 12px;
      padding: 10px;
      border-radius: 8px;
      background: #eef6ff;
      color: #184b7a;
      font-size: 13px;
      line-height: 1.4;
    }
    .diagram {
      width: 100%;
      max-height: calc(100vh - 190px);
      object-fit: contain;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: white;
    }
    .agents {
      margin-top: 12px;
      display: grid;
      gap: 7px;
      font-size: 13px;
    }
    .agent-row { display: flex; justify-content: space-between; gap: 8px; border-bottom: 1px solid #eef1f5; padding-bottom: 6px; }
    @media (max-width: 980px) {
      main { grid-template-columns: 1fr; height: auto; }
      .mode-grid { grid-template-columns: 1fr; }
      .flow { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
      .metrics { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>A2A Multi-Agent Workflow</h1>
      <div class="subtitle">Nhập câu hỏi, xem agent nào được gọi, tool nào chạy, và vì sao flow đi theo nhánh đó.</div>
    </div>
    <div class="status"><span class="dot" id="statusDot"></span><span id="statusText">Checking services</span></div>
  </header>
  <main>
    <section class="left">
      <div class="toolbar">
        <label for="question">Câu hỏi thử nghiệm</label>
        <textarea id="question">Một công ty trốn thuế và chia sẻ dữ liệu người dùng khi chưa có sự đồng ý. Hệ quả pháp lý, thuế và tuân thủ là gì?</textarea>
        <div class="actions">
          <select id="language" title="Ngôn ngữ output">
            <option value="vi" selected>Trả lời tiếng Việt</option>
            <option value="en">Answer in English</option>
          </select>
          <button id="runBtn">Chạy workflow</button>
          <button class="secondary" id="agentsBtn">Kiểm tra agents</button>
        </div>
        <div class="trace-id" id="traceId">trace: not started</div>
      </div>
      <div class="content">
        <div class="metrics" id="metrics"></div>
        <h3 class="panel-title">Workflow hiện tại</h3>
        <div class="flow" id="flow"></div>
        <h3 class="panel-title">Các bước đang diễn ra</h3>
        <div class="timeline" id="timeline"></div>
        <div class="answer" id="answer"></div>
      </div>
    </section>
    <section class="right">
      <div class="tabs" id="tabs"></div>
      <div class="content">
        <div class="mode-grid">
          <div class="mode-copy">
            <h2 id="modeTitle"></h2>
            <p id="modeFocus"></p>
            <p id="modeTakeaway"></p>
            <div class="hint">Gợi ý: chọn từng tab để đối chiếu diagram lý thuyết với timeline live bên trái. Khi chạy câu hỏi thật, trace sẽ cho thấy khác biệt giữa routing, A2A call và tool call.</div>
            <div class="agents" id="agents"></div>
          </div>
          <img class="diagram" id="diagram" alt="A2A diagram" />
        </div>
      </div>
    </section>
  </main>
  <script>
    const nodes = ["UI", "Customer Agent", "Law Agent", "Tax Agent", "Compliance Agent", "Registry"];
    const eventNames = {
      "request.start": "Nhận câu hỏi",
      "agent.start": "Agent bắt đầu",
      "graph.node": "Chạy node trong graph",
      "route.decision": "Quyết định route",
      "delegate.tax": "Gọi Tax Agent",
      "delegate.compliance": "Gọi Compliance Agent",
      "delegate.start": "A2A request",
      "delegate.complete": "A2A response",
      "agent.complete": "Agent hoàn tất",
      "request.complete": "Hiển thị answer",
      "request.error": "Có lỗi",
      "agent.error": "Agent lỗi"
    };
    const flowEl = document.getElementById("flow");
    const timelineEl = document.getElementById("timeline");
    const answerEl = document.getElementById("answer");
    const metricsEl = document.getElementById("metrics");
    const runBtn = document.getElementById("runBtn");
    const traceIdEl = document.getElementById("traceId");
    const agentsEl = document.getElementById("agents");
    const statusDot = document.getElementById("statusDot");
    const statusText = document.getElementById("statusText");
    let currentTrace = null;
    let pollTimer = null;
    let modes = [];

    function renderMetrics(metrics = {}) {
      const duration = metrics.duration_ms ? `${(metrics.duration_ms / 1000).toFixed(1)}s` : "0s";
      metricsEl.innerHTML = [
        ["Thời gian", duration],
        ["Agents", metrics.agents || 0],
        ["A2A calls", metrics.a2a_calls || 0],
        ["Events", metrics.events || 0],
      ].map(([label, value]) => `<div class="metric"><strong>${value}</strong><span>${label}</span></div>`).join("");
    }

    function renderFlow(events = []) {
      const byAgent = {};
      for (const ev of events) byAgent[ev.agent] = ev.status || "running";
      flowEl.innerHTML = nodes.slice(0, 6).map(name => `
        <div class="node ${byAgent[name] || ""}">
          <strong>${name}</strong>
          <span>${statusLabel(byAgent[name])}</span>
        </div>`).join("");
    }

    function statusLabel(status) {
      if (status === "done") return "xong";
      if (status === "error") return "lỗi";
      if (status === "running") return "đang chạy";
      return "chờ";
    }

    function renderEvents(events) {
      const important = events.filter(ev => !["delegate.complete"].includes(ev.event));
      timelineEl.innerHTML = important.map(ev => `
        <div class="event ${ev.status || "running"}">
          <div class="event-head"><span>${ev.agent}</span><span>${eventNames[ev.event] || ev.event}</span></div>
          <small>${ev.detail || ""}</small>
          ${ev.tool ? `<small>tool: ${ev.tool}</small>` : ""}
        </div>`).join("");
    }

    async function pollTrace() {
      if (!currentTrace) return;
      const res = await fetch(`/api/traces/${currentTrace}`);
      const data = await res.json();
      renderFlow(data.events || []);
      renderEvents(data.events || []);
      renderMetrics(data.metrics || {});
      if (data.answer) {
        clearInterval(pollTimer);
        runBtn.disabled = false;
        if (data.answer.ok) {
          answerEl.innerHTML = `<h3>Kết quả trả lời</h3>${escapeHtml(data.answer.answer || "(empty answer)")}`;
        } else {
          answerEl.innerHTML = `<h3>Lỗi</h3>${escapeHtml(data.answer.error || "Request failed")}`;
        }
      }
    }

    async function runFlow() {
      const question = document.getElementById("question").value.trim();
      if (!question) return;
      currentTrace = crypto.randomUUID();
      traceIdEl.textContent = `trace: ${currentTrace}`;
      answerEl.textContent = "";
      timelineEl.innerHTML = "";
      renderMetrics({});
      renderFlow([]);
      runBtn.disabled = true;
      pollTimer = setInterval(pollTrace, 900);
      fetch("/api/ask", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          question,
          trace_id: currentTrace,
          language: document.getElementById("language").value
        })
      }).then(() => pollTrace()).catch(err => {
        answerEl.innerHTML = `<h3>Lỗi</h3>${escapeHtml(err.toString())}`;
        runBtn.disabled = false;
        clearInterval(pollTimer);
      });
    }

    async function loadModes() {
      const res = await fetch("/api/modes");
      modes = (await res.json()).modes;
      const tabs = document.getElementById("tabs");
      tabs.innerHTML = modes.map((m, i) => `<button class="tab ${i === 0 ? "active" : ""}" data-id="${m.id}">${m.id}</button>`).join("");
      tabs.addEventListener("click", ev => {
        if (!ev.target.dataset.id) return;
        document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
        ev.target.classList.add("active");
        showMode(ev.target.dataset.id);
      });
      showMode(modes[0].id);
    }

    function showMode(id) {
      const mode = modes.find(m => m.id === id);
      if (!mode) return;
      document.getElementById("modeTitle").textContent = mode.title;
      document.getElementById("modeFocus").textContent = mode.focus;
      document.getElementById("modeTakeaway").textContent = mode.takeaway;
      document.getElementById("diagram").src = `/diagram-assets/${mode.asset}`;
    }

    async function loadAgents() {
      try {
        const res = await fetch("/api/agents");
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        statusDot.style.background = "#1b7f5a";
        statusText.textContent = `${data.agents.length} registered agents`;
        agentsEl.innerHTML = data.agents.map(a => `
          <div class="agent-row"><span>${a.agent_name}</span><span>${(a.tasks || []).join(", ") || "entry"}</span></div>
        `).join("") || "<div>No agents registered yet.</div>";
      } catch (err) {
        statusDot.style.background = "#b42318";
        statusText.textContent = "Registry not reachable";
        agentsEl.innerHTML = `<div>${err.message}</div>`;
      }
    }

    function escapeHtml(text) {
      return String(text)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }

    runBtn.addEventListener("click", runFlow);
    document.getElementById("agentsBtn").addEventListener("click", loadAgents);
    renderMetrics({});
    renderFlow([]);
    loadModes();
    loadAgents();
    setInterval(loadAgents, 5000);
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
