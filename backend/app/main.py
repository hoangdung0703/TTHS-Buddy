import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import ValidationError

from app.api.chat import router as chat_router
from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.api.legal import router as legal_router
from app.api.notes import router as notes_router
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
from app.core.security import prefetch_jwks

configure_logging(os.getenv("ENVIRONMENT", "development"))
logger = get_logger(__name__)

JWKS_PREFETCH_TIMEOUT_SECONDS = 5.0


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

    # Load the Supabase signing keys now rather than on the first authenticated request, which on a
    # cold-started instance is a student who has already waited ~45s. Unlike the two checks above,
    # this is an optimisation and NOT a precondition: if it fails, verification still fetches the
    # keys on demand exactly as it did before this existed, so a failure here is logged and boot
    # continues. Bounded so a slow or unreachable JWKS endpoint cannot stretch a cold start that
    # students are already waiting through - PyJWKClient's own urlopen timeout is 30s. If the bound
    # trips, the worker thread is not cancelled (threads cannot be); it either finishes and fills
    # the cache anyway, or hits that 30s timeout and exits on its own, holding one executor slot at
    # most until then.
    logger.info("Pre-fetching Supabase JWKS...")
    try:
        key_count = await asyncio.wait_for(
            asyncio.to_thread(prefetch_jwks, settings), timeout=JWKS_PREFETCH_TIMEOUT_SECONDS
        )
        logger.info("Supabase JWKS pre-fetched (%d key(s)).", key_count)
    except Exception:
        logger.warning(
            "Supabase JWKS pre-fetch failed - continuing startup; the first authenticated request "
            "will fetch the keys on demand.", exc_info=True
        )

    yield


def create_app() -> FastAPI:
    # See Settings.enable_api_docs. FastAPI serves no route at all for a None URL, so with the
    # switch off these paths are plain 404s, indistinguishable from any other unknown path.
    docs_enabled = get_settings().enable_api_docs
    app = FastAPI(
        title="TTHS Buddy API", version="0.1.0", lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    add_cors_middleware(app)
    add_rate_limit_middleware(app)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(protected_test_router)
    app.include_router(chat_router)
    app.include_router(quiz_router)
    app.include_router(dashboard_router)
    app.include_router(legal_router)
    app.include_router(notes_router)
    return app


app = create_app()
