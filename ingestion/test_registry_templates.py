"""Guard: form templates kept in raw_documents/ (e.g. template_bienban.pdf, the Mẫu 22-HS layout used
by the mock-trial biên bản) must never reach the RAG index.

Ingestion selects files ONLY through DOCUMENT_REGISTRY (parse_law.py reads
RAW_DOCUMENTS_DIR / config.filename for each entry; nothing scans the directory). This test fails if
a template is ever registered, or if an ingestion script starts listing the directory.

Usage:
    python -m unittest ingestion.test_registry_templates
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from ingestion.document_registry import DOCUMENT_REGISTRY

INGESTION_DIR = Path(__file__).resolve().parent
TEMPLATE_PREFIX = "template_"
DIRECTORY_SCAN = re.compile(r"\.(?:glob|rglob|iterdir)\(|os\.(?:listdir|scandir|walk)\(")


class RegistryTemplateTests(unittest.TestCase):
    def test_no_template_is_registered(self):
        registered = [c.filename for c in DOCUMENT_REGISTRY if c.filename.casefold().startswith(TEMPLATE_PREFIX)]
        self.assertEqual(registered, [])

    def test_no_ingestion_script_scans_raw_documents(self):
        offenders = [p.name for p in INGESTION_DIR.glob("*.py")
                     if p.name != Path(__file__).name and DIRECTORY_SCAN.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
