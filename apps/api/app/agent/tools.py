from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.list_documents import list_documents
from app.auth.acl import ACLError, scope_document_search
from app.auth.models import AuthUser
from app.tools.actions import (
    ACTION_CREATE_ESCALATION,
    ACTION_CREATE_FOLLOW_UP,
    ACTION_UPDATE_TICKET,
    confirm_action,
    propose_action,
)
from app.tools.document_search import document_search
from app.tools.structured_data import structured_data_query
from langgraph.errors import GraphBubbleUp
from langgraph.types import interrupt


def _json(data: Any) -> str:
    return json.dumps(data, default=str, ensure_ascii=True)


def _parse_hitl_decision(decision: Any) -> str:
    if isinstance(decision, str):
        return decision.strip().lower()
    if isinstance(decision, dict):
        return str(decision.get("decision", "")).strip().lower()
    return "cancel"


def _is_confirm(choice: str) -> bool:
    return choice in ("confirm", "approved", "yes", "y")


def _hitl_action(
    *,
    action_type: str,
    draft: dict[str, Any],
    message: str,
    propose_kwargs: dict[str, Any],
    db: Session,
    user: AuthUser,
) -> str:
    """
    Pause with interrupt(), then propose+confirm only after resume confirms.

    interrupt() re-executes this function from the top on resume, so all DB
    writes must happen AFTER interrupt returns (avoids duplicate pendings).
    """
    try:
        decision = interrupt(
            {
                "type": "confirm_action",
                "action_type": action_type,
                "draft": draft,
                "message": message,
            }
        )
        choice = _parse_hitl_decision(decision)
        if not _is_confirm(choice):
            return _json(
                {
                    "hitl": "cancelled",
                    "needs_confirmation": False,
                    "executed": False,
                    "action_type": action_type,
                    "draft": draft,
                    "detail": f"User cancelled; no {action_type} applied.",
                }
            )

        proposed = propose_action(db, user, action_type=action_type, **propose_kwargs)
        pending = proposed.get("pending_action") or {}
        pending_id = pending.get("pending_id")
        if not pending_id:
            return _json({"error": "propose_failed", "detail": proposed})

        executed = confirm_action(db, user, pending_id)
        return _json({"hitl": "confirmed", "action_type": action_type, **executed})
    except GraphBubbleUp:
        raise
    except ACLError as exc:
        return _json({"error": "access_denied", "detail": str(exc)})
    except LookupError as exc:
        return _json({"error": "not_found", "detail": str(exc)})
    except ValueError as exc:
        return _json({"error": "bad_request", "detail": str(exc)})
    except Exception as exc:
        return _json({"error": "tool_failed", "detail": str(exc)})


class ListDocumentsArgs(BaseModel):
    include_deprecated: bool = Field(
        default=False,
        description="If true, include DEPRECATED docs (historical questions only).",
    )


class DocumentSearchArgs(BaseModel):
    query: str = Field(..., description="Natural language search query")
    include_deprecated: bool = Field(default=False)
    doc_types: list[str] | None = Field(
        default=None,
        description="Optional filter: policy, sop, product, agreement",
    )
    top_k: int = Field(default=6, ge=1, le=12)


class StructuredDataArgs(BaseModel):
    intent: str = Field(
        ...,
        description=(
            "One of: get_account, get_order, list_orders, get_ticket, list_tickets, "
            "calc_cancellation, calc_service_credit, calc_sla"
        ),
    )
    account_id: str | None = None
    order_id: str | None = None
    ticket_id: str | None = None
    status: str | None = None
    severity: str | None = Field(
        default=None,
        description="Optional P1/P2/P3 override for calc_sla",
    )


class EscalateArgs(BaseModel):
    ticket_id: str
    severity: str = "P1"
    reason: str
    recommended_next_step: str


class UpdateTicketArgs(BaseModel):
    ticket_id: str
    status: str | None = Field(
        default=None,
        description="New ticket status if changing (e.g. Open, In Progress, Resolved)",
    )
    assigned_to: str | None = Field(
        default=None,
        description="Assignee name/queue if reassigning",
    )
    notes: str | None = Field(
        default=None,
        description="Note to append to the ticket history",
    )


class FollowUpArgs(BaseModel):
    title: str = Field(..., description="Short follow-up task title")
    details: str | None = Field(default=None, description="Optional task details")
    ticket_id: str | None = Field(
        default=None,
        description="Optional related ticket (required for internal users without account scope)",
    )


