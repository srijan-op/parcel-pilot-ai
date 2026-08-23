from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.acl import ACLError, scope_document_search
from app.auth.deps import get_current_user
from app.auth.models import AuthUser
from app.tools.document_search import document_search as search_documents

router = APIRouter(prefix="/search", tags=["search"])


class DocumentSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    include_deprecated: bool = False
    account_id: str | None = None
    doc_types: list[str] | None = None
    doc_id: str | None = None
    top_k: int = Field(default=6, ge=1, le=20)


def _run_search(
    *,
    query: str,
    user: AuthUser,
    include_deprecated: bool,
    account_id: str | None,
    doc_types: list[str] | None = None,
    doc_id: str | None = None,
    top_k: int = 6,
) -> dict:
    try:
        scoped_account, scoped_deprecated = scope_document_search(
            user,
            requested_account_id=account_id,
            include_deprecated=include_deprecated,
        )
        chunks = search_documents(
            query,
            include_deprecated=scoped_deprecated,
            account_id=scoped_account,
            doc_types=doc_types,
            doc_id=doc_id,
            top_k=top_k,
        )
    except ACLError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Search failed: {exc}") from exc

    return {
        "query": query,
        "count": len(chunks),
        "scoped_account_id": scoped_account,
        "chunks": chunks,
    }


@router.post("/documents")
def search_documents_post(
    body: DocumentSearchRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    return _run_search(
        query=body.query,
        user=user,
        include_deprecated=body.include_deprecated,
        account_id=body.account_id,
        doc_types=body.doc_types,
        doc_id=body.doc_id,
        top_k=body.top_k,
    )


@router.get("/documents")
def search_documents_get(
    q: str = Query(..., min_length=1),
    include_deprecated: bool = False,
    account_id: str | None = None,
    top_k: int = Query(default=6, ge=1, le=20),
    user: AuthUser = Depends(get_current_user),
) -> dict:
    return _run_search(
        query=q,
        user=user,
        include_deprecated=include_deprecated,
        account_id=account_id,
        top_k=top_k,
    )
