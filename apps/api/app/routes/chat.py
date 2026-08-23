from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.graph import (
    resume_agent_turn,
    run_agent_turn,
    stream_agent_turn,
    stream_resume_agent_turn,
)
from app.auth.deps import get_current_user
from app.auth.models import AuthUser
from app.db.session import get_db

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    thread_id: str | None = Field(
        default=None,
        description="Optional conversation id; omit to start a new thread",
    )


class ChatResumeRequest(BaseModel):
    thread_id: str = Field(..., min_length=1)
    decision: Literal["confirm", "cancel"] = Field(
        ...,
        description="confirm = execute pending action; cancel = discard it",
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, default=str, ensure_ascii=True)
    return f"event: {event}\ndata: {payload}\n\n"


def _sse_stream(events):
    try:
        for item in events:
            yield _sse(item["event"], item.get("data") or {})
    except Exception as exc:
        yield _sse("error", {"detail": str(exc)})


@router.post("")
def chat(
    body: ChatRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Multi-step LangGraph agent turn (Groq + tools).
    May return status=awaiting_confirmation when a write tool pauses for HITL.
    """
    try:
        return run_agent_turn(
            user=user,
            db=db,
            message=body.message,
            thread_id=body.thread_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Agent failed: {exc}",
        ) from exc


@router.post("/stream")
def chat_stream(
    body: ChatRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """
    SSE stream of agent progress (C5).
    Events: start, tool_start, tool_end, assistant_delta,
            awaiting_confirmation, final, error
    """
    events = stream_agent_turn(
        user=user,
        db=db,
        message=body.message,
        thread_id=body.thread_id,
    )
    return StreamingResponse(
        _sse_stream(events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/resume")
def chat_resume(
    body: ChatResumeRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Resume after HITL pause (C3).
    Pass the same thread_id from the awaiting_confirmation response.
    """
    try:
        return resume_agent_turn(
            user=user,
            db=db,
            thread_id=body.thread_id,
            decision=body.decision,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Resume failed: {exc}",
        ) from exc


@router.post("/resume/stream")
def chat_resume_stream(
    body: ChatResumeRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """SSE stream while resuming a HITL-paused thread."""
    try:
        events = stream_resume_agent_turn(
            user=user,
            db=db,
            thread_id=body.thread_id,
            decision=body.decision,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return StreamingResponse(
        _sse_stream(events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
