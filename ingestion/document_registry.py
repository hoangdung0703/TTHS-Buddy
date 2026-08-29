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
    ),
    DocumentConfig(
        filename="Luật tổ chức toà án nhân dân.pdf",
        source_type="legal_text",
        law_version="Luật Tổ chức Tòa án nhân dân số 34/2024/QH15 (sửa đổi, bổ sung đến 2025)"
    ),
    DocumentConfig(
        filename="693495639-TINH-HUỐNG-TỐ-TỤNG-HINH-SỰ.pdf",
        source_type="academic_reference"
    ),
    DocumentConfig(
        filename="Giao-Trinh-Luat-Tố-Tụng-Hinh-Sự-Dh-Luat-Hn.pdf",
        source_type="academic_reference"
    ),
    DocumentConfig(
        filename="784492208-ĐỀ-CƯƠNG-LUẬT-TỐ-TỤNG-HINH-SỰ.pdf",
        source_type="academic_reference"
    ),
    DocumentConfig(
        filename="Đề cương ôn tập LTTHS theo từng chương.pdf",
        source_type="academic_reference"
    ),
    # 2026-08-29 batch: 10 of 12 newly-supplied PDFs (see requirements.md ingestion log).
    # Excluded from this batch:
    #  - "01_2026_TTLT-VKSNDTC-BCA-BQP_694946.pdf" (raw_documents/, unregistered on purpose):
    #    same number/date/title as the already-ingested "Thông tư liên tịch 01_2026 VKSND -
    #    BCA - BQP.pdf" above - confirmed duplicate, left un-renamed and un-parsed.
    #  - "Văn bản hợp nhất BLTTHS 2025 (104_VBHN-VPQH) - CHƯA INGEST.pdf": candidate
    #    replacement for "Bộ luật TTHS.pdf" above, pending a separate content-diff review
    #    before any replace decision - not registered here yet.
    DocumentConfig(
        filename="Quyết định 06_QĐ-VKSTC.pdf",
        source_type="legal_text",
        law_version="Quyết định 06/QĐ-VKSTC ngày 23/3/2026 (Quy chế công tác THQCT, kiểm sát khởi tố, điều tra và truy tố)"
    ),
    DocumentConfig(
        filename="Nghị quyết 05_2017_NQ-HĐTP.pdf",
        source_type="legal_text",
        law_version="Nghị quyết 05/2017/NQ-HĐTP"
    ),
    DocumentConfig(
        filename="Quyết định 505_QĐ-VKSTC.pdf",
        source_type="legal_text",
        law_version="Quyết định 505/QĐ-VKSTC ngày 18/12/2017 (Quy chế công tác THQCT, kiểm sát xét xử vụ án hình sự)"
    ),
    DocumentConfig(
        filename="Thông tư liên tịch 04_2025 BCA - VKSNDTC - TANDTC.pdf",
        source_type="legal_text",
        law_version="Thông tư liên tịch 04/2025/TTLT-BCA-VKSNDTC-TANDTC"
    ),
    DocumentConfig(
        filename="Thông tư liên tịch 02_2017 VKSNDTC - TANDTC - BCA - BQP.pdf",
        source_type="legal_text",
        law_version="Thông tư liên tịch 02/2017/TTLT-VKSNDTC-TANDTC-BCA-BQP"
    ),
    DocumentConfig(
        filename="Thông tư 02_2018_TT-TANDTC.pdf",
        source_type="legal_text",
        law_version="Thông tư 02/2018/TT-TANDTC"
    ),
    DocumentConfig(
        filename="Thông tư liên tịch 03_2018 BCA - VKSNDTC - TANDTC - BQP.pdf",
        source_type="legal_text",
        law_version="Thông tư liên tịch 03/2018/TTLT-BCA-VKSNDTC-TANDTC-BQP"
    ),
    DocumentConfig(
        filename="Thông tư liên tịch 08_2025 VKSNDTC - TANDTC - BCA - BTP - BYT.pdf",
        source_type="legal_text",
        law_version="Thông tư liên tịch 08/2025/TTLT-VKSNDTC-TANDTC-BCA-BTP-BYT"
    ),
    DocumentConfig(
        filename="Thông tư liên tịch 02_2018 BCA - VKSNDTC - TANDTC - BQP.pdf",
        source_type="legal_text",
        law_version="Thông tư liên tịch 02/2018/TTLT-BCA-VKSNDTC-TANDTC-BQP"
    ),
    DocumentConfig(
        filename="Thông tư liên tịch 29_2025 BTP - BCA - BQP - BTC - TANDTC - VKSNDTC.pdf",
        source_type="legal_text",
        law_version="Thông tư liên tịch 29/2025/TTLT-BTP-BCA-BQP-BTC-TANDTC-VKSNDTC"
    ),
]


def get_document_config(filename: str) -> DocumentConfig:
    for config in DOCUMENT_REGISTRY:
        if config.filename == filename:
            return config
    raise ValueError(f"No document_registry entry for file: {filename}")
