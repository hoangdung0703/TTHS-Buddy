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

    # Standard practice for verifying a token issued by a SEPARATE system (Supabase Auth) against
    # this server's own clock: some tolerance for clock skew between the two machines is expected
    # in any distributed deployment (NTP drift, container/VM clock jumps, etc.), not a hypothetical
    # edge case. Without it, PyJWT's default zero-leeway "iat must not be in the future" check
    # (jwt/api_jwt.py _validate_iat: `if iat > now + leeway: raise ImmatureSignatureError`) rejects
    # a perfectly valid, freshly-issued token whenever this server's clock is even a few seconds
    # behind Supabase's - hitting hardest exactly for a brand-new account's very first request,
    # since that is the one request guaranteed to happen right after the token's iat. Confirmed by
    # direct reproduction: a newly created account signing in and immediately calling a protected
    # route failed with ImmatureSignatureError, not any application bug. 30s comfortably covers
    # realistic clock drift between two well-maintained, NTP-synced servers without weakening the
    # exp check (which still runs with the same modest leeway, not disabled).
    JWT_CLOCK_SKEW_LEEWAY_SECONDS = 30

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
                leeway=JWT_CLOCK_SKEW_LEEWAY_SECONDS,
            )
        else:
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
                leeway=JWT_CLOCK_SKEW_LEEWAY_SECONDS,
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

