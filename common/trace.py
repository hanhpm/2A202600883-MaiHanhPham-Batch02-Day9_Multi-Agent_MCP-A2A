"""Optional trace event emitter for the demo UI.

Agents post events to TRACE_EVENT_URL when it is configured. Failures are
intentionally ignored so tracing never breaks the A2A system.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx


TRACE_EVENT_URL = os.getenv("TRACE_EVENT_URL", "").strip()


async def emit_event(
    *,
    trace_id: str,
    context_id: str,
    agent: str,
    event: str,
    detail: str = "",
    tool: str = "",
    status: str = "running",
    data: dict[str, Any] | None = None,
) -> None:
    """Send a trace event to the UI if tracing is enabled."""
    if not TRACE_EVENT_URL or not trace_id:
        return

    payload = {
        "trace_id": trace_id,
        "context_id": context_id,
        "agent": agent,
        "event": event,
        "detail": detail,
        "tool": tool,
        "status": status,
        "ts": time.time(),
        "data": data or {},
    }
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(TRACE_EVENT_URL, json=payload)
    except Exception:
        return
