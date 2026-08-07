"""Static source_document -> natural display-name mapping (requirements.md "Feature - Polish
Chat" muc A). The raw filenames stored as chunk metadata (ingestion/document_registry.py) are
fine as an internal/storage identifier, but were leaking straight to students - both inside
LLM-generated answers (format_academic_context_block below feeds the raw filename into the
context block the model reads and can echo back) and in citation UI - as e.g.
"Giao-Trinh-Luat-Tố-Tụng-Hinh-Sự-Dh-Luat-Hn.pdf" instead of a readable document name.

Corpus is fixed-size and only grows via a manual ingestion CLI run (requirements.md mục 1 - no
admin UI, no runtime document upload), so a static mapping checked into source control is the
right tool here, not a DB table or dynamic derivation from the filename.

Kept as its own module (not inside rag_prompts.py) because it's used from multiple places that
must never show a raw filename to a student: prompt-building (rag_prompts.py), the aggregate
structure-question answer (rag_service.py), and the legal-article full-text response
(legal_service.py).
"""
from __future__ import annotations

# Mirrors ingestion/document_registry.py's DOCUMENT_REGISTRY filenames exactly - kept as a
# separate list (not imported from the ingestion package) since backend/ and ingestion/ are
# independently deployable per requirements.md mục 3 architecture, and this mapping is a
# display-only concern of the backend, not an ingestion-pipeline one.
SOURCE_DOCUMENT_DISPLAY_NAMES: dict[str, str] = {
    "Bộ luật TTHS.pdf": "Bộ luật Tố tụng Hình sự",
    "Văn bản hợp nhất BLHS 2015.pdf": "Bộ luật Hình sự (văn bản hợp nhất 2015)",
    "Nghị định 250_NĐ-CP.pdf": "Nghị định 250/2025/NĐ-CP",
    "Thông tư liên tịch 05.pdf": "Thông tư liên tịch 05/2026/TTLT-BCA-BQP-VKSNDTC-TANDTC",
    "Thông tư liên tịch 01_2026 VKSND - BCA - BQP.pdf": "Thông tư liên tịch 01/2026/TTLT-VKSNDTC-BCA-BQP",
    "Luật tổ chức toà án nhân dân.pdf": "Luật Tổ chức Tòa án nhân dân",
    "Giáo trình Luật Tố tụng hình sự -đã nén.pdf": "Giáo trình Luật Tố tụng Hình sự",
    "Nguồn bào chữa trong LTTHS.pdf": "Nguồn bào chữa trong Luật Tố tụng Hình sự",
    "Suy đoán người vô tội trong thực hành quyền công tố của BLTTHS.pdf": (
        "Suy đoán vô tội trong thực hành quyền công tố theo Bộ luật Tố tụng Hình sự"
    ),
    "Mối quan hệ và tính thống nhất giữa LHS & LTTHS.pdf": (
        "Mối quan hệ và tính thống nhất giữa Luật Hình sự và Luật Tố tụng Hình sự"
    ),
    (
        "Mối quan hệ GIỮA CƠ QUAN ĐIỀU TRA VÀ VIỆN KIỂM SÁT TRONG VIỆC ÁP DỤNG, "
        "THAY ĐỔI, HỦY BỎ BIỆN PHÁP NGĂN CHẶN TRONG GIAI ĐOẠN KHỞI TỐ VỤ ÁN HÌNH SỰ.pdf"
    ): "Mối quan hệ giữa Cơ quan điều tra và Viện kiểm sát trong áp dụng biện pháp ngăn chặn",
    "Chính sách LTTHS về bảo vệ quyền con người.pdf": (
        "Chính sách Luật Tố tụng Hình sự về bảo vệ quyền con người"
    ),
    "Bảo vệ quyền con người bằng TTHS.pdf": "Bảo vệ quyền con người bằng Luật Tố tụng Hình sự",
    "693495639-TINH-HUỐNG-TỐ-TỤNG-HINH-SỰ.pdf": "Tình huống Tố tụng Hình sự",
    "Giao-Trinh-Luat-Tố-Tụng-Hinh-Sự-Dh-Luat-Hn.pdf": (
        "Giáo trình Luật Tố tụng Hình sự - Đại học Luật Hà Nội"
    ),
    "784492208-ĐỀ-CƯƠNG-LUẬT-TỐ-TỤNG-HINH-SỰ.pdf": "Đề cương Luật Tố tụng Hình sự",
    "Đề cương ôn tập LTTHS theo từng chương.pdf": "Đề cương ôn tập Luật Tố tụng Hình sự theo từng chương",
}


def get_display_name(source_document: str) -> str:
    """Falls back to the filename with its extension stripped (not the raw filename as-is) if a
    new document is ingested before this mapping is updated for it - degrades to "readable but
    not pretty" instead of a hard error or a raw ".pdf"-suffixed name reaching a student."""
    if source_document in SOURCE_DOCUMENT_DISPLAY_NAMES:
        return SOURCE_DOCUMENT_DISPLAY_NAMES[source_document]
    return source_document.removesuffix(".pdf")
