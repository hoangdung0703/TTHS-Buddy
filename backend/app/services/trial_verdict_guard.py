"""Checks on the structured nghị án decision before any tuyên án text is written (design doc
Mục 5.2). Hard errors block (the decision is regenerated once, then the hearing pauses); the only
soft outcome is the `penalty_unchecked` flag, raised when the penalty frame of the chosen khoản
cannot be parsed with certainty - decision 2026-10-19: block only on a confident parse.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models.trial import CaseFile, Verdict
from app.services.trial_config import BLHS_DOCUMENT, FORBIDDEN_POINT_TEXT, get_crime
from app.services.trial_case_validator import evidence_fact_map, remap_fact_ids
from app.services.trial_legal_pack import Khoan, LegalPack

_UNIT_MONTHS = {"năm": 12, "tháng": 1}
_PRISON_RANGE = re.compile(r"phạt\s+tù\s+từ\s+(\d+)\s+(năm|tháng)\s+đến\s+(\d+)\s+(năm|tháng)", re.IGNORECASE)
_NON_CUSTODIAL = re.compile(r"cải\s+tạo\s+không\s+giam\s+giữ\s+đến\s+(\d+)\s+(năm|tháng)", re.IGNORECASE)
_FINE_MAIN = re.compile(r"phạt\s+tiền\s+từ", re.IGNORECASE)

# BLHS Điều 36 (cải tạo không giam giữ: 06 tháng - 03 năm) and Điều 65 (án treo: tù không quá
# 03 năm, thời gian thử thách 01 - 05 năm). Encoded here rather than parsed: these Phần chung
# limits are stable and the legal team reviews this file (design doc Mục 9 item 5).
NON_CUSTODIAL_MIN_MONTHS = 6
SUSPENDED_MAX_PRISON_MONTHS = 36
PROBATION_MIN_MONTHS, PROBATION_MAX_MONTHS = 12, 60
# BLHS Điều 54 khoản 1: at least two mitigating circumstances of Điều 51 khoản 1.
DIEU_54_MIN_MITIGATING = 2


@dataclass(frozen=True)
class PenaltyFrame:
    prison_min_months: int
    prison_max_months: int
    non_custodial_max_months: int | None
    fine_as_main: bool


def parse_penalty_frame(khoan: Khoan) -> PenaltyFrame | None:
    """Only the khoản's own sentence (before its điểm) states the frame. Exactly one prison range
    must be present for the parse to count as certain; anything else returns None."""
    head = khoan.head
    ranges = _PRISON_RANGE.findall(head)
    if len(ranges) != 1:
        return None
    low, low_unit, high, high_unit = ranges[0]
    non_custodial = _NON_CUSTODIAL.search(head)
    return PenaltyFrame(
        prison_min_months=int(low) * _UNIT_MONTHS[low_unit],
        prison_max_months=int(high) * _UNIT_MONTHS[high_unit],
        non_custodial_max_months=(int(non_custodial.group(1)) * _UNIT_MONTHS[non_custodial.group(2)]
                                  if non_custodial else None),
        fine_as_main=bool(_FINE_MAIN.search(head.split("phạt tù")[0])),
    )


@dataclass
class VerdictCheck:
    errors: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def normalise_verdict(verdict: Verdict, case: CaseFile) -> Verdict:
    """Same repair as at case generation: an evidence id cited as a fact becomes its linked fact."""
    fact_ids = {f.id for f in case.draft.facts}
    by_evidence = evidence_fact_map(case.draft.evidence, fact_ids)

    def fix(items):
        return [i.model_copy(update={"fact_ids": remap_fact_ids(i.fact_ids, fact_ids, by_evidence)}) for i in items]
    return verdict.model_copy(update={"mitigating": fix(verdict.mitigating), "aggravating": fix(verdict.aggravating)})


def check_verdict(verdict: Verdict, case: CaseFile, pack: LegalPack) -> VerdictCheck:
    result = VerdictCheck()
    errors = result.errors
    charge = case.draft.charge
    crime = get_crime(case.crime_key)
    fact_ids = {f.id for f in case.draft.facts}

    for label, dieu, items in (("mitigating", "51", verdict.mitigating), ("aggravating", "52", verdict.aggravating)):
        article = pack.get(BLHS_DOCUMENT, dieu)
        for item in items:
            if article is None or not article.has_khoan(item.khoan):
                errors.append(f"{label}: khoản {item.khoan} Điều {dieu} không tồn tại")
            elif item.diem and not article.has_diem(item.khoan, item.diem):
                errors.append(f"{label}: điểm {item.diem} khoản {item.khoan} Điều {dieu} không tồn tại")
            for fid in item.fact_ids:
                if fid not in fact_ids:
                    errors.append(f"{label}: fact_id không tồn tại {fid}")

    if not verdict.guilty:
        if verdict.penalty_type != "khong" or verdict.suspended:
            errors.append("Tuyên không phạm tội thì penalty_type phải là 'khong' và không có án treo")
        return result

    # Điều 298 BLTTHS: same Điều; the charged khoản or a lower (lighter) allowed khoản.
    if verdict.dieu != charge.dieu:
        errors.append(f"Chỉ được xét xử theo Điều {charge.dieu} đã truy tố (Điều 298 BLTTHS)")
        return result
    if verdict.khoan not in crime.allowed_khoan or int(verdict.khoan) > int(charge.khoan):
        errors.append(f"Khoản {verdict.khoan} vượt giới hạn xét xử; chỉ khoản {charge.khoan} hoặc khoản nhẹ hơn")
        return result
    article = pack.get(BLHS_DOCUMENT, verdict.dieu)
    if article is None or not article.has_khoan(verdict.khoan):
        errors.append(f"Khoản {verdict.khoan} Điều {verdict.dieu} không có trong văn bản luật")
        return result
    khoan = article.khoans[verdict.khoan]
    for letter in verdict.diem:
        if not article.has_diem(verdict.khoan, letter):
            errors.append(f"Điểm {letter} không có trong khoản {verdict.khoan} Điều {verdict.dieu}")
        elif FORBIDDEN_POINT_TEXT.search(khoan.diem_text(letter)):
            errors.append(f"Điểm {letter} liên quan người dưới 18 tuổi, không được dùng")

    if verdict.penalty_type == "khong":
        errors.append("Đã tuyên có tội thì phải có hình phạt (miễn hình phạt không thuộc phạm vi mô phỏng)")
        return result

    frame = parse_penalty_frame(khoan)
    if frame is None:
        result.flags.append("penalty_unchecked")
    elif verdict.penalty_type == "tu":
        months = verdict.penalty_months
        if months is None or months <= 0:
            errors.append("penalty_months phải là số tháng tù > 0")
        elif months > frame.prison_max_months:
            errors.append(f"Mức tù {months} tháng vượt mức cao nhất của khung ({frame.prison_max_months} tháng)")
        elif months < frame.prison_min_months:
            strong_mitigating = [m for m in verdict.mitigating if m.khoan == "1"]
            if not verdict.applies_dieu_54:
                errors.append(f"Mức tù {months} tháng dưới mức thấp nhất của khung ({frame.prison_min_months} "
                              f"tháng) mà không áp dụng Điều 54 BLHS")
            elif len(strong_mitigating) < DIEU_54_MIN_MITIGATING:
                errors.append("Áp dụng Điều 54 BLHS cần ít nhất 2 tình tiết giảm nhẹ tại khoản 1 Điều 51")
    elif verdict.penalty_type == "cai_tao_khong_giam_giu":
        months = verdict.penalty_months
        if frame.non_custodial_max_months is None:
            errors.append("Khung hình phạt của khoản này không có cải tạo không giam giữ")
        elif months is None or not NON_CUSTODIAL_MIN_MONTHS <= months <= frame.non_custodial_max_months:
            errors.append(f"Cải tạo không giam giữ phải từ {NON_CUSTODIAL_MIN_MONTHS} đến "
                          f"{frame.non_custodial_max_months} tháng")
    elif verdict.penalty_type == "phat_tien" and not frame.fine_as_main:
        errors.append("Khoản này không có phạt tiền là hình phạt chính")

    if verdict.suspended:
        if verdict.penalty_type != "tu" or (verdict.penalty_months or 0) > SUSPENDED_MAX_PRISON_MONTHS:
            errors.append("Án treo chỉ áp dụng với mức phạt tù không quá 03 năm (Điều 65 BLHS)")
        if verdict.probation_months is None or not PROBATION_MIN_MONTHS <= verdict.probation_months <= PROBATION_MAX_MONTHS:
            errors.append("Thời gian thử thách của án treo phải từ 01 đến 05 năm")
    return result
