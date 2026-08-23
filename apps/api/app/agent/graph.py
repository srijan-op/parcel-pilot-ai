from __future__ import annotations

import uuid
from collections.abc import Iterator
from functools import lru_cache
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command
from sqlalchemy.orm import Session

from app.agent.list_documents import format_catalog_for_prompt, list_documents
from app.agent.prompts import build_system_prompt
from app.agent.tools import build_agent_tools
from app.auth.models import AuthUser
from app.config import get_settings
from app.trust.synthesis import synthesize_trust


@lru_cache
def get_checkpointer() -> MemorySaver:
    return MemorySaver()


def _is_rate_limit_error(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    return (
        "ratelimit" in name
        or "rate_limit" in text
        or "rate limit" in text
        or "tokens per minute" in text
        or "tpm" in text
        or "429" in text
    )


def _build_llm() -> ChatGroq:
    settings = get_settings()
    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY is required for the chat agent")

    primary_key = settings.groq_api_key
    fallback_key = (settings.groq_api_key_2 or "").strip() or None
    model = settings.groq_model

    def _make(api_key: str) -> ChatGroq:
        return ChatGroq(api_key=api_key, model=model, temperature=0)

    if not fallback_key:
        return _make(primary_key)

    class ChatGroqWithKeyFallback(ChatGroq):
        """Primary Groq key; on TPM/429, retry once with GROQ_API_KEY_2."""

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[no-untyped-def]
            try:
                return super()._generate(
                    messages, stop=stop, run_manager=run_manager, **kwargs
                )
            except Exception as exc:
                if not _is_rate_limit_error(exc):
                    raise
                return _make(fallback_key)._generate(
                    messages, stop=stop, run_manager=run_manager, **kwargs
                )

        def _stream(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[no-untyped-def]
            try:
                yield from super()._stream(
                    messages, stop=stop, run_manager=run_manager, **kwargs
                )
            except Exception as exc:
                if not _is_rate_limit_error(exc):
                    raise
                yield from _make(fallback_key)._stream(
                    messages, stop=stop, run_manager=run_manager, **kwargs
                )

    return ChatGroqWithKeyFallback(api_key=primary_key, model=model, temperature=0)


def _build_agent(user: AuthUser, db: Session):
    catalog = list_documents(user, include_deprecated=False)
    system_prompt = build_system_prompt(user, format_catalog_for_prompt(catalog))
    tools = build_agent_tools(user, db)
    return create_react_agent(
        _build_llm(),
        tools,
        prompt=system_prompt,
        checkpointer=get_checkpointer(),
    )


def _extract_tool_trace(messages: list[Any], *, since_last_human: bool = True) -> list[dict[str, Any]]:
    """
    Build tool call/result pairs for trust + UI.
    By default only tools after the latest HumanMessage (current turn).
    """
    scoped = messages
    if since_last_human:
        last_human = -1
        for i, msg in enumerate(messages):
            if isinstance(msg, HumanMessage):
                last_human = i
        if last_human >= 0:
            scoped = messages[last_human + 1 :]

    ordered: list[dict[str, Any]] = []
    pending: dict[str, dict[str, Any]] = {}
    for msg in scoped:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for call in msg.tool_calls:
                item = {
                    "tool": call.get("name"),
                    "args": call.get("args") or {},
                    "result_preview": None,
                }
                ordered.append(item)
                pending[str(call.get("id") or "")] = item
        if isinstance(msg, ToolMessage):
            item = pending.get(str(msg.tool_call_id))
            if item is not None:
                item["result_preview"] = str(msg.content)[:800]
    return ordered


def _final_answer(messages: list[Any]) -> str:
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage) or not msg.content:
            continue
        tool_calls = getattr(msg, "tool_calls", None) or []
        if tool_calls:
            continue
        content = msg.content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
            text = "\n".join(parts).strip()
            if text:
                return text
        else:
            return str(content).strip()
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content).strip()
    return ""


def _serialize_interrupt(raw: Any) -> dict[str, Any] | None:
    if not raw:
        return None
    # create_react_agent may return tuple/list of Interrupt objects
    first = raw[0] if isinstance(raw, (list, tuple)) else raw
    value = getattr(first, "value", first)
    if isinstance(value, dict):
        return value
    return {"raw": str(value)}


def _interrupt_from_state(agent: Any, config: dict[str, Any]) -> dict[str, Any] | None:
    """
    LangGraph 0.2 invoke() often omits __interrupt__ from the return dict.
    Pending interrupts live on get_state(...).tasks[].interrupts.
    """
    state = agent.get_state(config)
    if state is None:
        return None
    for task in list(getattr(state, "tasks", None) or []):
        interrupts = getattr(task, "interrupts", None)
        if interrupts:
            return _serialize_interrupt(interrupts)
    direct = getattr(state, "interrupts", None)
    if direct:
        return _serialize_interrupt(direct)
    return None


