"""Regression test: a brand-new account's very first API call, immediately after sign-in, must
not be rejected due to clock skew between this backend and Supabase Auth's server.

Background (see requirements.md): backend/app/core/security.py's verify_supabase_jwt() used to
call jwt.decode() with no `leeway`, so PyJWT's default zero-tolerance "iat must not be in the
future" check (jwt/api_jwt.py _validate_iat) rejected an otherwise-valid, freshly-issued token
whenever this server's clock was even a few seconds behind Supabase's - hitting hardest for a
brand-new account, since signup+first-request is the one flow guaranteed to happen right at the
token's iat. This is a REAL bug affecting real users (any two independently-clocked servers can
drift by a few seconds - that's exactly why "leeway" is standard JWT-verification practice), not
a test-environment-only artifact. Fixed by adding a 30s leeway to both the ES256 and HS256
jwt.decode() branches.

Usage:
    uvicorn app.main:app --reload &          # from backend/, in another terminal
    python backend/evaluation/test_jwt_iat_leeway.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import create_supabase_client, get_settings  # noqa: E402
from supabase import create_client  # noqa: E402

API_BASE = "http://localhost:8000"
TEST_PASSWORD = "TestPass123!"
TEST_EMAIL = "ttths-test-iat-leeway@example.com"

_ROOT_ENV = dotenv_values(PROJECT_ROOT / ".env")

DASHBOARD_ROUTES = ("/api/dashboard/stats", "/api/dashboard/keywords-yesterday", "/api/dashboard/weak-topics")

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {message}")
    if not condition:
        failures.append(message)


def main() -> int:
    settings = get_settings()
    admin_client = create_supabase_client(settings)

    print("=== Setup: create 1 disposable real Supabase account ===")
    created = admin_client.auth.admin.create_user(
        {"email": TEST_EMAIL, "password": TEST_PASSWORD, "email_confirm": True}
    )
    user_id = created.user.id
    print(f"  user = {user_id}")

    try:
        print("\n=== Sign in, then call 3 protected routes IMMEDIATELY (no delay) ===")
        anon_client = create_client(str(settings.supabase_url), _ROOT_ENV["NEXT_PUBLIC_SUPABASE_ANON_KEY"])
        session = anon_client.auth.sign_in_with_password({"email": TEST_EMAIL, "password": TEST_PASSWORD})
        token = session.session.access_token

        with httpx.Client(timeout=10) as client:
            for route in DASHBOARD_ROUTES:
                response = client.get(f"{API_BASE}{route}", headers={"Authorization": f"Bearer {token}"})
                check(response.status_code == 200,
                      f"{route} immediately after sign-in should be 200, got {response.status_code} "
                      f"({response.text[:150]!r}) - a 401 here means the iat-leeway regression is back")
    finally:
        print("\n=== Teardown ===")
        try:
            admin_client.table("chat_query_logs").delete().eq("user_id", user_id).execute()
            admin_client.auth.admin.delete_user(user_id)
        except Exception as exc:
            print(f"  (cleanup warning: {exc})")

    print(f"\n{'=' * 60}")
    if failures:
        print(f"FAIL - {len(failures)} check(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("ALL JWT IAT-LEEWAY TESTS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
