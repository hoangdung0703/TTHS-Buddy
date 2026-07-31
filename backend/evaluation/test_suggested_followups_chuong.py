"""Phase 3 Extension - suggested_followups chuong-priority: real (no-mock) test against the live
Qdrant collection and the real rag_service._build_suggested_followups.

Usage:
    python backend/evaluation/test_suggested_followups_chuong.py

Regression case for the Phase 6 accepted-limitation this closes: asking about one procedural
role (Tham phan, Dieu 45 Bo luat TTHS) should now surface OTHER Dieu in the exact same Chuong
(III - "Co quan co tham quyen tien hanh to tung, nguoi co tham quyen tien hanh to tung"), which
holds a run of consecutive per-role Dieu (Chanh an 44, Tham phan 45, Hoi tham 46, Kiem tra vien
43, Thu ky Toa an 47, Tham tra vien 48) - not just whatever is topically nearest by embedding,
which could previously land in a different Chuong entirely.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.services import rag_service as rs  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.models import FieldCondition, Filter, MatchValue  # noqa: E402

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def _chuong_of(client: QdrantClient, collection: str, source_document: str, dieu_number: str) -> str | None:
    points, _ = client.scroll(
        collection_name=collection,
        scroll_filter=Filter(must=[
            FieldCondition(key="source_type", match=MatchValue(value="legal_text")),
            FieldCondition(key="source_document", match=MatchValue(value=source_document)),
            FieldCondition(key="dieu_number", match=MatchValue(value=dieu_number)),
        ]),
        limit=1,
        with_payload=True,
    )
    return points[0].payload.get("chuong_number") if points else None


def main() -> int:
    settings = get_settings()
    client = QdrantClient(url=str(settings.qdrant_url), api_key=settings.qdrant_api_key, check_compatibility=False)
    collection = settings.qdrant_collection
    source_document = "Bộ luật TTHS.pdf"

    points, _ = client.scroll(
        collection_name=collection,
        scroll_filter=Filter(must=[
            FieldCondition(key="source_type", match=MatchValue(value="legal_text")),
            FieldCondition(key="source_document", match=MatchValue(value=source_document)),
            FieldCondition(key="dieu_number", match=MatchValue(value="45")),
        ]),
        limit=5,
        with_payload=True,
    )
    check(len(points) > 0, "expected to find Dieu 45 (Tham phan) chunks in Qdrant")
    if not points:
        print("FAIL - could not find Dieu 45, aborting")
        return 1

    top_point = points[0]
    chuong_of_45 = top_point.payload.get("chuong_number")
    print(f"Dieu 45 payload: chuong_number={chuong_of_45!r} dieu_title={top_point.payload.get('dieu_title')!r}")
    check(chuong_of_45 == "III", f"expected Dieu 45 to be in Chuong III, got {chuong_of_45!r}")

    top_chunk = rs.RetrievedChunk(point_id=str(top_point.id), score=1.0, is_exact_match=True, payload=top_point.payload)
    followups = rs._build_suggested_followups(client, collection, top_chunk, set())

    print("Followups for Dieu 45 (Tham phan):")
    for f in followups:
        print(f"  Dieu {f.dieu_number}: {f.suggested_question}")

    check(len(followups) > 0, "expected at least one suggested followup for Dieu 45")

    followup_dieu_numbers = {f.dieu_number for f in followups}
    same_chuong_role_cluster = {"43", "44", "46", "47", "48"}  # Kiem tra vien, Chanh an, Hoi tham, Thu ky, Tham tra vien
    check(bool(followup_dieu_numbers & same_chuong_role_cluster),
          f"expected at least one followup from the same-chuong role cluster {same_chuong_role_cluster}, "
          f"got {followup_dieu_numbers}")

    for dieu_number in followup_dieu_numbers:
        followup_chuong = _chuong_of(client, collection, source_document, dieu_number)
        check(followup_chuong == chuong_of_45,
              f"followup Dieu {dieu_number} has chuong_number={followup_chuong!r}, expected same as Dieu 45's "
              f"{chuong_of_45!r} - a mismatch here would mean the old vector-similarity-only accepted-limitation "
              f"is back")

    if failures:
        print(f"\nFAIL - {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("\nALL SUGGESTED_FOLLOWUPS CHUONG-PRIORITY TESTS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
