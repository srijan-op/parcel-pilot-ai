from app.db.base import Base
from app.db.models import (  # noqa: F401
    Account,
    AuditLog,
    Document,
    Escalation,
    FollowUpTask,
    Order,
    PendingAction,
    Ticket,
)
from app.db.session import get_engine


def create_all_tables() -> None:
    Base.metadata.create_all(bind=get_engine())
