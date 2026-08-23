from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.schema import create_all_tables
from app.routes.actions import router as actions_router
from app.routes.auth import router as auth_router
from app.routes.chat import router as chat_router
from app.routes.data import router as data_router
from app.routes.search import router as search_router
from app.routes.tools import router as tools_router
from app.timeutil import get_snapshot_at

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="ParcelPilot AI support agent API — Groq LLM + Gemini embeddings + PostgreSQL",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(data_router)
app.include_router(search_router)
app.include_router(tools_router)
app.include_router(actions_router)
app.include_router(chat_router)


@app.on_event("startup")
def ensure_tables() -> None:
    """Create action/audit tables if missing (safe no-op if already present)."""
    try:
        create_all_tables()
    except Exception:
        # DB may be unreachable at boot; routes will surface 503 later.
        pass


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "llm_provider": "groq",
        "embedding_provider": "gemini",
        "data_path": str(settings.resolved_data_path),
        "snapshot_at": get_snapshot_at().isoformat(),
    }


@app.get("/")
def root() -> dict:
    return {
        "message": "ParcelPilot Assist API",
        "docs": "/docs",
        "health": "/health",
    }
