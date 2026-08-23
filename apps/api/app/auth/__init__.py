"""Mock JWT auth for ParcelPilot demo personas."""

from app.auth.acl import (
    ACLError,
    assert_account_access,
    is_customer,
    is_internal,
    require_roles,
    resolve_account_scope,
    scope_document_search,
)
from app.auth.deps import get_current_user, get_optional_user
from app.auth.models import AuthUser
from app.auth.personas import PERSONAS, get_persona, list_personas
from app.auth.tokens import create_access_token, decode_access_token

__all__ = [
    "ACLError",
    "PERSONAS",
    "AuthUser",
    "assert_account_access",
    "create_access_token",
    "decode_access_token",
    "get_current_user",
    "get_optional_user",
    "get_persona",
    "is_customer",
    "is_internal",
    "list_personas",
    "require_roles",
    "resolve_account_scope",
    "scope_document_search",
]
