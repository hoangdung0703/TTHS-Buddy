"""Phase 3 Extension - aggregate/structure query handling: real (no-mock) test against the live
Qdrant collection and the real rag_service functions.

Usage:
    python backend/evaluation/test_aggregate_structure_query.py

Covers:
1. Intent detection (is_aggregate_structure_question) fires on the exact reported question and
   not on an ordinary lookup question.
2. detect_source_document correctly resolves "Bo luat TTHS" wording (this was a real pre-existing
   bug - the old regex "blths" never matched the real abbreviation "BLTTHS", 6 letters, at all).
3. count_chuong_and_dieu against BLTTHS returns numbers in a range consistent with the real,
   publicly known structure of the Bo luat To tung hinh su 2015 (sua doi bo sung 2021) - not just
   "the code ran without raising".
4. A document with confirmed no real Chuong structure (Thong tu lien tich 01/2026) reports
   chuong_count=0 and phrases the answer accordingly, instead of being force-fit.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.services import rag_service as rs  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    settings = get_settings()
    client = QdrantClient(url=str(settings.qdrant_url), api_key=settings.qdrant_api_key, check_compatibility=False)
    collection = settings.qdrant_collection

    q1 = "Bộ luật TTHS gồm bao nhiêu chương, bao nhiêu điều?"
    check(rs.is_aggregate_structure_question(q1), f"expected aggregate intent detected for: {q1!r}")
    check(rs.detect_source_document(q1) == "Bộ luật TTHS.pdf", f"expected BLTTHS source_document for: {q1!r}")

    q2 = "Điều 109 quy định gì?"
    check(not rs.is_aggregate_structure_question(q2), f"expected NO aggregate intent for: {q2!r}")

    chuong_count, dieu_count, law_version = rs.count_chuong_and_dieu(client, collection, "Bộ luật TTHS.pdf")
    print(f"BLTTHS: chuong_count={chuong_count} dieu_count={dieu_count} law_version={law_version!r}")
    check(chuong_count == 35, f"expected 35 active Chuong for BLTTHS (36 total minus 1 abolished), got {chuong_count}")
    check(400 < dieu_count < 520, f"expected dieu_count in a realistic range for BLTTHS (400-520), got {dieu_count}")

    answer = rs.build_aggregate_structure_answer("Bộ luật TTHS.pdf", law_version, chuong_count, dieu_count)
    print(f"Aggregate answer: {answer}")
    check(str(chuong_count) in answer, "answer text should mention the chuong count")
    check(str(dieu_count) in answer, "answer text should mention the dieu count")
    check("Lưu ý" in answer, "answer text should include the ingested-data-disclaimer note")

    tt01_chuong, tt01_dieu, tt01_version = rs.count_chuong_and_dieu(
        client, collection, "Thông tư liên tịch 01_2026 VKSND - BCA - BQP.pdf"
    )
    print(f"Thong tu 01/2026: chuong_count={tt01_chuong} dieu_count={tt01_dieu}")
    check(tt01_chuong == 0, f"Thong tu 01/2026 has no Chuong structure - expected chuong_count=0, got {tt01_chuong}")
    check(tt01_dieu > 0, f"Thong tu 01/2026 should still have dieu_count > 0, got {tt01_dieu}")
    tt01_answer = rs.build_aggregate_structure_answer(
        "Thông tư liên tịch 01_2026 VKSND - BCA - BQP.pdf", tt01_version, tt01_chuong, tt01_dieu
    )
    print(f"Thong tu 01/2026 answer: {tt01_answer}")
    check("không được chia thành các chương" in tt01_answer, "expected no-chuong-structure phrasing")

    if failures:
        print(f"\nFAIL - {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("\nALL AGGREGATE STRUCTURE QUERY TESTS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
