"""Phase 4 Extension 2 - conversation history: real E2E + security test against a running
backend (uvicorn on :8000 by default) with 2 disposable real Supabase Auth accounts.

Usage:
    uvicorn app.main:app --reload &          # from backend/, in another terminal
    python backend/evaluation/test_conversation_history_e2e.py

Creates 2 real throwaway Supabase Auth users via the Admin API, signs in as each (real password
grant - real JWTs issued by Supabase, not self-signed), exercises the full flow through the real
SSE /api/chat/query endpoint + the new GET /api/chat/conversations[/{id}] routes, then deletes
both accounts and their chat_query_logs rows on the way out (best-effort, even on failure).

Covers:
  - conversation_id stays stable across turns of the same conversation, and a fresh "no
    conversation_id" ask always gets a NEW one (never reuses/guesses).
  - GET /api/chat/conversations groups correctly and sorts most-recently-updated first.
  - GET /api/chat/conversations/{id} returns the full, correctly-ordered turn history.
  - SECURITY: a different real user, with a real token, using the EXACT correct conversation_id
    of another user's real conversation, gets 404 (not 200, not 403 - 404 so existence is never
    confirmed to a caller who doesn't own it). Also checks the list endpoint doesn't leak
    cross-user, and that no Authorization header is a clean 401.
"""
from __future__ import annotations

import json
import sys
import time
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
USER_A_EMAIL = "ttths-test-conv-a@example.com"
USER_B_EMAIL = "ttths-test-conv-b@example.com"

_ROOT_ENV = dotenv_values(PROJECT_ROOT / ".env")

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {message}")
    if not condition:
        failures.append(message)


def sign_in(email: str, password: str) -> str:
    settings = get_settings()
    anon_client = create_client(str(settings.supabase_url), _ROOT_ENV["NEXT_PUBLIC_SUPABASE_ANON_KEY"])
    result = anon_client.auth.sign_in_with_password({"email": email, "password": password})
    return result.session.access_token


def ask(token: str, question: str, conversation_id: str | None) -> tuple[str, str]:
    """Sends one question via the real SSE endpoint, returns (answer_text, conversation_id)."""
    body: dict[str, str] = {"question": question}
    if conversation_id:
        body["conversation_id"] = conversation_id

    answer_parts: list[str] = []
    returned_conversation_id = conversation_id or ""
    with httpx.Client(timeout=60) as client:
        with client.stream(
            "POST", f"{API_BASE}/api/chat/query", json=body, headers={"Authorization": f"Bearer {token}"}
        ) as response:
            response.raise_for_status()
            current_event = None
            for line in response.iter_lines():
                if line.startswith("event:"):
                    current_event = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    data = json.loads(line[len("data:"):].strip())
                    if current_event == "citations":
                        returned_conversation_id = data["conversation_id"]
                    elif current_event == "answer_delta":
                        answer_parts.append(data["delta"])
    return "".join(answer_parts), returned_conversation_id


def setup_test_user(admin_client, email: str) -> str:
    created = admin_client.auth.admin.create_user({"email": email, "password": TEST_PASSWORD, "email_confirm": True})
    return created.user.id


def teardown_test_user(admin_client, user_id: str) -> None:
    try:
        admin_client.table("chat_query_logs").delete().eq("user_id", user_id).execute()
        admin_client.auth.admin.delete_user(user_id)
    except Exception as exc:  # best-effort cleanup, never mask the real test result
        print(f"  (cleanup warning: failed to remove test user {user_id}: {exc})")


