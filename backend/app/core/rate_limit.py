"""Rate limiting keyed by authenticated user, not IP - see requirements.md security audit
mục 4: many users can share one IP (school/office NAT), so per-IP limiting would either
under-limit a shared IP or over-limit innocent users behind it. The key is derived by decoding
the same JWT require_supabase_user verifies, independently here because slowapi's global
default_limits run in ASGI middleware, BEFORE FastAPI resolves route dependencies - so
request.state.user (set inside require_supabase_user) isn't available yet at that point.
Falls back to client IP only for requests with no valid token, which every route except
/api/health rejects with 401 anyway.
"""
from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.core.security import _extract_bearer_token, verify_supabase_jwt


def _rate_limit_key(request: Request) -> str:
    try:
        token = _extract_bearer_token(request.headers.get("Authorization"))
        user = verify_supabase_jwt(token, get_settings())
        return f"user:{user.user_id}"
    except Exception:
        return f"ip:{get_remote_address(request)}"


# Generic ceiling for every other route (mostly GET reads) - loose enough to never bother a real
# user, tight enough to blunt naive scripted spam. Write routes that call an LLM (chat query,
# essay submit) get a much stricter override. Applied via an explicit @limiter.limit(...) on
# EVERY route (including DEFAULT_RATE_LIMIT ones) rather than Limiter's default_limits - see
# add_rate_limit_middleware's docstring in core/middleware.py for why default_limits silently
# doesn't work on this FastAPI version.
DEFAULT_RATE_LIMIT = "60/minute"
LLM_ROUTE_RATE_LIMIT = "10/minute"

limiter = Limiter(key_func=_rate_limit_key)
