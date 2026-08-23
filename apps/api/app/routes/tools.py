from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.acl import ACLError
from app.auth.deps import get_current_user
from app.auth.models import AuthUser
from app.db.session import get_db
from app.tools.structured_data import ALL_INTENTS, LOOKUP_INTENTS, READY_CALC_INTENTS, structured_data_query

router = APIRouter(prefix="/tools", tags=["tools"])


class StructuredDataRequest(BaseModel):
    intent: str = Field(
        ...,
        description=f"One of: {sorted(ALL_INTENTS)}",
    )
    account_id: str | None = None
    order_id: str | None = None
    ticket_id: str | None = None
    status: str | None = None
    severity: str | None = Field(
        default=None,
        description="Optional P1/P2/P3 override for calc_sla",
    )


@router.get("/intents")
def list_intents() -> dict[str, Any]:
    """Document supported structured_data_query intents."""
    return {
        "lookups": sorted(LOOKUP_INTENTS),
        "calculators_ready": sorted(READY_CALC_INTENTS),
        "calculators_coming": [],
    }


@router.post("/structured_data")
def structured_data_endpoint(
    body: StructuredDataRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Parameterized account/order/ticket lookups with JWT ACL.
    No raw SQL — agent (later) picks an intent + params.
    """
    try:
        result = structured_data_query(
            db,
            user,
            intent=body.intent,
            account_id=body.account_id,
            order_id=body.order_id,
            ticket_id=body.ticket_id,
            status=body.status,
            severity=body.severity,
        )
    except ACLError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {exc}",
        ) from exc

    return {
        "user": {
            "persona_id": user.persona_id,
            "role": user.role,
            "account_id": user.account_id,
        },
        **result,
    }
