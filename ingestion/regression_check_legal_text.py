"""Regression check for chunk_legal_text (Phase 3 Extension - Buoc 1/Buoc 2 test suite).

Usage:
    python -m ingestion.regression_check_legal_text

Re-runs the real extraction + chunk_legal_text pipeline on all 5 legal_text source PDFs and
diffs the result against the committed ingestion/chunks.json (the last known-good full parse
already upserted to Qdrant), chunk-by-chunk (matched on source_document + dieu_number +
khoan_number), comparing dieu_title and chunk_text exactly. Also explicitly re-confirms all
KNOWN_NON_KHOAN_TITLE_CONTINUATIONS entries still resolve (the _apply_known_title_continuation
assert inside chunking.py already guards this at parse time - this script reports it explicitly
too, as a standing regression gate to run before any future change to chunking.py).

Read-only: does not modify chunks.json or re-upsert anything to Qdrant.
"""
from __future__ import annotations

import json

from ingestion.chunking import KNOWN_NON_KHOAN_TITLE_CONTINUATIONS
from ingestion.config import CHUNKS_OUTPUT_PATH
from ingestion.document_registry import DOCUMENT_REGISTRY
from ingestion.parse_law import parse_document


def _key_for(chunk: dict) -> tuple:
    return (chunk["source_document"], chunk["dieu_number"], chunk["khoan_number"])


def _sort_key(t: tuple) -> tuple:
    return (t[0], t[1], t[2] or "")


def main() -> int:
    golden_all = json.loads(CHUNKS_OUTPUT_PATH.read_text(encoding="utf-8"))
    golden_legal = [c for c in golden_all if c["source_type"] == "legal_text"]
    golden_by_key = {_key_for(c): c for c in golden_legal}

    legal_configs = [c for c in DOCUMENT_REGISTRY if c.source_type == "legal_text"]

    total_mismatches = 0
    total_fresh = 0

    for config in legal_configs:
        print(f"\n=== {config.filename} ===")
        fresh_chunks, stats = parse_document(config)
        total_fresh += len(fresh_chunks)
        fresh_by_key = {_key_for(c): c for c in fresh_chunks}

        golden_keys = {k for k in golden_by_key if k[0] == config.filename}
        fresh_keys = {k for k in fresh_by_key if k[0] == config.filename}

        missing = golden_keys - fresh_keys
        extra = fresh_keys - golden_keys
        common = golden_keys & fresh_keys

        mismatches = []
        for k in sorted(common, key=_sort_key):
            g = golden_by_key[k]
            f = fresh_by_key[k]
            if g["dieu_title"] != f["dieu_title"] or g["chunk_text"] != f["chunk_text"]:
                mismatches.append((k, g["dieu_title"], f["dieu_title"]))

        print(f"  golden chunks: {len(golden_keys)}   fresh chunks: {len(fresh_keys)}")
        print(f"  missing (in golden, not fresh): {len(missing)}")
        print(f"  extra   (in fresh, not golden): {len(extra)}")
        print(f"  content mismatches (title/text differ): {len(mismatches)}")
        if missing:
            print(f"    missing keys: {sorted(missing, key=_sort_key)[:10]}")
        if extra:
            print(f"    extra keys: {sorted(extra, key=_sort_key)[:10]}")
        for k, g_title, f_title in mismatches[:10]:
            print(f"    MISMATCH {k}: golden title={g_title!r} vs fresh title={f_title!r}")

        total_mismatches += len(missing) + len(extra) + len(mismatches)
        if stats.pages_needing_fallback:
            print(f"  OCR fallback pages this run: {stats.pages_needing_fallback} "
                  f"(success={stats.ocr_success}, blocked={stats.recitation_blocked}, "
                  f"other_fail={stats.other_ocr_failure})")

    print(f"\n=== Known title-continuation table ({len(KNOWN_NON_KHOAN_TITLE_CONTINUATIONS)} entries) ===")
    print("All entries are guarded by an assert inside chunking.py itself (idx == 0) - since "
          "parse_document() above completed without raising, every entry's exact-substring match "
          "against the real source PDFs still holds.")
    for (doc, dieu), _ in KNOWN_NON_KHOAN_TITLE_CONTINUATIONS.items():
        candidates = [c for c in golden_legal if c["source_document"] == doc and c["dieu_number"] == dieu]
        title = candidates[0]["dieu_title"] if candidates else "<NOT FOUND IN GOLDEN>"
        print(f"  {doc} Dieu {dieu}: {title!r}")

    print("\n=== SUMMARY ===")
    print(f"Total fresh legal_text chunks: {total_fresh}")
    print(f"Total golden legal_text chunks: {len(golden_legal)}")
    print(f"Total mismatches/missing/extra: {total_mismatches}")
    print("BASELINE PASS" if total_mismatches == 0 else "BASELINE FAIL - regressions found")
    return 0 if total_mismatches == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