def build_agent_tools(user: AuthUser, db: Session) -> list[StructuredTool]:
    """Build LangChain tools closed over auth + DB session."""

    def _list_documents(include_deprecated: bool = False) -> str:
        docs = list_documents(user, include_deprecated=include_deprecated)
        return _json({"count": len(docs), "documents": docs})

    def _document_search(
        query: str,
        include_deprecated: bool = False,
        doc_types: list[str] | None = None,
        top_k: int = 6,
    ) -> str:
        try:
            scoped_account, scoped_deprecated = scope_document_search(
                user,
                requested_account_id=user.account_id if user.role == "customer" else None,
                include_deprecated=include_deprecated,
            )
            chunks = document_search(
                query,
                include_deprecated=scoped_deprecated,
                account_id=scoped_account,
                doc_types=doc_types,
                top_k=top_k,
            )
            return _json({"count": len(chunks), "chunks": chunks})
        except ACLError as exc:
            return _json({"error": "access_denied", "detail": str(exc)})
        except Exception as exc:
            return _json({"error": "search_failed", "detail": str(exc)})

    def _structured_data(
        intent: str,
        account_id: str | None = None,
        order_id: str | None = None,
        ticket_id: str | None = None,
        status: str | None = None,
        severity: str | None = None,
    ) -> str:
        try:
            result = structured_data_query(
                db,
                user,
                intent=intent,
                account_id=account_id,
                order_id=order_id,
                ticket_id=ticket_id,
                status=status,
                severity=severity,
            )
            return _json(result)
        except ACLError as exc:
            return _json({"error": "access_denied", "detail": str(exc)})
        except LookupError as exc:
            return _json({"error": "not_found", "detail": str(exc)})
        except ValueError as exc:
            return _json({"error": "bad_request", "detail": str(exc)})
        except Exception as exc:
            return _json({"error": "tool_failed", "detail": str(exc)})

    def _create_escalation(
        ticket_id: str,
        reason: str,
        recommended_next_step: str,
        severity: str = "P1",
    ) -> str:
        draft = {
            "ticket_id": ticket_id,
            "severity": severity,
            "reason": reason,
            "recommended_next_step": recommended_next_step,
        }
        return _hitl_action(
            action_type=ACTION_CREATE_ESCALATION,
            draft=draft,
            message=(
                f"Escalation proposed for {ticket_id} ({severity}) but not executed. "
                "Confirm to create the escalation, or cancel to discard."
            ),
            propose_kwargs={
                "ticket_id": ticket_id,
                "severity": severity,
                "reason": reason,
                "recommended_next_step": recommended_next_step,
            },
            db=db,
            user=user,
        )

    def _update_ticket(
        ticket_id: str,
        status: str | None = None,
        assigned_to: str | None = None,
        notes: str | None = None,
    ) -> str:
        draft = {
            "ticket_id": ticket_id,
            "status": status,
            "assigned_to": assigned_to,
            "notes": notes,
        }
        return _hitl_action(
            action_type=ACTION_UPDATE_TICKET,
            draft=draft,
            message=(
                f"Ticket update proposed for {ticket_id} but not executed. "
                "Confirm to apply the update, or cancel to discard."
            ),
            propose_kwargs={
                "ticket_id": ticket_id,
                "status": status,
                "assigned_to": assigned_to,
                "notes": notes,
            },
            db=db,
            user=user,
        )

    def _create_follow_up(
        title: str,
        details: str | None = None,
        ticket_id: str | None = None,
    ) -> str:
        draft = {
            "ticket_id": ticket_id,
            "title": title,
            "details": details,
        }
        label = ticket_id or "account"
        return _hitl_action(
            action_type=ACTION_CREATE_FOLLOW_UP,
            draft=draft,
            message=(
                f"Follow-up task proposed ({title!r} for {label}) but not created. "
                "Confirm to create the task, or cancel to discard."
            ),
            propose_kwargs={
                "ticket_id": ticket_id,
                "title": title,
                "details": details,
            },
            db=db,
            user=user,
        )

    tools = [
        StructuredTool.from_function(
            name="list_documents",
            description="List available policy/SOP/agreement documents and their status/authority.",
            func=_list_documents,
            args_schema=ListDocumentsArgs,
        ),
        StructuredTool.from_function(
            name="document_search",
            description="Semantic search over ParcelPilot policy PDFs and agreements.",
            func=_document_search,
            args_schema=DocumentSearchArgs,
        ),
        StructuredTool.from_function(
            name="structured_data_query",
            description=(
                "Lookup accounts/orders/tickets or run calculators "
                "(calc_cancellation, calc_service_credit, calc_sla). "
                "get_ticket also returns parsed_order_ids and related_orders inferred "
                "from ticket text (ORD-#### mentions, carrier/status hints)."
            ),
            func=_structured_data,
            args_schema=StructuredDataArgs,
        ),
        StructuredTool.from_function(
            name="create_escalation",
            description=(
                "Propose a ticket escalation and pause for human confirmation. "
                "After the user confirms or cancels, returns the execution result. "
                "Do not claim the escalation is done until confirmation succeeds."
            ),
            func=_create_escalation,
            args_schema=EscalateArgs,
        ),
        StructuredTool.from_function(
            name="update_ticket",
            description=(
                "Propose a ticket status/assignee/notes update and pause for confirmation. "
                "Provide at least one of status, assigned_to, or notes. "
                "Do not claim the ticket was updated until confirmation succeeds."
            ),
            func=_update_ticket,
            args_schema=UpdateTicketArgs,
        ),
        StructuredTool.from_function(
            name="create_follow_up_task",
            description=(
                "Propose a follow-up task and pause for confirmation. "
                "Use when someone should be reminded to act later. "
                "Do not claim the task exists until confirmation succeeds."
            ),
            func=_create_follow_up,
            args_schema=FollowUpArgs,
        ),
    ]
    return tools
