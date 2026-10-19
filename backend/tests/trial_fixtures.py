"""Shared fixtures for the mock-trial unit tests. Legal packs are built from the real
ingestion/chunks.json (the same payloads Qdrant holds), so the tests exercise real khoản/điểm text
without any network call. Case drafts are synthetic and written for the tests."""
from __future__ import annotations

import json
import unittest
from functools import lru_cache
from pathlib import Path

from app.models.trial import CaseDraft, CaseFile, CaseKnobs, CaseOptions, CourtInfo
from app.services.trial_config import get_crime
from app.services.trial_legal_pack import LegalPack, build_pack, pack_request_for_crime
from app.services.trial_names import COURT_ROLES, assign_names

CHUNKS_PATH = Path(__file__).resolve().parents[2] / "ingestion" / "chunks.json"


@lru_cache(maxsize=1)
def _chunks() -> tuple[dict, ...]:
    # chunks.json is gitignored (ingestion/chunks*.json): present on an ingestion machine, absent
    # in a fresh clone. Tests that need real legal text skip there instead of failing.
    if not CHUNKS_PATH.exists():
        raise unittest.SkipTest("ingestion/chunks.json not available")
    return tuple(json.loads(CHUNKS_PATH.read_text(encoding="utf-8")))


@lru_cache(maxsize=8)
def pack_for(crime_key: str) -> LegalPack:
    request = pack_request_for_crime(get_crime(crime_key))
    wanted = {(doc, d) for doc, numbers in request.items() for d in numbers}
    return build_pack(c for c in _chunks() if (c["source_document"], c["dieu_number"]) in wanted)


STATEMENT_BI_CAO = ("Tôi khai nhận khoảng 21 giờ tôi đi ngang qua nhà bị hại, thấy chiếc xe máy dựng trước cửa "
                    "không khóa cổ nên dắt đi. Tôi định bán lấy tiền tiêu xài, nhưng hôm sau thấy ân hận nên đã "
                    "mang xe trả lại và xin lỗi bị hại.")
STATEMENT_BI_HAI = ("Tôi để xe trước cửa nhà khoảng mười phút để vào lấy đồ. Khi quay ra thì không thấy xe đâu, "
                    "tôi hỏi hàng xóm rồi đến công an phường trình báo ngay trong đêm, đề nghị xử lý theo pháp luật.")
STATEMENT_NLC_1 = ("Tối hôm đó tôi ngồi uống nước ở quán đối diện, thấy một thanh niên mặc áo khoác đen dắt chiếc "
                   "xe đi về phía chợ. Lúc đầu tôi tưởng là người nhà nên không để ý, sau mới biết là bị lấy trộm.")
INDICTMENT = ("Viện kiểm sát nhân dân truy tố bị cáo {BI_CAO} về tội trộm cắp tài sản theo khoản 1 Điều 173 "
              "Bộ luật Hình sự, căn cứ Điều 243 Bộ luật Tố tụng hình sự. " + "Nội dung vụ án được trình bày "
              "đầy đủ theo hồ sơ, gồm diễn biến hành vi, chứng cứ thu thập được và nhân thân bị cáo. " * 25)


def _person(pid: str, **overrides) -> dict:
    base = {"id": pid, "gender": "nam", "age": 34, "occupation": "lao động tự do",
            "residence_place": "phường A, tỉnh X", "stance": "khai đúng sự việc",
            "statement_summary": "Trình bày diễn biến như đã khai.", "knowledge": ["Biết sự việc F1"],
            "demeanor": "bình tĩnh"}
    base.update(overrides)
    return base


