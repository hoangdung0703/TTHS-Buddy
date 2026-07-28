from fastapi import APIRouter, Depends

from app.core.security import require_supabase_user
from app.models.auth import AuthUser, ProtectedTestResponse

router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/protected-test", response_model=ProtectedTestResponse)
async def protected_test(current_user: AuthUser = Depends(require_supabase_user)) -> ProtectedTestResponse:
    return ProtectedTestResponse(user=current_user)
