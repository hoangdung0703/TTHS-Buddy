"""Per-file classification for the 12 raw source PDFs. Classification was confirmed
manually against document content (not filename guessing) before parse_law.py was written -
see requirements.md Phase 3 notes for the underlying decisions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SourceType = Literal["legal_text", "academic_reference"]


@dataclass(frozen=True)
class DocumentConfig:
    filename: str
    source_type: SourceType
    # Only meaningful for legal_text: the human-readable version/issue identifier used
    # as the "law_version" chunk metadata field required by requirements.md section 4.
    law_version: str | None = None


DOCUMENT_REGISTRY: list[DocumentConfig] = [
    DocumentConfig(
        filename="Bộ luật TTHS.pdf",
        source_type="legal_text",
        law_version="BLTTHS 2015 (số 101/2015/QH13, sửa đổi bổ sung 2021)"
    ),
    DocumentConfig(
        filename="Văn bản hợp nhất BLHS 2015.pdf",
        source_type="legal_text",
        law_version="BLHS - Văn bản hợp nhất năm 2025"
    ),
    DocumentConfig(
        filename="Nghị định 250_NĐ-CP.pdf",
        source_type="legal_text",
        law_version="Nghị định 250/2025/NĐ-CP"
    ),
    DocumentConfig(
        filename="Thông tư liên tịch 05.pdf",
        source_type="legal_text",
        law_version="Thông tư liên tịch 05/2026/TTLT-BCA-BQP-VKSNDTC-TANDTC"
    ),
    DocumentConfig(
        filename="Thông tư liên tịch 01_2026 VKSND - BCA - BQP.pdf",
        source_type="legal_text",
        law_version="Thông tư liên tịch 01/2026/TTLT-VKSNDTC-BCA-BQP"
    ),
    DocumentConfig(
        filename="Giáo trình Luật Tố tụng hình sự -đã nén.pdf",
        source_type="academic_reference"
    ),
    DocumentConfig(
        filename="Nguồn bào chữa trong LTTHS.pdf",
        source_type="academic_reference"
    ),
    DocumentConfig(
        filename="Suy đoán người vô tội trong thực hành quyền công tố của BLTTHS.pdf",
        source_type="academic_reference"
    ),
    DocumentConfig(
        filename="Mối quan hệ và tính thống nhất giữa LHS & LTTHS.pdf",
        source_type="academic_reference"
    ),
    DocumentConfig(
        filename=(
            "Mối quan hệ GIỮA CƠ QUAN ĐIỀU TRA VÀ VIỆN KIỂM SÁT TRONG VIỆC ÁP DỤNG, "
            "THAY ĐỔI, HỦY BỎ BIỆN PHÁP NGĂN CHẶN TRONG GIAI ĐOẠN KHỞI TỐ VỤ ÁN HÌNH SỰ.pdf"
        ),
        source_type="academic_reference"
    ),
    DocumentConfig(
        filename="Chính sách LTTHS về bảo vệ quyền con người.pdf",
        source_type="academic_reference"
    ),
    DocumentConfig(
        filename="Bảo vệ quyền con người bằng TTHS.pdf",
        source_type="academic_reference"
    )
]


def get_document_config(filename: str) -> DocumentConfig:
    for config in DOCUMENT_REGISTRY:
        if config.filename == filename:
            return config
    raise ValueError(f"No document_registry entry for file: {filename}")
