"""Regression tests for the "Chuong/Muc heading bleeds into the preceding Dieu's chunk_text"
bug (see requirements.md bug report - discovered via Dieu 108 BLTTHS: its chunk_text ended with
"...vu an.\nChuong VII\n58\nBIEN PHAP NGAN CHAN, BIEN PHAP CUONG CHE\nMuc I\nBIEN PHAP NGAN
CHAN" - the next Chuong/Muc heading, swept in verbatim because chunk_legal_text's body-end
computation only looked at the position of the NEXT "Dieu N." match, never at the
chuong_events/muc_events _find_chuong_muc_events() already computes for metadata purposes).

Covers the 3 distinct shapes confirmed by direct inspection of ingestion/chunks.json before the
fix:
1. Simple bleed - a single Chuong+Muc heading pair (Dieu 108).
2. Consecutive-heading bleed - a repealed Chuong with no Dieu under it, so TWO Chuong headings
   (one "(duoc bai bo)", one real) plus stray footnotes get swept in before the real next Dieu
   (Dieu 412).
3. Heading + large trailing footnote block bleed - the heading itself is immediately followed by
   several unrelated footnotes that happen to sit at the bottom of that page in the linearized
   PDF text, ~1200 chars, landing in the LAST Khoan-split segment (khoan 4) of the Dieu (Dieu 454).

Usage:
    python -m ingestion.test_dieu_chuong_muc_boundary
"""
from __future__ import annotations

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
    """Mirrors the "last khoan-segment of this Dieu" selection used in the corpus-wide scan -
    the trailing heading bleed, if present, can only land in the last physical segment."""
    matches = [c for c in chunks if c["dieu_number"] == dieu_number]
    def sort_key(c: dict) -> tuple[int, int]:
        kn = c["khoan_number"]
        if kn is None:
            return (0, 0)
        import re
        m = re.match(r"(\d+)", kn)
        return (1, int(m.group(1)) if m else 0)
    return sorted(matches, key=sort_key)[-1]


def main() -> int:
    ttths = chunks_for("Bộ luật TTHS.pdf")

    # --- Case 1: simple bleed (Dieu 108 -> Chuong VII / Muc I heading) ---
    c108 = last_chunk(ttths, "108")
    check("Chương VII" not in c108["chunk_text"],
          f"Dieu 108 chunk_text still contains the next Chuong's heading 'Chương VII': "
          f"{c108['chunk_text'][-200:]!r}")
    check("Mục I" not in c108["chunk_text"],
          f"Dieu 108 chunk_text still contains the next Muc's heading 'Mục I': "
          f"{c108['chunk_text'][-200:]!r}")
    check("BIỆN PHÁP NGĂN CHẶN" not in c108["chunk_text"],
          f"Dieu 108 chunk_text still contains the next Muc's title text: "
          f"{c108['chunk_text'][-200:]!r}")
    check(" ".join(c108["chunk_text"].split()).endswith("đã thu thập được về vụ án."),
          f"Dieu 108 chunk_text should end cleanly at its own last real sentence, got tail: "
          f"{c108['chunk_text'][-80:]!r}")

    # The Dieu that starts the NEXT section must still have its own real content intact -
    # guards against the fix over-truncating and swallowing genuine content into the wrong Dieu.
    c109 = last_chunk(ttths, "109")
    check(c109["chuong_number"] == "VII" and c109["muc_number"] == "I",
          f"Dieu 109 should open Chuong VII / Muc I, got chuong={c109['chuong_number']!r} "
          f"muc={c109['muc_number']!r}")
    check(len(c109["chunk_text"]) > 50, "Dieu 109 chunk_text unexpectedly short/empty")

    # --- Case 2: consecutive-heading bleed (Dieu 412 -> repealed Chuong XXVIII + real Chuong XXIX) ---
    c412 = last_chunk(ttths, "412")
    check("Chương XXVIII" not in c412["chunk_text"],
          f"Dieu 412 chunk_text still contains repealed 'Chương XXVIII': "
          f"{c412['chunk_text'][-300:]!r}")
    check("Chương XXIX" not in c412["chunk_text"],
          f"Dieu 412 chunk_text still contains the next real 'Chương XXIX' heading: "
          f"{c412['chunk_text'][-300:]!r}")
    check("THỦ TỤC TỐ TỤNG TRUY CỨU" not in c412["chunk_text"],
          f"Dieu 412 chunk_text still contains Chuong XXIX's title text: "
          f"{c412['chunk_text'][-300:]!r}")

    # --- Case 3: heading + large trailing footnote block bleed (Dieu 454 -> Chuong XXXI) ---
    # Note: stripping ~1200 chars of bled footnote text drops Dieu 454's body back under
    # LONG_DIEU_CHAR_THRESHOLD, so it correctly stops being Khoan-split (was spuriously split into
    # khoan 1-4 before the fix only because the bled text pushed it over the length threshold) -
    # last_chunk() now returns the single unsplit chunk (khoan_number None), which is the correct
    # shape, not a regression.
    c454 = last_chunk(ttths, "454")
    check(c454["khoan_number"] is None,
          f"Dieu 454 no longer needs Khoan-splitting once the bled footnote text is stripped "
          f"(body now under LONG_DIEU_CHAR_THRESHOLD) - expected a single chunk (khoan_number "
          f"None), got khoan_number={c454['khoan_number']!r}")
    check("Chương XXXI" not in c454["chunk_text"],
          f"Dieu 454 chunk_text still contains 'Chương XXXI': {c454['chunk_text'][-300:]!r}")
    check("THỦ TỤC RÚT GỌN" not in c454["chunk_text"],
          f"Dieu 454 chunk_text still contains Chuong XXXI's title: {c454['chunk_text'][-300:]!r}")
    check("cơ sở bắt buộc chữa bệnh tâm thần" not in c454["chunk_text"],
          f"Dieu 454 chunk_text still contains the trailing footnote block: "
          f"{c454['chunk_text'][-300:]!r}")
    check(" ".join(c454["chunk_text"].split()).endswith(
              "có thể được phục hồi theo quy định của Bộ luật này."),
          f"Dieu 454 chunk_text should end at its own real last sentence, got tail: "
          f"{c454['chunk_text'][-80:]!r}")

    if failures:
        print(f"FAIL - {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("ALL DIEU/CHUONG/MUC BOUNDARY TEST CASES PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
