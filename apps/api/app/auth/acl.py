from __future__ import annotations

from app.auth.models import AuthUser


class ACLError(PermissionError):
    """Raised when a caller is not allowed to access a resource."""


def is_internal(user: AuthUser) -> bool:
    return user.role in ("support_agent", "ops_admin")


def is_customer(user: AuthUser) -> bool:
    return user.role == "customer"


def require_roles(user: AuthUser, *allowed: str) -> None:
    if user.role not in allowed:
        raise ACLError(f"Role '{user.role}' is not allowed for this action")


def assert_account_access(user: AuthUser, resource_account_id: str | None) -> None:
    """
    Customers may only touch their own account.
    Internal roles may touch any account.
    """
    if is_internal(user):
        return
    if not user.account_id:
        raise ACLError("Customer token is missing account_id")
    if resource_account_id is None:
        # Global / unscoped resource — OK for customers (e.g. CURRENT policy PDFs)
        return
    if resource_account_id != user.account_id:
        raise ACLError(
            f"Access denied: account {resource_account_id} is outside your scope "
            f"({user.account_id})"
        )


def resolve_account_scope(
    user: AuthUser,
    requested_account_id: str | None = None,
) -> str | None:
    """
    Decide which account_id filter to apply for list/search tools.

    - Customer: always force their own account_id (ignore or reject other requests)
    - Internal: use requested_account_id as-is (None = all accounts)
    """
    if is_customer(user):
        if not user.account_id:
            raise ACLError("Customer token is missing account_id")
        if requested_account_id and requested_account_id != user.account_id:
            raise ACLError(
                f"Access denied: cannot query account {requested_account_id} "
                f"as customer {user.account_id}"
            )
        return user.account_id

    return requested_account_id


def scope_document_search(
    user: AuthUser,
    *,
    requested_account_id: str | None = None,
    include_deprecated: bool = False,
) -> tuple[str | None, bool]:
    """
    ACL for document_search.

    Returns (account_id_filter, include_deprecated).

    Customer → filter to own account + global docs (via Chroma $or);
               never include deprecated.
    Internal → optional account filter; may include deprecated.
    """
    account_filter = resolve_account_scope(user, requested_account_id)
    if is_customer(user):
        return account_filter, False
    return account_filter, include_deprecated
