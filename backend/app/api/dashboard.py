from fastapi import APIRouter, Depends, Request

from app.core.rate_limit import DEFAULT_RATE_LIMIT, limiter
from app.core.security import require_supabase_user
from app.models.auth import AuthUser
from app.models.dashboard import (
    DashboardStats,
    KeywordsYesterdayResponse,
    KeywordYesterday,
    WeakTopic,
    WeakTopicsResponse,
)
from app.services.dashboard_service import get_dashboard_stats, get_keywords_yesterday, get_weak_topics

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/keywords-yesterday", response_model=KeywordsYesterdayResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def keywords_yesterday(
    request: Request,
    current_user: AuthUser = Depends(require_supabase_user),
) -> KeywordsYesterdayResponse:
    keywords = get_keywords_yesterday(request.app.state.supabase_client, current_user.user_id)
    return KeywordsYesterdayResponse(keywords=[KeywordYesterday(**k) for k in keywords])


@router.get("/weak-topics", response_model=WeakTopicsResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def weak_topics(
    request: Request,
    current_user: AuthUser = Depends(require_supabase_user),
) -> WeakTopicsResponse:
    topics = get_weak_topics(request.app.state.supabase_client, current_user.user_id)
    return WeakTopicsResponse(weak_topics=[WeakTopic(**t) for t in topics])


@router.get("/stats", response_model=DashboardStats)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def stats(
    request: Request,
    current_user: AuthUser = Depends(require_supabase_user),
) -> DashboardStats:
    return DashboardStats(**get_dashboard_stats(request.app.state.supabase_client, current_user.user_id))
