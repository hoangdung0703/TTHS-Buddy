"""New test cases for Phase 3 Extension - Chuong/Muc detection (Buoc 2).

Usage:
    python -m ingestion.test_chuong_muc

Re-runs the real extraction + chunk_legal_text pipeline and asserts:
1. Every legal_text chunk's chuong_number/chuong_title/muc_number/muc_title matches a
   hand-verified expected value for a sample of Dieu spanning: first Dieu of a document,
   a Dieu inside a Muc, a Dieu in a Chuong with no Muc, a Dieu near a Chuong boundary
   (to check the transition + Muc reset logic), and the last Dieu of a document.
2. Nghi dinh 250 and Thong tu lien tich 05 (confirmed to have real Chuong, no Muc) get
   chuong_number set and muc_number is always None.
3. Thong tu lien tich 01_2026 (confirmed to have NO Chuong/Muc structure at all) gets
   chuong_number/muc_number None for every single chunk - not forced.
4. Muc numbering resets across Chuong boundaries (BLHS "Muc 1" appears under multiple
   different Chuong - each occurrence must resolve to ITS OWN enclosing Chuong, not leak
   from a previous one).
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


def first_chunk(chunks: list[dict], dieu_number: str) -> dict:
    return next(c for c in chunks if c["dieu_number"] == dieu_number)


def main() -> int:
    # --- Bo luat TTHS: has Chuong (roman) + Muc (roman) ---
    ttths = chunks_for("Bộ luật TTHS.pdf")

    c = first_chunk(ttths, "1")
    check(c["chuong_number"] == "I", f"TTHS Dieu 1 chuong_number expected 'I', got {c['chuong_number']!r}")
    check(c["chuong_title"] == "PHẠM VI ĐIỀU CHỈNH, NHIỆM VỤ, HIỆU LỰC CỦA BỘ LUẬT TỐ TỤNG HÌNH SỰ",
          f"TTHS Dieu 1 chuong_title mismatch: {c['chuong_title']!r}")
    check(c["muc_number"] is None, f"TTHS Dieu 1 muc_number expected None, got {c['muc_number']!r}")

    # Dieu 109 is the first Dieu of Chuong VII / Muc I (BIEN PHAP NGAN CHAN)
    c = first_chunk(ttths, "109")
    check(c["chuong_number"] == "VII", f"TTHS Dieu 109 chuong_number expected 'VII', got {c['chuong_number']!r}")
    check(c["muc_number"] == "I", f"TTHS Dieu 109 muc_number expected 'I', got {c['muc_number']!r}")
    check(c["muc_title"] == "BIỆN PHÁP NGĂN CHẶN", f"TTHS Dieu 109 muc_title mismatch: {c['muc_title']!r}")

    # Dieu 126 is the first Dieu of Muc II (BIEN PHAP CUONG CHE) within the SAME Chuong VII
    c = first_chunk(ttths, "126")
    check(c["chuong_number"] == "VII", f"TTHS Dieu 126 chuong_number expected 'VII', got {c['chuong_number']!r}")
    check(c["muc_number"] == "II", f"TTHS Dieu 126 muc_number expected 'II', got {c['muc_number']!r}")
    check(c["muc_title"] == "BIỆN PHÁP CƯỠNG CHẾ", f"TTHS Dieu 126 muc_title mismatch: {c['muc_title']!r}")

    # Dieu 34 is in Chuong III, which has no Muc at all -> muc must be None, not leaked from Chuong II
    c = first_chunk(ttths, "34")
    check(c["chuong_number"] == "III", f"TTHS Dieu 34 chuong_number expected 'III', got {c['chuong_number']!r}")
    check(c["muc_number"] is None, f"TTHS Dieu 34 muc_number expected None (no Muc in Chuong III), got {c['muc_number']!r}")

    # Dieu 497 is in the last real Chuong (XXXVI)
    c = first_chunk(ttths, "497")
    check(c["chuong_number"] == "XXXVI", f"TTHS Dieu 497 chuong_number expected 'XXXVI', got {c['chuong_number']!r}")

    # --- BLHS: has Chuong (roman) + Muc (arabic, same-line title, some wrap to 2nd line) ---
    blhs = chunks_for("Văn bản hợp nhất BLHS 2015.pdf")

    c = first_chunk(blhs, "1")
    check(c["chuong_number"] == "I", f"BLHS Dieu 1 chuong_number expected 'I', got {c['chuong_number']!r}")
    check(c["muc_number"] is None, f"BLHS Dieu 1 muc_number expected None, got {c['muc_number']!r}")

    # Dieu 90 is Muc 1 of Chuong XII - title wraps onto a 2nd physical line before "Dieu 90"
    c = first_chunk(blhs, "90")
    check(c["chuong_number"] == "XII", f"BLHS Dieu 90 chuong_number expected 'XII', got {c['chuong_number']!r}")
    check(c["muc_number"] == "1", f"BLHS Dieu 90 muc_number expected '1', got {c['muc_number']!r}")
    check(c["muc_title"] == "QUY ĐỊNH CHUNG VỀ XỬ LÝ HÌNH SỰ ĐỐI VỚI NGƯỜI DƯỚI 18 TUỔI PHẠM TỘI",
          f"BLHS Dieu 90 muc_title mismatch (wrap-merge across the heading boundary): {c['muc_title']!r}")

    # Dieu 50 is ALSO "Muc 1" but under Chuong VIII, a totally different chapter - must not be
    # confused with Dieu 90's "Muc 1" under Chuong XII (this is the numbering-resets-per-Chuong check)
    c = first_chunk(blhs, "50")
    check(c["chuong_number"] == "VIII", f"BLHS Dieu 50 chuong_number expected 'VIII', got {c['chuong_number']!r}")
    check(c["muc_number"] == "1", f"BLHS Dieu 50 muc_number expected '1', got {c['muc_number']!r}")
    check(c["muc_title"] == "QUY ĐỊNH CHUNG VỀ QUYẾT ĐỊNH HÌNH PHẠT",
          f"BLHS Dieu 50 muc_title mismatch: {c['muc_title']!r}")
    check(c["muc_title"] != first_chunk(blhs, "90")["muc_title"],
          "BLHS Dieu 50 and Dieu 90 both report muc_number '1' but MUST have different muc_title "
          "(different Chuong) - a leak across the Chuong boundary would make these equal")

    # --- Nghi dinh 250: real Chuong (confirmed 4), no Muc at all ---
    nd250 = chunks_for("Nghị định 250_NĐ-CP.pdf")
    check(all(c["muc_number"] is None for c in nd250),
          "Nghi dinh 250 has no Muc structure - every chunk's muc_number must be None")
    check(any(c["chuong_number"] is not None for c in nd250),
          "Nghi dinh 250 has real Chuong structure (confirmed I-IV) - chuong_number should not be all-None")
    chuong_numbers_nd250 = {c["chuong_number"] for c in nd250 if c["chuong_number"] is not None}
    check(chuong_numbers_nd250 == {"I", "II", "III", "IV"},
          f"Nghi dinh 250 expected exactly chuong I-IV, got {sorted(chuong_numbers_nd250)}")

    # --- Thong tu lien tich 05: real Chuong (confirmed 3), no Muc at all ---
    tt05 = chunks_for("Thông tư liên tịch 05.pdf")
    check(all(c["muc_number"] is None for c in tt05),
          "Thong tu 05 has no Muc structure - every chunk's muc_number must be None")
    chuong_numbers_tt05 = {c["chuong_number"] for c in tt05 if c["chuong_number"] is not None}
    check(chuong_numbers_tt05 == {"I", "II", "III"},
          f"Thong tu 05 expected exactly chuong I-III, got {sorted(chuong_numbers_tt05)}")

    # --- Thong tu lien tich 01_2026: confirmed NO Chuong/Muc structure - must not be forced ---
    tt01 = chunks_for("Thông tư liên tịch 01_2026 VKSND - BCA - BQP.pdf")
    check(all(c["chuong_number"] is None for c in tt01),
          "Thong tu 01_2026 has no real Chuong structure - chuong_number must stay None for every chunk, "
          "not be force-fit")
    check(all(c["muc_number"] is None for c in tt01),
          "Thong tu 01_2026 has no real Muc structure - muc_number must stay None for every chunk")

    if failures:
        print(f"FAIL - {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("ALL NEW CHUONG/MUC TEST CASES PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
