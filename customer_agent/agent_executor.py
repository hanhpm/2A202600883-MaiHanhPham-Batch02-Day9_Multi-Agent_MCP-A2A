"""Customer Agent — AgentExecutor bridge between A2A SDK and LangGraph."""

from __future__ import annotations

import logging
import os
from uuid import uuid4

from langchain_core.messages import HumanMessage

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TextPart

from common.trace import emit_event
from customer_agent.graph import build_graph

logger = logging.getLogger(__name__)


class CustomerAgentExecutor(AgentExecutor):
    """Bridges A2A RequestContext to the Customer LangGraph agent."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        question = self._extract_question(context)
        context_id = context.context_id or str(uuid4())
        task_id = context.task_id or str(uuid4())

        # Propagate or generate trace metadata
        metadata = context.message.metadata or {} if context.message else {}
        trace_id = metadata.get("trace_id", str(uuid4()))
        depth = int(metadata.get("delegation_depth", 0))

        logger.info(
            "CustomerAgent executing | task=%s context=%s trace=%s depth=%d",
            task_id, context_id, trace_id, depth,
        )

        updater = TaskUpdater(event_queue, task_id, context_id)
        await updater.submit()
        await updater.start_work()
        await emit_event(
            trace_id=trace_id,
            context_id=context_id,
            agent="Customer Agent",
            event="agent.start",
            detail="Received user question and preparing delegate tool",
            status="running",
        )

        try:
            if _fast_delegate_enabled():
                answer = await self._delegate_directly(
                    question=question,
                    context_id=context_id,
                    trace_id=trace_id,
                    depth=depth,
                )
            else:
                answer = await self._run_react_customer_graph(
                    question=question,
                    context_id=context_id,
                    trace_id=trace_id,
                    depth=depth,
                )

            if not answer:
                answer = "I was unable to process your legal question at this time."

            await updater.add_artifact(
                parts=[Part(root=TextPart(text=answer))],
                name="legal_response",
            )
            await emit_event(
                trace_id=trace_id,
                context_id=context_id,
                agent="Customer Agent",
                event="agent.complete",
                detail="Final response returned to the user",
                status="done",
                data={"chars": len(answer)},
            )
            await updater.complete()

        except Exception as exc:
            logger.exception("CustomerAgent execution error: %s", exc)
            await emit_event(
                trace_id=trace_id,
                context_id=context_id,
                agent="Customer Agent",
                event="agent.error",
                detail=str(exc),
                status="error",
            )
            await updater.failed(
                updater.new_agent_message(
                    parts=[Part(root=TextPart(text=f"Request failed: {exc}"))]
                )
            )

    async def _delegate_directly(
        self,
        *,
        question: str,
        context_id: str,
        trace_id: str,
        depth: int,
    ) -> str:
        """Fast path: skip Customer ReAct LLM and delegate directly to Law Agent."""
        from common.a2a_client import delegate
        from common.registry_client import discover

        await emit_event(
            trace_id=trace_id,
            context_id=context_id,
            agent="Customer Agent",
            event="fast_delegate",
            detail="Skipping Customer ReAct loop and delegating directly to Law Agent",
            tool="Registry discover + A2A",
        )
        endpoint = await discover("legal_question")
        return await delegate(
            endpoint=endpoint,
            question=question,
            context_id=context_id,
            trace_id=trace_id,
            depth=depth + 1,
        )

    async def _run_react_customer_graph(
        self,
        *,
        question: str,
        context_id: str,
        trace_id: str,
        depth: int,
    ) -> str:
        """Original Customer Agent ReAct behavior."""
        # Build a per-request graph so the tool closure captures this request's IDs
        graph = build_graph(
            trace_id=trace_id,
            context_id=context_id,
            depth=depth,
        )

        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=question)]},
            config={"configurable": {"thread_id": context_id}},
        )

        # Extract the last AI message from the result
        answer = ""
        for msg in reversed(result.get("messages", [])):
            if hasattr(msg, "content") and msg.content:
                if not isinstance(msg, HumanMessage):
                    # Skip ToolMessages, only want final AIMessage
                    from langchain_core.messages import AIMessage
                    if isinstance(msg, AIMessage):
                        answer = msg.content
                        break

        if not answer:
            # Fallback: any non-human message content
            for msg in reversed(result.get("messages", [])):
                content = getattr(msg, "content", "")
                if content and not isinstance(msg, HumanMessage):
                    answer = content
                    break
        return answer

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or str(uuid4())
        context_id = context.context_id or str(uuid4())
        updater = TaskUpdater(event_queue, task_id, context_id)
        await updater.cancel()

    @staticmethod
    def _extract_question(context: RequestContext) -> str:
        if context.message and context.message.parts:
            parts = []
            for part in context.message.parts:
                inner = getattr(part, "root", part)
                text = getattr(inner, "text", None)
                if text:
                    parts.append(text)
            return "\n".join(parts)
        return ""


def _fast_delegate_enabled() -> bool:
    value = os.getenv("CUSTOMER_FAST_DELEGATE", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}
