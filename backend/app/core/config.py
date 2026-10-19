from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path

import httpx
from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams
from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

from app.core.logging import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_VECTOR_SIZE = 768
QUESTION_BANK_PATH = PROJECT_ROOT / "ingestion" / "question_bank.json"
CHAT_SUGGESTIONS_SEED_PATH = PROJECT_ROOT / "ingestion" / "chat_suggestions_seed.json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    environment: str = Field(alias="ENVIRONMENT")
    supabase_url: AnyHttpUrl = Field(alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(alias="SUPABASE_SERVICE_ROLE_KEY", min_length=1)
    supabase_jwt_secret: str = Field(alias="SUPABASE_JWT_SECRET", min_length=1)
    google_api_key: str = Field(alias="GOOGLE_API_KEY", min_length=1)
    gemini_chat_model: str = Field(alias="GEMINI_CHAT_MODEL", min_length=1)
    gemini_embedding_model: str = Field(alias="GEMINI_EMBEDDING_MODEL", min_length=1)
    # requirements.md "Tăng impact LLM cho câu hỏi dài/phức tạp": stronger model used only for the
    # final generation call on long/tình huống questions (is_long_question, see rag_service.py's
    # LONG_QUESTION_CHAR_THRESHOLD) - unset falls back to gemini_chat_model so existing deployments
    # keep working unchanged until this is explicitly configured.
    gemini_chat_model_complex: str | None = Field(default=None, alias="GEMINI_CHAT_MODEL_COMPLEX")
    qdrant_url: AnyHttpUrl = Field(alias="QDRANT_URL")
    qdrant_api_key: str = Field(alias="QDRANT_API_KEY", min_length=1)
    qdrant_collection: str = Field(alias="QDRANT_COLLECTION", min_length=1)
    cors_allowed_origins: str = Field(default="http://localhost:3000", alias="CORS_ALLOWED_ORIGINS")
    # Interactive API docs (/docs, /redoc) and the schema behind them (/openapi.json). OFF unless
    # explicitly enabled, in every environment - deliberately its own switch and not derived from
    # ENVIRONMENT, so that no environment value can expose them by accident. Meant for local
    # development only; not set on Render. Before 2026-10-18 all three were always on in production,
    # publishing every route, parameter and response shape of the API.
    enable_api_docs: bool = Field(default=False, alias="ENABLE_API_DOCS")
    # "Phiên tòa giả định": the court name printed on simulated hearings and records. Left as a
    # visible placeholder until the legal team confirms the post-2025 naming (see
    # docs/phien-toa-gia-dinh/THIET-KE.md Mục 9); unset keeps that placeholder.
    trial_court_name: str | None = Field(default=None, alias="TRIAL_COURT_NAME")

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def resolved_complex_chat_model(self) -> str:
        return self.gemini_chat_model_complex or self.gemini_chat_model

    @field_validator("environment")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed_environments = {"development", "test", "production"}

        if normalized not in allowed_environments:
            raise ValueError("ENVIRONMENT must be development, test, or production")

        return normalized


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# HTTP/1.1 connection pool for the shared Supabase client - see create_supabase_client.
#
# max_connections caps simultaneous in-flight Supabase requests per worker process; a request
# beyond it waits for a free connection (up to the timeout) instead of failing. 32 matches the
# ceiling on what one process can actually have in flight: the calls run on asyncio's default
# thread pool, which Python caps at min(32, cpu_count + 4) threads - so a smaller pool could
# become a queue a busy worker never needed, and a larger one would never be filled. Each of the
# two gunicorn workers (-w 2) gets its own pool.
#
# max_keepalive_connections keeps a handful of connections open between requests so a typical
# request (one or two reads) reuses a warm connection instead of paying a fresh TLS handshake to
# Supabase's Cloudflare edge. 8 covers the normal steady state - a chat turn's two concurrent
# reads, plus the sidebar and dashboard reads that a page load fires at the same time - without
# holding idle sockets open that would only be closed by keepalive expiry anyway.
SUPABASE_HTTP_LIMITS = httpx.Limits(max_connections=32, max_keepalive_connections=8)
# postgrest-py's own defaults for the client it would otherwise build itself. They are restated
# because a caller-supplied client replaces that client wholesale, defaults included.
SUPABASE_HTTP_TIMEOUT_SECONDS = 120.0


def create_supabase_client(settings: Settings) -> Client:
    """One Supabase client per process, shared by every request - over HTTP/1.1, NOT HTTP/2.

    postgrest-py builds its own httpx client with http2=True, and this one instance is used from
    many threads at once: every Supabase call runs in asyncio's thread pool, the chat route runs
    two of them concurrently by design (api/chat.py's asyncio.gather of the two history reads), and
    two students' requests overlap whenever they happen to. Over HTTP/2 all of those share ONE
    connection, and httpcore's synchronous HTTP/2 path is not safe for that: two threads encoding
    request headers at the same moment corrupt the shared HPACK compression state. Observed in a
    test run on 2026-10-17 as `ProtocolError("Received pseudo-header in trailer ...")`, after which
    Supabase closed the connection with COMPRESSION_ERROR and both in-flight reads failed together.
    The chat route's history readers turned such failures into an empty history, so a follow-up
    question was silently answered without its conversation.

    Over HTTP/1.1 the pool hands each concurrent request its own connection; there is no shared
    per-connection state for threads to race on. The same client is also what supabase-py's auth
    and storage clients use, so they move to HTTP/1.1 with it.
    """
    http_client = httpx.Client(
        http2=False,
        limits=SUPABASE_HTTP_LIMITS,
        timeout=SUPABASE_HTTP_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    return create_client(
        str(settings.supabase_url), settings.supabase_service_role_key,
        options=SyncClientOptions(httpx_client=http_client),
    )


def create_qdrant_client(settings: Settings) -> QdrantClient:
    return QdrantClient(url=str(settings.qdrant_url), api_key=settings.qdrant_api_key, check_compatibility=False)


async def verify_supabase_connection(client: Client) -> None:
    def _check_connection() -> None:
        client.auth.admin.list_users(page=1, per_page=1)

    await asyncio.to_thread(_check_connection)


# Every payload field rag_service.py filters on needs a keyword index, or Qdrant rejects the
# filtered query with a 400 - discovered incrementally as each new filter was added
# (source_type/dieu_number in Phase 4, source_document in Phase 6, law_version in the
# GET /api/legal/articles/{dieu_number} feature). Kept in sync with ingestion/vector_store.py's
# FILTERABLE_PAYLOAD_FIELDS.
FILTERABLE_PAYLOAD_FIELDS = ("source_type", "dieu_number", "source_document", "law_version")

# chunk_index needs a separate INTEGER (not KEYWORD) index - rag_service's academic_reference
# neighbor expansion range-filters on it (Range(gte=..., lte=...)), which Qdrant only accepts
# against a numeric-typed index. Kept in sync with ingestion/vector_store.py.
FILTERABLE_INTEGER_PAYLOAD_FIELDS = ("chunk_index",)


async def ensure_qdrant_collection(client: QdrantClient, collection_name: str) -> None:
    def _ensure_collection() -> None:
        if not client.collection_exists(collection_name):
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=DEFAULT_VECTOR_SIZE, distance=Distance.COSINE)
            )

        for field_name in FILTERABLE_PAYLOAD_FIELDS:
            client.create_payload_index(collection_name, field_name=field_name,
                                         field_schema=PayloadSchemaType.KEYWORD)
        for field_name in FILTERABLE_INTEGER_PAYLOAD_FIELDS:
            client.create_payload_index(collection_name, field_name=field_name,
                                         field_schema=PayloadSchemaType.INTEGER)

    await asyncio.to_thread(_ensure_collection)
