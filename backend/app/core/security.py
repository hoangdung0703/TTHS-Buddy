from __future__ import annotations

from typing import Any

import jwt
from jwt import PyJWKClient
from fastapi import Depends, Header, HTTPException, Request, status
from jwt import ExpiredSignatureError, InvalidTokenError

from app.core.config import Settings, get_settings
from app.models.auth import AuthUser


def _extract_bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header format")

    return token.strip()


def verify_supabase_jwt(token: str, settings: Settings) -> AuthUser:
    header = jwt.get_unverified_header(token)
    algorithm = str(header.get("alg") or "")

    try:
        if algorithm == "ES256":
            jwks_url = f"{str(settings.supabase_url).rstrip('/')}/auth/v1/.well-known/jwks.json"
            jwk_client = PyJWKClient(jwks_url)
            signing_key = jwk_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256"],
                issuer=f"{str(settings.supabase_url).rstrip('/')}/auth/v1",
                options={"verify_aud": False},
            )
        else:
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
    except ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from exc
    except InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user_id = str(payload.get("sub") or "")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing subject claim")

    email_value = payload.get("email")
    email = str(email_value) if email_value is not None else None

    return AuthUser(user_id=user_id, email=email, claims=payload)


async def require_supabase_user(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    settings: Settings = Depends(get_settings),
) -> AuthUser:
    token = _extract_bearer_token(authorization)
    user = verify_supabase_jwt(token, settings)
    request.state.user = user
    return user

