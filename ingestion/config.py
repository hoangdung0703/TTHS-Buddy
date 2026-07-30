"""Environment configuration for ingestion scripts. Reads the root .env, independent
from backend/app/core/config.py since ingestion runs standalone (per requirements.md)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DOCUMENTS_DIR = PROJECT_ROOT / "ingestion" / "raw_documents"
CHUNKS_OUTPUT_PATH = PROJECT_ROOT / "ingestion" / "chunks.json"
QUESTION_BANK_OUTPUT_PATH = PROJECT_ROOT / "ingestion" / "question_bank.json"


class IngestionSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    google_api_key: str = Field(alias="GOOGLE_API_KEY", min_length=1)
    gemini_chat_model: str = Field(alias="GEMINI_CHAT_MODEL", min_length=1)
    gemini_embedding_model: str = Field(alias="GEMINI_EMBEDDING_MODEL", min_length=1)
    qdrant_url: str = Field(alias="QDRANT_URL", min_length=1)
    qdrant_api_key: str = Field(alias="QDRANT_API_KEY", min_length=1)
    qdrant_collection: str = Field(alias="QDRANT_COLLECTION", min_length=1)


@lru_cache(maxsize=1)
def get_ingestion_settings() -> IngestionSettings:
    return IngestionSettings()
