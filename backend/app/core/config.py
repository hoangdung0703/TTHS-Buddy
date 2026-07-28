from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from supabase import Client, create_client

from app.core.logging import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_VECTOR_SIZE = 768


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
    qdrant_url: AnyHttpUrl = Field(alias="QDRANT_URL")
    qdrant_api_key: str = Field(alias="QDRANT_API_KEY", min_length=1)
    qdrant_collection: str = Field(alias="QDRANT_COLLECTION", min_length=1)

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


def create_supabase_client(settings: Settings) -> Client:
    return create_client(str(settings.supabase_url), settings.supabase_service_role_key)


def create_qdrant_client(settings: Settings) -> QdrantClient:
    return QdrantClient(url=str(settings.qdrant_url), api_key=settings.qdrant_api_key, check_compatibility=False)


async def verify_supabase_connection(client: Client) -> None:
    def _check_connection() -> None:
        client.auth.admin.list_users(page=1, per_page=1)

    await asyncio.to_thread(_check_connection)


async def ensure_qdrant_collection(client: QdrantClient, collection_name: str) -> None:
    def _ensure_collection() -> None:
        if client.collection_exists(collection_name):
            return

        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=DEFAULT_VECTOR_SIZE, distance=Distance.COSINE)
        )

    await asyncio.to_thread(_ensure_collection)