def main() -> int:
    settings = get_settings()
    admin_client = create_supabase_client(settings)

    print("=== Setup: create 2 disposable real Supabase accounts ===")
    user_a_id = setup_test_user(admin_client, USER_A_EMAIL)
    user_b_id = setup_test_user(admin_client, USER_B_EMAIL)
    print(f"  user A = {user_a_id}, user B = {user_b_id}")

    try:
        token_a = sign_in(USER_A_EMAIL, TEST_PASSWORD)
        token_b = sign_in(USER_B_EMAIL, TEST_PASSWORD)
        # PyJWT's iat check has zero leeway - calling the API within ~1-2s of sign-in can trip
        # ImmatureSignatureError from ordinary clock/network jitter between this machine and
        # Supabase's auth server. Real users never hit this (browser login has human-scale delay
        # before the first API call); this sleep only compensates for a synchronous test script.
        time.sleep(3)

        print("\n=== User A: ask 2 questions in the same conversation ===")
        answer1, conv_a = ask(token_a, "Điều 8 Bộ luật TTHS quy định gì?", None)
        check(len(conv_a) > 0, "conversation_id should be assigned on first question")
        _answer2, conv_a_again = ask(token_a, "Còn Điều 9 thì sao?", conv_a)
        check(conv_a_again == conv_a, "second question in same conversation should keep the same conversation_id")
        time.sleep(1)  # let both inserts land before reading back

        print("\n=== User A: ask 1 question in a SEPARATE (new) conversation ===")
        _answer3, conv_a2 = ask(token_a, "Thời hạn tạm giam tối đa là bao lâu?", None)
        check(conv_a2 != conv_a, "a fresh 'new conversation' ask (no conversation_id) must get a DIFFERENT id")
        time.sleep(1)

        print("\n=== GET /api/chat/conversations (User A) - should list both, most recent first ===")
        with httpx.Client(timeout=30) as client:
            list_resp = client.get(f"{API_BASE}/api/chat/conversations", headers={"Authorization": f"Bearer {token_a}"})
        check(list_resp.status_code == 200, f"list conversations should be 200, got {list_resp.status_code}")
        ids_a = [c["conversation_id"] for c in list_resp.json()["conversations"]]
        check(conv_a in ids_a, "first conversation should appear in User A's list")
        check(conv_a2 in ids_a, "second (new) conversation should appear in User A's list")
        check(ids_a.index(conv_a2) < ids_a.index(conv_a), "most recently updated conversation should sort first")

        print("\n=== GET /api/chat/conversations/{id} (User A, own conversation) - full history ===")
        with httpx.Client(timeout=30) as client:
            detail_resp = client.get(
                f"{API_BASE}/api/chat/conversations/{conv_a}", headers={"Authorization": f"Bearer {token_a}"}
            )
        check(detail_resp.status_code == 200, f"detail should be 200 for own conversation, got {detail_resp.status_code}")
        turns = detail_resp.json().get("turns", [])
        check(len(turns) == 2, f"expected 2 turns (2 questions asked), got {len(turns)}")
        if len(turns) == 2:
            check(turns[0]["question"] == "Điều 8 Bộ luật TTHS quy định gì?", "first turn = first question asked")
            check(turns[0]["answer"] == answer1, "first turn's answer should match what was streamed back")
            check(turns[1]["question"] == "Còn Điều 9 thì sao?", "second turn = second question asked")

        print("\n=== SECURITY: User B tries to read User A's conversation via correct ID, own token ===")
        with httpx.Client(timeout=30) as client:
            cross_resp = client.get(
                f"{API_BASE}/api/chat/conversations/{conv_a}", headers={"Authorization": f"Bearer {token_b}"}
            )
        check(cross_resp.status_code == 404,
              f"User B reading User A's real conversation_id must be 404 (not 200/403), got {cross_resp.status_code}")
        if cross_resp.status_code == 200:
            print(f"  !!! LEAKED DATA: {cross_resp.json()}")

        print("\n=== SECURITY: User B's own conversation list must NOT contain User A's conversations ===")
        with httpx.Client(timeout=30) as client:
            list_b_resp = client.get(f"{API_BASE}/api/chat/conversations", headers={"Authorization": f"Bearer {token_b}"})
        ids_b = [c["conversation_id"] for c in list_b_resp.json().get("conversations", [])]
        check(conv_a not in ids_b, "User B's conversation list must not contain User A's conversation_id")
        check(conv_a2 not in ids_b, "User B's conversation list must not contain User A's second conversation_id")

        print("\n=== SECURITY: no Authorization header at all -> 401, not a leak ===")
        with httpx.Client(timeout=30) as client:
            no_auth_resp = client.get(f"{API_BASE}/api/chat/conversations/{conv_a}")
        check(no_auth_resp.status_code == 401, f"no auth header should be 401, got {no_auth_resp.status_code}")

    finally:
        print("\n=== Teardown: deleting the 2 disposable test accounts + their log rows ===")
        teardown_test_user(admin_client, user_a_id)
        teardown_test_user(admin_client, user_b_id)

    print(f"\n{'=' * 60}")
    if failures:
        print(f"FAIL - {len(failures)} check(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("ALL CONVERSATION HISTORY E2E + SECURITY TESTS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
