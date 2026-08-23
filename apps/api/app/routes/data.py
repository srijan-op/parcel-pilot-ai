from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import Account, Document, Order, Ticket
from app.db.session import get_db
from app.timeutil import get_snapshot_at

router = APIRouter(prefix="/data", tags=["data"])


@router.get("/stats")
def data_stats(db: Session = Depends(get_db)) -> dict:
    """Row counts after ingest — verify Phase A3."""
    try:
        db.execute(text("SELECT 1"))
        return {
            "snapshot_at": get_snapshot_at().isoformat(),
            "accounts": db.scalar(select(func.count()).select_from(Account)) or 0,
            "orders": db.scalar(select(func.count()).select_from(Order)) or 0,
            "tickets": db.scalar(select(func.count()).select_from(Ticket)) or 0,
            "documents": db.scalar(select(func.count()).select_from(Document)) or 0,
        }
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database unavailable: {exc}",
        ) from exc
