from __future__ import annotations

from pydantic import BaseModel


class LegalArticleResponse(BaseModel):
    dieu_number: str
    dieu_title: str | None
    law_version: str | None
    source_document: str
    full_text: str
