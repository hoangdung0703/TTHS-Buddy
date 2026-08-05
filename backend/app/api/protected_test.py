from fastapi import APIRouter, Depends, Request

from app.core.rate_limit import DEFAULT_RATE_LIMIT, limiter
from app.core.security import require_supabase_user
from app.models.auth import AuthUser, ProtectedTestResponse

router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/protected-test", response_model=ProtectedTestResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def protected_test(
    request: Request, current_user: AuthUser = Depends(require_supabase_user)
) -> ProtectedTestResponse:
    return ProtectedTestResponse(user=current_user)
