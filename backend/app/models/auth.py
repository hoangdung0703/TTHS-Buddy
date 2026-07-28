from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class AuthUser(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_id: str
    email: str | None
    claims: dict[str, Any]


class ProtectedTestResponse(BaseModel):
    user: AuthUser
