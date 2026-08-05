import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import ValidationError

from app.api.chat import router as chat_router
from app.api.dashboard import router as dashboard_router
from app.api.essay import router as essay_router
from app.api.health import router as health_router
from app.api.legal import router as legal_router
from app.api.protected_test import router as protected_test_router
from app.api.quiz import router as quiz_router
from app.core.config import (
    create_qdrant_client,
    create_supabase_client,
    ensure_qdrant_collection,
    get_settings,
    verify_supabase_connection,
)
from app.core.logging import configure_logging, get_logger
from app.core.middleware import add_cors_middleware, add_rate_limit_middleware, register_exception_handlers

configure_logging(os.getenv("ENVIRONMENT", "development"))
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        settings = get_settings()
    except ValidationError:
        logger.exception("Environment validation failed. Check required variables in .env.")
        raise

    configure_logging(settings.environment)

    logger.info("Starting TTHS Buddy backend in %s mode", settings.environment)

    supabase_client = create_supabase_client(settings)
    qdrant_client = create_qdrant_client(settings)

    app.state.settings = settings
    app.state.supabase_client = supabase_client
    app.state.qdrant_client = qdrant_client

    logger.info("Checking Supabase connection...")
    await verify_supabase_connection(supabase_client)
    logger.info("Supabase connection successful.")

    logger.info("Checking Qdrant connection and collection...")
    await ensure_qdrant_collection(qdrant_client, settings.qdrant_collection)
    logger.info("Qdrant connection successful.")

    yield


def create_app() -> FastAPI:
    app = FastAPI(title="TTHS Buddy API", version="0.1.0", lifespan=lifespan)
    add_cors_middleware(app)
    add_rate_limit_middleware(app)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(protected_test_router)
    app.include_router(chat_router)
    app.include_router(quiz_router)
    app.include_router(essay_router)
    app.include_router(dashboard_router)
    app.include_router(legal_router)
    return app


app = create_app()
