from typing import Any

from app.core.config import Settings


def verify_supabase_jwt(token: str, settings: Settings) -> dict[str, Any]:
    raise NotImplementedError("Supabase JWT verification will be added in Phase 2.")
