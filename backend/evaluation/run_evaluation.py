"""Phase 9 evaluation runner: replays backend/evaluation/test_set.json against the real
POST /api/chat/query endpoint (real JWT, real Gemini/Qdrant calls - no mocking) and computes
the 3 metrics required by requirements.md Muc 8 (Phase 9 Definition of Done):

  - citation accuracy: for direct_citation/analytical cases with a non-empty
    expected_dieu_numbers, do the returned citations contain the expected Dieu?
  - groundedness: every response must have citations OR be the exact fallback answer - never
    neither (the Phase 4 contract, re-measured here systematically).
  - correct-refusal rate: for out_of_scope cases, does the bot actually refuse (fallback text)
    instead of fabricating an answer?

A 4th, secondary check covers the 2 analytical cases whose expected_dieu_numbers is
intentionally empty (they test academic_reference retrieval on a cross-topic question, not
citation of a single Dieu) - see test_set.json comments in the accompanying report.

Two fields needed for groundedness/academic-usage are not exposed on the public API response
(is_fallback, used_academic_reference), so this script reads them back from chat_query_logs
(service-role client) right after each call - that table is written synchronously inside the
/api/chat/query request handler before it returns, so the row is guaranteed to exist by the
time this script queries it.

Required environment variables (never hardcode credentials in this file):
  EVAL_USER_EMAIL, EVAL_USER_PASSWORD - an existing Supabase user to sign in as
Optional:
  EVAL_API_BASE_URL - default http://localhost:8000
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values
from supabase import create_client

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import create_supabase_client, get_settings  # noqa: E402
from app.services.rag_service import FALLBACK_ANSWER  # noqa: E402

TEST_SET_PATH = Path(__file__).resolve().parent / "test_set.json"
RESULTS_PATH = Path(__file__).resolve().parent / "results.json"
CHAT_QUERY_LOGS_TABLE = "chat_query_logs"

# The 2 analytical questions in test_set.json whose expected_dieu_numbers is deliberately empty
# (broad cross-topic synthesis questions meant to test academic_reference retrieval, not
# citation of one Dieu) - identified by question text since test_set.json has no dedicated flag.
ACADEMIC_ONLY_QUESTIONS = {
    "Phân tích mối quan hệ và tính thống nhất giữa Luật Hình sự và Luật Tố tụng hình sự trong việc xử lý tội phạm.",
    "Phân tích mối quan hệ phối hợp giữa Cơ quan điều tra và Viện kiểm sát trong việc áp dụng, thay đổi, hủy bỏ biện pháp ngăn chặn ở giai đoạn khởi tố vụ án hình sự.",
}


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"ERROR: missing required environment variable {name}", file=sys.stderr)
        sys.exit(1)
    return value


def _sign_in_eval_user(supabase_url: str, anon_key: str, email: str, password: str) -> tuple[str, str]:
    anon_client = create_client(supabase_url, anon_key)
    auth_response = anon_client.auth.sign_in_with_password({"email": email, "password": password})
    return auth_response.session.access_token, auth_response.user.id


def _call_chat_query(api_base_url: str, token: str, question: str) -> dict[str, Any]:
    response = httpx.post(
        f"{api_base_url}/api/chat/query",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"question": question},
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()


def _read_log_fields(service_client: Any, user_id: str, question: str) -> dict[str, Any]:
    response = (
        service_client.table(CHAT_QUERY_LOGS_TABLE)
        .select("is_fallback, used_academic_reference")
        .eq("user_id", user_id)
        .eq("question", question)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not response.data:
        # Logging degrades gracefully on failure (see chat_log_service.py) - if the row is
        # missing, fall back to reasoning from the API response text alone rather than crashing
        # the whole evaluation run over a single logging hiccup.
        return {"is_fallback": None, "used_academic_reference": None}
    return response.data[0]


def _is_fallback_text(answer: str) -> bool:
    return answer.strip() == FALLBACK_ANSWER


def run_one(api_base_url: str, token: str, user_id: str, service_client: Any,
            case: dict[str, Any]) -> dict[str, Any]:
    api_response = _call_chat_query(api_base_url, token, case["question"])
    log_fields = _read_log_fields(service_client, user_id, case["question"])

    returned_dieu_numbers = [c["dieu_number"] for c in api_response.get("citations", [])]
    has_citations = len(returned_dieu_numbers) > 0
    is_fallback = log_fields["is_fallback"] if log_fields["is_fallback"] is not None else _is_fallback_text(
        api_response.get("answer", "")
    )

    expected = set(case["expected_dieu_numbers"])
    returned = set(returned_dieu_numbers)

    result = {
        "question": case["question"],
        "category": case["category"],
        "should_refuse": case["should_refuse"],
        "expected_dieu_numbers": sorted(expected),
        "returned_dieu_numbers": sorted(returned),
        "is_fallback": is_fallback,
        "used_academic_reference": log_fields["used_academic_reference"],
        "answer": api_response.get("answer", ""),
        "grounded": has_citations or is_fallback,
    }

    if case["should_refuse"]:
        result["correctly_refused"] = is_fallback
    elif expected:
        result["citation_recall"] = len(expected & returned) / len(expected)
        result["citation_precision"] = (len(expected & returned) / len(returned)) if returned else 0.0
        result["all_expected_cited"] = expected.issubset(returned)
    elif case["question"] in ACADEMIC_ONLY_QUESTIONS:
        result["academic_reference_used"] = bool(log_fields["used_academic_reference"])

    return result


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        by_category.setdefault(r["category"], []).append(r)

    summary: dict[str, Any] = {}

    # Citation accuracy - only over direct_citation/analytical cases with a non-empty
    # expected_dieu_numbers (the cases where result["all_expected_cited"] was computed).
    citation_cases = [r for r in results if "all_expected_cited" in r]
    if citation_cases:
        summary["citation_accuracy"] = {
            "n": len(citation_cases),
            "exact_match_rate": sum(r["all_expected_cited"] for r in citation_cases) / len(citation_cases),
            "mean_recall": sum(r["citation_recall"] for r in citation_cases) / len(citation_cases),
            "mean_precision": sum(r["citation_precision"] for r in citation_cases) / len(citation_cases),
        }

    # Groundedness - over all 29 cases.
    summary["groundedness"] = {
        "n": len(results),
        "grounded_rate": sum(r["grounded"] for r in results) / len(results),
        "violations": [r["question"] for r in results if not r["grounded"]],
    }

    # Correct-refusal rate - over out_of_scope cases.
    refusal_cases = [r for r in results if r["should_refuse"]]
    if refusal_cases:
        summary["correct_refusal"] = {
            "n": len(refusal_cases),
            "rate": sum(r["correctly_refused"] for r in refusal_cases) / len(refusal_cases),
            "failures": [r["question"] for r in refusal_cases if not r["correctly_refused"]],
        }

    # Academic-reference-usage check - the 2 cross-topic analytical cases.
    academic_cases = [r for r in results if "academic_reference_used" in r]
    if academic_cases:
        summary["academic_reference_usage"] = {
            "n": len(academic_cases),
            "rate": sum(r["academic_reference_used"] for r in academic_cases) / len(academic_cases),
            "details": [
                {"question": r["question"], "used_academic_reference": r["academic_reference_used"]}
                for r in academic_cases
            ],
        }

    summary["by_category_grounded_rate"] = {
        category: sum(r["grounded"] for r in rows) / len(rows) for category, rows in by_category.items()
    }

    return summary


def print_report(results: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    print("\n" + "=" * 78)
    print("PHASE 9 EVALUATION REPORT")
    print("=" * 78)

    print(f"\nTotal questions: {len(results)}")
    for category, rate in summary["by_category_grounded_rate"].items():
        n = sum(1 for r in results if r["category"] == category)
        print(f"  - {category}: {n} câu, groundedness = {rate:.0%}")

    if "citation_accuracy" in summary:
        ca = summary["citation_accuracy"]
        print(f"\n[1] CITATION ACCURACY (n={ca['n']}, direct_citation + analytical có expected_dieu_numbers)")
        print("    Cách tính: exact_match_rate = tỷ lệ câu mà TẤT CẢ Điều kỳ vọng đều xuất hiện trong")
        print("    citations trả về (cho phép trích thêm Điều khác); mean_recall/mean_precision đo chi")
        print("    tiết hơn: recall = tỷ lệ Điều kỳ vọng thực sự được trích (không bỏ sót), precision =")
        print("    tỷ lệ trích dẫn đúng trong số citations trả về (không trích thừa).")
        print(f"    exact_match_rate = {ca['exact_match_rate']:.0%}")
        print(f"    mean_recall       = {ca['mean_recall']:.0%}")
        print(f"    mean_precision    = {ca['mean_precision']:.0%}")

    gr = summary["groundedness"]
    print(f"\n[2] GROUNDEDNESS (n={gr['n']}, toàn bộ bộ test)")
    print("    Điều kiện: mọi câu trả lời phải có citations HOẶC là đúng câu fallback - không bao giờ")
    print("    thiếu cả hai.")
    print(f"    grounded_rate = {gr['grounded_rate']:.0%}")
    if gr["violations"]:
        print(f"    VI PHẠM ({len(gr['violations'])} câu):")
        for q in gr["violations"]:
            print(f"      - {q}")

    if "correct_refusal" in summary:
        cr = summary["correct_refusal"]
        print(f"\n[3] CORRECT-REFUSAL RATE (n={cr['n']}, category=out_of_scope)")
        print(f"    rate = {cr['rate']:.0%}")
        if cr["failures"]:
            print(f"    THẤT BẠI ({len(cr['failures'])} câu - bot KHÔNG từ chối dù ngoài phạm vi):")
            for q in cr["failures"]:
                print(f"      - {q}")

    if "academic_reference_usage" in summary:
        ar = summary["academic_reference_usage"]
        print(f"\n[4] ACADEMIC-REFERENCE USAGE (n={ar['n']}, 2 câu analytical có expected_dieu_numbers rỗng)")
        print(f"    rate = {ar['rate']:.0%}")
        for d in ar["details"]:
            status = "OK" if d["used_academic_reference"] else "KHÔNG dùng academic_reference"
            print(f"      - [{status}] {d['question']}")

    print("\n" + "-" * 78)
    print("CHI TIẾT TỪNG CÂU FAIL (nếu có):")
    any_fail = False
    for r in results:
        failed = (not r["grounded"]) or (r.get("all_expected_cited") is False) or \
                 (r.get("correctly_refused") is False) or (r.get("academic_reference_used") is False)
        if not failed:
            continue
        any_fail = True
        print(f"\n  [{r['category']}] {r['question']}")
        print(f"    expected_dieu_numbers = {r['expected_dieu_numbers']}")
        print(f"    returned_dieu_numbers = {r['returned_dieu_numbers']}")
        print(f"    is_fallback = {r['is_fallback']}, grounded = {r['grounded']}")
        print(f"    answer (rút gọn) = {r['answer'][:200]}")
    if not any_fail:
        print("  (không có câu nào fail)")
    print("=" * 78 + "\n")


def main() -> None:
    # NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY live in the root .env (shared with
    # the frontend); os.environ still wins so a caller can override without editing the file.
    root_env = {**dotenv_values(PROJECT_ROOT / ".env"), **os.environ}

    api_base_url = os.environ.get("EVAL_API_BASE_URL", "http://localhost:8000")
    eval_email = _require_env("EVAL_USER_EMAIL")
    eval_password = _require_env("EVAL_USER_PASSWORD")

    supabase_url = root_env.get("NEXT_PUBLIC_SUPABASE_URL")
    anon_key = root_env.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    if not supabase_url or not anon_key:
        print("ERROR: NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY not found in .env",
              file=sys.stderr)
        sys.exit(1)

    settings = get_settings()
    service_client = create_supabase_client(settings)

    token, user_id = _sign_in_eval_user(supabase_url, anon_key, eval_email, eval_password)

    test_set = json.loads(TEST_SET_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(test_set)} test cases from {TEST_SET_PATH.name}")

    results: list[dict[str, Any]] = []
    for i, case in enumerate(test_set, start=1):
        print(f"  [{i}/{len(test_set)}] {case['question'][:70]}...")
        result = run_one(api_base_url, token, user_id, service_client, case)
        results.append(result)
        time.sleep(0.3)  # light pacing against the Gemini API, not a hard rate limit need

    summary = summarize(results)
    print_report(results, summary)

    RESULTS_PATH.write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Đã lưu kết quả đầy đủ vào {RESULTS_PATH}")


if __name__ == "__main__":
    main()
