from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.models.errors import ErrorResponse


def add_cors_middleware(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def add_rate_limit_middleware(app: FastAPI) -> None:
    # NOT SlowAPIMiddleware: verified by hand that it silently no-ops on this FastAPI version
    # (0.140+'s app.routes returns lazy `_IncludedRouter` wrappers instead of flat Starlette
    # Route objects, so slowapi's own route lookup - which expects `route.matches()` - never
    # finds a handler and treats every request as exempt). Confirmed with a 70-request burst
    # against an undecorated GET route: all 70 returned 200, zero were limited. Every rate-limited
    # route below is therefore decorated directly with @limiter.limit(...) - see chat.py,
    # quiz.py, essay.py, dashboard.py, legal.py - which does NOT depend on this middleware at
    # all (the decorator's own wrapper calls the limiter check directly). app.state.limiter is
    # still set here since it's what those decorators' underlying Limiter instance is attached
    # to for FastAPI app introspection.
    app.state.limiter = limiter


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_exceeded_handler(_: Request, exc: RateLimitExceeded) -> JSONResponse:
        payload = ErrorResponse(
            error={"code": "rate_limit_exceeded", "message": f"Too many requests - limit is {exc.detail}."}
        )
        return JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS, content=payload.model_dump())

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        payload = ErrorResponse(error={"code": "http_error", "message": str(exc.detail)})
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        payload = ErrorResponse(error={"code": "validation_error", "message": "Request validation failed"})
        return JSONResponse(status_code=422, content=payload.model_dump())

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        from app.core.logging import get_logger

        logger = get_logger(__name__)
        logger.exception("Unhandled server error")
        payload = ErrorResponse(error={"code": "internal_server_error", "message": "Internal server error"})
        return JSONResponse(status_code=500, content=payload.model_dump())