def _resolve_interrupt(
    agent: Any,
    config: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any] | None:
    return _serialize_interrupt(result.get("__interrupt__")) or _interrupt_from_state(
        agent, config
    )


def _pack_response(
    *,
    thread_id: str,
    user: AuthUser,
    messages: list[Any],
    interrupt_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if interrupt_payload:
        draft = interrupt_payload.get("draft") or {}
        pending = interrupt_payload.get("pending_action") or {}
        answer = (
            interrupt_payload.get("message")
            or "Action proposed. Please confirm or cancel to continue."
        )
        tools_used = _extract_tool_trace(messages)
        trust = synthesize_trust(answer=answer, tools_used=tools_used)
        return {
            "thread_id": thread_id,
            "status": "awaiting_confirmation",
            "answer": answer,
            "awaiting_confirmation": True,
            "action_type": interrupt_payload.get("action_type"),
            "pending_id": interrupt_payload.get("pending_id") or pending.get("pending_id"),
            "draft": draft,
            "pending_action": pending or None,
            "interrupt": interrupt_payload,
            "tools_used": tools_used,
            "trust": {
                "confidence": trust["confidence"],
                "conflicts": trust["conflicts"],
                "citations": trust["citations"],
                "flags": sorted(set(trust["flags"] + ["needs_confirmation", "awaiting_hitl"])),
                "facts": trust["facts"],
                "agreement_override": trust["agreement_override"],
                "abstain": trust["abstain"],
                "needs_manager_approval": trust["needs_manager_approval"],
                "recommend_escalation": trust["recommend_escalation"],
                "needs_confirmation": True,
                "summary": trust["trust_summary"],
            },
            "user": {
                "persona_id": user.persona_id,
                "role": user.role,
                "account_id": user.account_id,
            },
        }

    answer = _final_answer(messages)
    tools_used = _extract_tool_trace(messages)
    trust = synthesize_trust(answer=answer, tools_used=tools_used)
    return {
        "thread_id": thread_id,
        "status": "completed",
        "answer": trust["answer"],
        "awaiting_confirmation": False,
        "pending_id": trust["facts"].get("pending_action_id"),
        "tools_used": tools_used,
        "trust": {
            "confidence": trust["confidence"],
            "conflicts": trust["conflicts"],
            "citations": trust["citations"],
            "flags": trust["flags"],
            "facts": trust["facts"],
            "agreement_override": trust["agreement_override"],
            "abstain": trust["abstain"],
            "needs_manager_approval": trust["needs_manager_approval"],
            "recommend_escalation": trust["recommend_escalation"],
            "needs_confirmation": trust["needs_confirmation"],
            "summary": trust["trust_summary"],
        },
        "user": {
            "persona_id": user.persona_id,
            "role": user.role,
            "account_id": user.account_id,
        },
    }


def _messages_from_state(agent: Any, config: dict[str, Any]) -> list[Any]:
    state = agent.get_state(config)
    if state is None:
        return []
    values = getattr(state, "values", None) or {}
    if isinstance(values, dict):
        return list(values.get("messages") or [])
    return []


def _normalize_messages(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    return [raw]


def _emit_from_update(node: str, update: Any) -> Iterator[dict[str, Any]]:
    """Translate a LangGraph updates-chunk into UI-facing stream events."""
    if not isinstance(update, dict):
        return
    messages = _normalize_messages(update.get("messages"))
    if node == "agent":
        for msg in messages:
            if not isinstance(msg, AIMessage):
                continue
            tool_calls = getattr(msg, "tool_calls", None) or []
            for call in tool_calls:
                yield {
                    "event": "tool_start",
                    "data": {
                        "tool": call.get("name"),
                        "tool_call_id": call.get("id"),
                        "args": call.get("args") or {},
                    },
                }
            # Final-ish text mid-turn (rare while tools still pending)
            if msg.content and not tool_calls:
                text = _final_answer([msg])
                if text:
                    yield {"event": "assistant_delta", "data": {"text": text}}
    elif node == "tools":
        for msg in messages:
            if not isinstance(msg, ToolMessage):
                continue
            yield {
                "event": "tool_end",
                "data": {
                    "tool": getattr(msg, "name", None),
                    "tool_call_id": msg.tool_call_id,
                    "result_preview": str(msg.content)[:800],
                },
            }


def _assert_awaiting_interrupt(agent: Any, config: dict[str, Any], thread_id: str) -> None:
    state = agent.get_state(config)
    has_interrupt = False
    if state is not None:
        for task in list(getattr(state, "tasks", None) or []):
            if getattr(task, "interrupts", None):
                has_interrupt = True
                break
        if not has_interrupt and getattr(state, "interrupts", None):
            has_interrupt = True
    if not has_interrupt:
        raise ValueError(
            f"Thread '{thread_id}' is not awaiting confirmation. "
            "Send a /chat message that proposes a write action first "
            "(escalation, ticket update, or follow-up)."
        )


def _stream_graph(
    *,
    agent: Any,
    config: dict[str, Any],
    input_payload: Any,
    thread_id: str,
    user: AuthUser,
) -> Iterator[dict[str, Any]]:
    """
    Yield SSE-oriented events while the agent runs.

    Events: start | tool_start | tool_end | assistant_delta |
            awaiting_confirmation | final | error
    """
    yield {"event": "start", "data": {"thread_id": thread_id}}
    try:
        for chunk in agent.stream(input_payload, config=config, stream_mode="updates"):
            if not isinstance(chunk, dict):
                continue
            if "__interrupt__" in chunk:
                interrupt_payload = _serialize_interrupt(chunk.get("__interrupt__"))
                if not interrupt_payload:
                    interrupt_payload = _interrupt_from_state(agent, config)
                messages = _messages_from_state(agent, config)
                packed = _pack_response(
                    thread_id=thread_id,
                    user=user,
                    messages=messages,
                    interrupt_payload=interrupt_payload,
                )
                yield {"event": "awaiting_confirmation", "data": packed}
                return

            for node, update in chunk.items():
                if node == "__interrupt__":
                    continue
                yield from _emit_from_update(str(node), update)

        interrupt_payload = _interrupt_from_state(agent, config)
        messages = _messages_from_state(agent, config)
        packed = _pack_response(
            thread_id=thread_id,
            user=user,
            messages=messages,
            interrupt_payload=interrupt_payload,
        )
        if packed.get("awaiting_confirmation"):
            yield {"event": "awaiting_confirmation", "data": packed}
        else:
            yield {"event": "final", "data": packed}
    except Exception as exc:
        yield {"event": "error", "data": {"detail": str(exc)}}


def run_agent_turn(
    *,
    user: AuthUser,
    db: Session,
    message: str,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """
    Run one user turn. May return status=awaiting_confirmation if HITL paused.
    """
    thread_id = thread_id or str(uuid.uuid4())
    agent = _build_agent(user, db)
    config = {"configurable": {"thread_id": thread_id}}
    result = agent.invoke(
        {"messages": [HumanMessage(content=message)]},
        config=config,
    )
    interrupt_payload = _resolve_interrupt(agent, config, result)
    messages = result.get("messages") or []
    return _pack_response(
        thread_id=thread_id,
        user=user,
        messages=messages,
        interrupt_payload=interrupt_payload,
    )


def stream_agent_turn(
    *,
    user: AuthUser,
    db: Session,
    message: str,
    thread_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Stream one user turn as tool/status events (C5)."""
    thread_id = thread_id or str(uuid.uuid4())
    agent = _build_agent(user, db)
    config = {"configurable": {"thread_id": thread_id}}
    yield from _stream_graph(
        agent=agent,
        config=config,
        input_payload={"messages": [HumanMessage(content=message)]},
        thread_id=thread_id,
        user=user,
    )


def resume_agent_turn(
    *,
    user: AuthUser,
    db: Session,
    thread_id: str,
    decision: Literal["confirm", "cancel"],
) -> dict[str, Any]:
    """
    Resume a graph paused on a write-tool HITL
    (create_escalation / update_ticket / create_follow_up_task).
    decision: confirm | cancel
    """
    agent = _build_agent(user, db)
    config = {"configurable": {"thread_id": thread_id}}
    _assert_awaiting_interrupt(agent, config, thread_id)

    result = agent.invoke(
        Command(resume={"decision": decision}),
        config=config,
    )
    interrupt_payload = _resolve_interrupt(agent, config, result)
    messages = result.get("messages") or []
    return _pack_response(
        thread_id=thread_id,
        user=user,
        messages=messages,
        interrupt_payload=interrupt_payload,
    )


def stream_resume_agent_turn(
    *,
    user: AuthUser,
    db: Session,
    thread_id: str,
    decision: Literal["confirm", "cancel"],
) -> Iterator[dict[str, Any]]:
    """Stream HITL resume (confirm/cancel) with live tool events."""
    agent = _build_agent(user, db)
    config = {"configurable": {"thread_id": thread_id}}
    _assert_awaiting_interrupt(agent, config, thread_id)
    yield from _stream_graph(
        agent=agent,
        config=config,
        input_payload=Command(resume={"decision": decision}),
        thread_id=thread_id,
        user=user,
    )
