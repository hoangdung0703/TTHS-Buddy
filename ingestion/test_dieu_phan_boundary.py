"""Regression tests for the "next Phan (Part-level) heading bleeds into the preceding Dieu's
chunk_text" bug - the SAME root cause as the Chuong/Muc bleed fixed earlier (see
test_dieu_chuong_muc_boundary.py), found one structural level up: Phan sits ABOVE Chuong, and
chunk_legal_text's body-end truncation originally only considered chuong_events/muc_events, so a
Dieu immediately preceding a new Phan (Part) - which is also, incidentally, always immediately
followed by a Chuong heading - still swept the Phan heading (and the Chuong start after it) into
its own trailing text even after the Chuong/Muc fix landed.

Confirmed by direct inspection of chunks.json before this fix, across all 10 Dieu (in Bo luat
TTHS and BLHS - the only 2 documents with real Phan structure) that sit right before a Phan
transition:
    Bo luat TTHS: 142, 235, 249, 362, 369, 412, 490, 508
    BLHS:         107, 425

Usage:
    python -m ingestion.test_dieu_phan_boundary
"""
from __future__ import annotations

import re

from ingestion.document_registry import DOCUMENT_REGISTRY
from ingestion.parse_law import parse_document

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def chunks_for(filename: str) -> list[dict]:
    config = next(c for c in DOCUMENT_REGISTRY if c.filename == filename)
    chunks, _ = parse_document(config)
    return chunks


def last_chunk(chunks: list[dict], dieu_number: str) -> dict:
    matches = [c for c in chunks if c["dieu_number"] == dieu_number]

    def sort_key(c: dict) -> tuple[int, int]:
        kn = c["khoan_number"]
        if kn is None:
            return (0, 0)
        m = re.match(r"(\d+)", kn)
        return (1, int(m.group(1)) if m else 0)

    return sorted(matches, key=sort_key)[-1]


def main() -> int:
    ttths = chunks_for("Bộ luật TTHS.pdf")
    blhs = chunks_for("Văn bản hợp nhất BLHS 2015.pdf")

    # Dieu 412 - already known-bad after the Chuong/Muc-only fix: Chuong XXVIII/XXIX bleed was
    # gone, but "Phần thứ bảy\nTHỦ TỤC ĐẶC BIỆT" (the Part heading right before those Chuong)
    # was still left dangling at the end of its chunk_text.
    c412 = last_chunk(ttths, "412")
    check("Phần thứ bảy" not in c412["chunk_text"],
          f"Dieu 412 chunk_text still contains 'Phần thứ bảy': {c412['chunk_text'][-200:]!r}")
    check("THỦ TỤC ĐẶC BIỆT" not in c412["chunk_text"],
          f"Dieu 412 chunk_text still contains Phan 7's title 'THỦ TỤC ĐẶC BIỆT': "
          f"{c412['chunk_text'][-200:]!r}")

    # Dieu 142 - last Dieu before "Phần thứ hai\nKHỞI TỐ, ĐIỀU TRA VỤ ÁN HÌNH SỰ"
    c142 = last_chunk(ttths, "142")
    check("Phần thứ hai" not in c142["chunk_text"],
          f"Dieu 142 chunk_text still contains 'Phần thứ hai': {c142['chunk_text'][-200:]!r}")
    check("KHỞI TỐ, ĐIỀU TRA VỤ ÁN HÌNH SỰ" not in c142["chunk_text"],
          f"Dieu 142 chunk_text still contains Phan 2's title: {c142['chunk_text'][-200:]!r}")

    # Dieu 107 (BLHS) - last Dieu before "Phần thứ hai\nCÁC TỘI PHẠM"
    c107 = last_chunk(blhs, "107")
    check("Phần thứ hai" not in c107["chunk_text"],
          f"BLHS Dieu 107 chunk_text still contains 'Phần thứ hai': {c107['chunk_text'][-200:]!r}")
    check("CÁC TỘI PHẠM" not in c107["chunk_text"],
          f"BLHS Dieu 107 chunk_text still contains Phan 2's title 'CÁC TỘI PHẠM': "
          f"{c107['chunk_text'][-200:]!r}")

    # The Dieu that follows a Phan transition must still have its own content intact - guards
    # against the fix over-truncating into the wrong Dieu.
    # Chuong XXVIII was repealed with no Dieu under it, so the real next Dieu after 412 is 431
    # (first Dieu of Chuong XXIX, the chapter that actually opens Phan 7).
    c431 = last_chunk(ttths, "431")
    check(len(c431["chunk_text"]) > 50, "Dieu 431 (first Dieu of Phan 7) chunk_text unexpectedly short/empty")
    c108_blhs = last_chunk(blhs, "108")
    check(len(c108_blhs["chunk_text"]) > 50, "BLHS Dieu 108 (first Dieu of Phan 2) chunk_text unexpectedly short/empty")

    if failures:
        print(f"FAIL - {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("ALL DIEU/PHAN BOUNDARY TEST CASES PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
