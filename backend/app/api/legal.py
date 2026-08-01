from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.security import require_supabase_user
from app.models.auth import AuthUser
from app.models.legal import LegalArticleResponse
from app.services.legal_service import get_dieu_full_text

router = APIRouter(prefix="/api/legal", tags=["legal"])


@router.get("/articles/{dieu_number}", response_model=LegalArticleResponse)
async def get_legal_article(
    dieu_number: str,
    request: Request,
    law_version: str = Query(..., description="Disambiguates dieu_number across documents that share it"),
    current_user: AuthUser = Depends(require_supabase_user),
) -> LegalArticleResponse:
    """Feature nhỏ - Xem toàn văn Điều luật từ citation pill (see requirements.md). law_version
    is required, not optional: the corpus has multiple documents (BLTTHS/BLHS/Nghi dinh 250/2
    Thong tu lien tich) that reuse the same dieu_number, so dieu_number alone can't identify one
    article - see LAW_NAME_TO_SOURCE_DOCUMENT in rag_service.py for the same recurring issue."""
    qdrant_client = request.app.state.qdrant_client
    article = get_dieu_full_text(qdrant_client, request.app.state.settings.qdrant_collection, dieu_number, law_version)
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return LegalArticleResponse(**article)
