from __future__ import annotations

import hmac
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient
from fastapi import Depends, Header, HTTPException, Request, status
from jwt import ExpiredSignatureError, InvalidTokenError, PyJWKClientError

from app.core.config import Settings, get_settings
from app.models.auth import AuthUser


@lru_cache(maxsize=4)
def _jwk_client(jwks_url: str) -> PyJWKClient:
    """One PyJWKClient per JWKS URL, for the life of the process.

    A fresh PyJWKClient was being constructed on every verification, which made its cache useless:
    each call re-fetched the JWK set from Supabase over the network. Measured at ~0.30s per
    verification, and the chat route verifies the same token TWICE (once for the rate-limit key,
    once for the auth dependency), so roughly 0.6s of every authenticated request was spent
    re-downloading keys that never change.

    cache_jwk_set and lifespan are PyJWT 2.13's defaults (True / 300s) and are passed explicitly
    so a future default change cannot silently turn the cache off again. Key rotation still works:
    the set is re-fetched when the 300s lifespan expires, and get_signing_key additionally forces
    one refresh whenever a kid is not found in the cached set.

    maxsize=4, not 1: the key is the URL, and keeping a couple of entries costs nothing while
    letting tests point at a different issuer without evicting the production client.
    """
    return PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=300)


# request.state keys for the single-verification-per-request cache. Private names so nothing else
# is tempted to treat them as public API; read/written only through verify_supabase_jwt_for_request.
_STATE_TOKEN = "_verified_auth_token"
_STATE_USER = "_verified_auth_user"


def _extract_bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header format")

    return token.strip()


def verify_supabase_jwt(token: str, settings: Settings) -> AuthUser:
    # Inside the try, not before it: get_unverified_header raises DecodeError ("Not enough
    # segments") on anything that is not a well-formed JWT, and DecodeError is an
    # InvalidTokenError. Parsing out here meant a garbage Authorization header escaped as an
    # unhandled exception and became a 500 - a client sending nonsense was told the server had
    # failed, and the 500 rate would be driven by malformed input rather than by real faults.
    try:
        algorithm = str(jwt.get_unverified_header(token).get("alg") or "")
    except InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

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
            signing_key = _jwk_client(jwks_url).get_signing_key_from_jwt(token)
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
    # PyJWKClientError is NOT a subclass of InvalidTokenError (verified against PyJWT 2.13.0), so
    # before this clause existed a token carrying an unknown `kid` escaped as an unhandled
    # exception and became a 500 instead of a 401 - an auth failure reported as a server fault.
    # PyJWT refreshes the JWK set once before giving up, so a genuinely rotated key still verifies;
    # only a kid that is absent even from the freshly fetched set reaches here.
    except PyJWKClientError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    except InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user_id = str(payload.get("sub") or "")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing subject claim")

    email_value = payload.get("email")
    email = str(email_value) if email_value is not None else None

    return AuthUser(user_id=user_id, email=email, claims=payload)


def verify_supabase_jwt_for_request(request: Request, token: str, settings: Settings) -> AuthUser:
    """verify_supabase_jwt, but at most once per request.

    The chat route verifies the same token twice - the rate-limit key function needs the user id
    before the route runs, and require_supabase_user needs the full AuthUser - which doubled the
    cost of an already-expensive ES256 verification. Whichever runs first stores its result on
    request.state and the second call reuses it.

    Only ever reused for the byte-identical token that produced it: the comparison is against the
    exact token string, so this can never hand one request's identity to a different token. A
    failed verification raises and caches nothing, so an invalid token is re-rejected rather than
    remembered. Scope is one request, so there is no cross-request state to go stale.
    """
    cached_token = getattr(request.state, _STATE_TOKEN, None)
    cached_user = getattr(request.state, _STATE_USER, None)
    if (
        cached_user is not None
        and isinstance(cached_token, str)
        and hmac.compare_digest(cached_token, token)
    ):
        return cached_user

    user = verify_supabase_jwt(token, settings)
    setattr(request.state, _STATE_TOKEN, token)
    setattr(request.state, _STATE_USER, user)
    return user


async def require_supabase_user(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    settings: Settings = Depends(get_settings),
) -> AuthUser:
    token = _extract_bearer_token(authorization)
    user = verify_supabase_jwt_for_request(request, token, settings)
    request.state.user = user
    return user