def valid_draft_dict() -> dict:
    """Điều 173 khoản 1, property value 12.500.000 đồng, victim present, one witness."""
    return {
        "title": "Vụ trộm cắp chiếc xe máy tại phường A",
        "incident_summary": "{BI_CAO} lấy chiếc xe máy của {BI_HAI} trị giá 12.500.000 đồng.",
        "defendant": {**_person("BI_CAO", age=27, stance="nhận tội, xin giảm nhẹ"),
                      "education": "12/12", "prior_record": "không", "preventive_measure": "cấm đi khỏi nơi cư trú"},
        "victim": _person("BI_HAI", gender="nu", age=41, stance="yêu cầu bồi thường"),
        "witnesses": [_person("NLC_1", age=52, stance="chứng kiến một phần")],
        "related_party": None,
        "facts": [
            {"id": "F1", "time": "khoảng 21 giờ", "place": "phường A, tỉnh X",
             "description": "{BI_CAO} dắt chiếc xe máy của {BI_HAI} đang dựng trước nhà."},
            {"id": "F2", "time": "ngày hôm sau", "place": "phường B, tỉnh X",
             "description": "{BI_CAO} tự nguyện trả lại xe và bồi thường 2.000.000 đồng."},
        ],
        "evidence": [
            {"id": "E1", "type": "vat_chung", "description": "Chiếc xe máy", "value_vnd": None, "injury_percent": None},
            {"id": "E2", "type": "dinh_gia", "description": "Kết luận định giá tài sản",
             "value_vnd": 12500000, "injury_percent": None},
            {"id": "E3", "type": "tai_lieu", "description": "Biên bản thu giữ xe", "value_vnd": None,
             "injury_percent": None},
            {"id": "E4", "type": "tai_lieu", "description": "Giấy nhận tiền bồi thường", "value_vnd": None,
             "injury_percent": None, "fact_id": "F2"},
        ],
        "pretrial_statements": [
            {"person_id": "BI_CAO", "summary": STATEMENT_BI_CAO, "inconsistencies": [{"text": "Giờ lấy xe khai khác nhau", "claimed_amount_vnd": None}]},
            {"person_id": "BI_HAI", "summary": STATEMENT_BI_HAI, "inconsistencies": []},
            {"person_id": "NLC_1", "summary": STATEMENT_NLC_1, "inconsistencies": []},
        ],
        "charge": {"dieu": "173", "khoan": "1", "diem": [], "crime_name": "Tội trộm cắp tài sản"},
        "measure_value": 12500000,
        "defendant_plea": "nhan_toan_bo",
        "compensation_vnd": 2000000,
        "extra_amounts": [{"label": "Tiền bị cáo định bán xe", "amount_vnd": 7000000, "evidence_id": "E1"}],
        "mitigating": [{"khoan": "1", "diem": "b", "fact_ids": ["F2"]},
                       {"khoan": "1", "diem": "s", "fact_ids": ["F2"]}],
        "aggravating": [],
        "civil_claim": {"claimant_id": "BI_HAI", "amount_vnd": 2000000, "basis": "Chi phí sửa xe"},
        "indictment_text": INDICTMENT,
    }


def valid_knobs() -> CaseKnobs:
    return CaseKnobs(khoan="1", plea="nhan_toan_bo", has_compensation=True, aggravating_points=[],
                     mitigating_points=["b", "s"])


def valid_options() -> CaseOptions:
    return CaseOptions(crime_key="blhs_173", user_role="ksv", victim_present=True, witness_count=1)


def valid_case_file(options: CaseOptions | None = None, draft: dict | None = None) -> CaseFile:
    options = options or valid_options()
    model = CaseDraft.model_validate(draft or valid_draft_dict())
    people = [(pid, label, "nam") for pid, label in COURT_ROLES.items()]
    people += [("BI_CAO", "Bị cáo", "nam"), ("BI_HAI", "Bị hại", "nu"), ("NLC_1", "Người làm chứng", "nam")]
    return CaseFile(crime_key=options.crime_key, options=options, knobs=valid_knobs(),
                    court=CourtInfo(name="Tòa án nhân dân [test]", hearing_date="19/10/2026", venue="phường A, tỉnh X"),
                    incident_date="01/03/2026", participants=assign_names(people, seed=7, excluded=frozenset()),
                    draft=model)
