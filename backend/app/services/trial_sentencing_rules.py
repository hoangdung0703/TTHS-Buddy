"""Legal checks on a sentencing decision - ONE source of truth for both deciders (nhóm B, design doc
Mục 11.16):
- the Chủ tọa's own decision form (trial_chair_decision.check_decision): a hard finding blocks
  "Chốt quyết định", a soft one is a warning the student may override;
- the AI nghị án of every other role (trial_verdict_guard.check_verdict): a hard finding rejects the
  decision and regenerates it (then the hearing pauses), a soft one is only measured (logged).

Every rule has a code, a fixed severity in RULES and a legal basis checked against
ingestion/chunks.json (BLHS: "Văn bản hợp nhất BLHS 2015.pdf", BLTTHS: "Bộ luật TTHS.pdf"). Where the
corpus is silent the rule is soft: the fee schedule (Nghị quyết 326/2016/UBTVQH14), the civil-law
principle that compensation does not exceed the claim, and the finer conditions of án treo are not in
the corpus. Điều 298 khoản 2 BLTTHS allows "khoản khác ... trong cùng một điều luật" without saying
lighter, so a heavier khoản of the charged Điều is soft as well.

The checks were written for the Chủ tọa (chặng R4) and moved here unchanged; check order and messages
are what the Chủ tọa form shows, so they must not move without updating its tests.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Literal

from app.models.trial import CaseFile, ChairDecision, Verdict
from app.services.trial_config import BLHS_DOCUMENT, FORBIDDEN_POINT_TEXT, get_crime
from app.services.trial_legal_pack import Khoan, LegalArticle, LegalPack

BLHS = "Bộ luật Hình sự"
BLTTHS = "Bộ luật Tố tụng hình sự"

# --- Phần chung limits (BLHS), encoded rather than parsed: stable text the legal team reviews here ----
# Điều 38 khoản 1: "mức tối thiểu là 03 tháng và mức tối đa là 20 năm".
PRISON_MIN_MONTHS, PRISON_MAX_MONTHS = 3, 240
# Điều 35 khoản 3: "không được thấp hơn 1.000.000 đồng".
FINE_MIN_VND = 1_000_000
# Điều 36 khoản 1: "từ 06 tháng đến 03 năm".
NON_CUSTODIAL_MIN_MONTHS, NON_CUSTODIAL_MAX_MONTHS = 6, 36
# Điều 9 khoản 1 điểm b: "nghiêm trọng" ends at a frame maximum of 07 năm tù; cải tạo không giam giữ
# (Điều 36 khoản 1) and phạt tiền as the main penalty (Điều 35 khoản 1 điểm a) stop there.
SERIOUS_MAX_MONTHS = 84
# Điều 65 khoản 1: án treo "khi xử phạt tù không quá 03 năm", thử thách "từ 01 năm đến 05 năm".
SUSPENDED_MAX_PRISON_MONTHS = 36
PROBATION_MIN_MONTHS, PROBATION_MAX_MONTHS = 12, 60
# Điều 54 khoản 1: "ít nhất hai tình tiết giảm nhẹ quy định tại khoản 1 Điều 51".
DIEU_54_MIN_MITIGATING = 2
# The khoản that list circumstances: Điều 51 khoản 1 (điểm a-x) and khoản 2 ("tình tiết khác", no
# điểm); Điều 52 khoản 1. Điều 51 khoản 3 and Điều 52 khoản 2 are rules about circumstances, not ones.
CIRCUMSTANCE_KHOANS = {"51": ("1", "2"), "52": ("1",)}
CONFISCATIONS = frozenset({"tich_thu_sung_ngan_sach", "tich_thu_tieu_huy"})

Severity = Literal["hard", "soft"]

# Code -> severity: the single table both deciders read. Basis per rule is in the message's `basis`.
RULES: dict[str, Severity] = {
    # Circumstances (Điều 51 khoản 1-2, Điều 52 khoản 1 BLHS; khoản 2 Điều 326 BLTTHS)
    "circumstance_unknown": "hard", "circumstance_no_fact": "hard", "circumstance_unknown_fact": "hard",
    "mitigating_other_reason": "soft", "aggravating_frame_overlap": "soft",
    # Charge limits (Điều 298 BLTTHS) and the article text
    "charge_article": "hard", "khoan_unknown": "hard", "khoan_heavier": "soft",
    "diem_unknown": "hard", "diem_minor": "hard",
    # Penalty
    "conviction_without_penalty": "hard", "penalty_unchecked": "soft",
    "penalty_months": "hard", "prison_general_range": "hard", "above_frame": "hard", "below_frame": "hard",
    "below_adjacent_frame": "hard", "adjacent_frame_unchecked": "soft", "dieu54_conditions": "hard",
    "non_custodial_range": "hard", "non_custodial_class": "hard", "non_custodial_frame": "hard",
    "non_custodial_not_in_frame": "hard",
    "fine_min": "hard", "fine_not_in_frame": "hard", "fine_not_main": "hard",
    # Án treo (Điều 65 khoản 1 BLHS)
    "suspended_prison": "hard", "probation_range": "hard", "probation_without_suspension": "hard",
    "suspended_without_mitigating": "soft",
    # Acquittal, release, civil, exhibits, fees
    "acquittal_with_penalty": "hard", "release_needed": "soft",
    "civil_negative": "hard", "civil_over_claim": "soft",
    "exhibit_unknown": "hard", "exhibit_duplicate": "hard", "exhibit_missing": "hard",
    "exhibit_confiscated_property": "soft",
    "acquittal_criminal_fee": "hard", "acquittal_victim_fee": "soft", "civil_fee_without_claim": "soft",
    # Form of the Chủ tọa's nhận định (điểm d khoản 2 Điều 260 BLTTHS); the AI decision has no such field check.
    "reasoning_length": "hard",
}

_UNIT_MONTHS = {"năm": 12, "tháng": 1}
_PRISON_RANGE = re.compile(r"phạt\s+tù\s+từ\s+(\d+)\s+(năm|tháng)\s+đến\s+(\d+)\s+(năm|tháng)", re.IGNORECASE)
_NON_CUSTODIAL = re.compile(r"cải\s+tạo\s+không\s+giam\s+giữ\s+đến\s+(\d+)\s+(năm|tháng)", re.IGNORECASE)
_FINE_MAIN = re.compile(r"phạt\s+tiền\s+từ", re.IGNORECASE)


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


def is_penalty_khoan(article: LegalArticle, khoan: str) -> bool:
    """A khoản that sets a main penalty frame. The last khoản of the crime articles ("Người phạm tội còn
    có thể bị phạt tiền ...") lists additional penalties only and is never the khoản a verdict applies."""
    head = article.khoans[khoan].head.lower()
    return "còn có thể bị" not in head and ("phạt tù" in head or "phạt tiền" in head or "cải tạo" in head)


@dataclass(frozen=True)
class Finding:
    code: str
    field: str
    message: str
    basis: list[str]


@dataclass
class RuleCheck:
    """Findings of one decision: `errors` hold the hard rules, `warnings` the soft ones (RULES)."""
    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    def add(self, code: str, field_: str, message: str, *basis: str) -> None:
        finding = Finding(code, field_, message, list(basis))
        (self.errors if RULES[code] == "hard" else self.warnings).append(finding)

    def as_dict(self) -> dict:
        return {"errors": [asdict(f) for f in self.errors], "warnings": [asdict(f) for f in self.warnings],
                "flags": list(self.flags)}

    @property
    def ok(self) -> bool:
        return not self.errors


# --- Rules shared by both deciders -----------------------------------------------------------------

def circumstances(decision: Verdict, case: CaseFile, pack: LegalPack, check: RuleCheck) -> None:
    fact_ids = {f.id for f in case.draft.facts}
    for label, dieu, items in (("mitigating", "51", decision.mitigating), ("aggravating", "52", decision.aggravating)):
        article = pack.get(BLHS_DOCUMENT, dieu)
        for index, item in enumerate(items):
            where = f"{label}[{index}]"
            if article is None or not article.has_khoan(item.khoan) or item.khoan not in CIRCUMSTANCE_KHOANS[dieu]:
                check.add("circumstance_unknown", where, f"Khoản {item.khoan} Điều {dieu} {BLHS} không tồn tại.",
                          f"Điều {dieu} {BLHS}")
            # A khoản without điểm (Điều 51 khoản 2, "tình tiết khác") takes an empty điểm.
            elif article.khoans[item.khoan].diem and (not item.diem or not article.has_diem(item.khoan, item.diem)):
                check.add("circumstance_unknown", where, f"Điểm {item.diem or '(trống)'} khoản {item.khoan} Điều "
                          f"{dieu} {BLHS} không tồn tại.", f"Điều {dieu} {BLHS}")
            if not item.fact_ids:
                check.add("circumstance_no_fact", where, "Mỗi tình tiết phải gắn với ít nhất một sự việc trong hồ sơ.",
                          f"khoản 2 Điều 326 {BLTTHS}")
            unknown = [f for f in item.fact_ids if f not in fact_ids]
            if unknown:
                check.add("circumstance_unknown_fact", where, f"Sự việc không có trong hồ sơ: {', '.join(unknown)}.",
                          f"khoản 2 Điều 326 {BLTTHS}")
    if any(m.khoan == "2" for m in decision.mitigating):
        check.add("mitigating_other_reason", "mitigating", "Tình tiết giảm nhẹ theo khoản 2 Điều 51 phải được ghi rõ "
                  "lý do trong bản án: nêu lý do trong phần nhận định.", f"khoản 2 Điều 51 {BLHS}")
    if decision.guilty and decision.aggravating and decision.diem:
        check.add("aggravating_frame_overlap", "aggravating", "Kiểm tra lại: tình tiết đã là dấu hiệu định khung hình "
                  "phạt thì không được coi là tình tiết tăng nặng.", f"khoản 2 Điều 52 {BLHS}")


def fine_and_civil_amounts(decision: Verdict, case: CaseFile, check: RuleCheck) -> None:
    if decision.fine_vnd is not None and decision.penalty_type != "phat_tien":
        check.add("fine_not_main", "fine_vnd", "Chỉ ghi số tiền phạt khi hình phạt chính là phạt tiền; hình phạt "
                  "bổ sung chưa có trong bản mô phỏng.", f"khoản 1 Điều 35 {BLHS}")
    if decision.civil_amount_vnd is not None and decision.civil_amount_vnd < 0:
        check.add("civil_negative", "civil_amount_vnd", "Số tiền bồi thường không được âm.", f"khoản 1 Điều 48 {BLHS}")


def civil_over_claim(decision: Verdict, case: CaseFile, check: RuleCheck) -> None:
    amount = decision.civil_amount_vnd or 0
    claim = case.draft.civil_claim
    # Soft (decision Q11): "không vượt yêu cầu" is a civil-law rule the corpus does not hold.
    if amount > 0 and (claim is None or amount > claim.amount_vnd):
        check.add("civil_over_claim", "civil_amount_vnd", "Số tiền bồi thường lớn hơn số tiền bị hại yêu cầu trong hồ "
                  "sơ.", f"Điều 30 {BLTTHS}", f"khoản 1 Điều 48 {BLHS}")


def acquittal_penalty(decision: Verdict, check: RuleCheck) -> None:
    if decision.penalty_type != "khong" or decision.suspended:
        check.add("acquittal_with_penalty", "penalty_type", "Tuyên không phạm tội thì không có hình phạt và không có "
                  "án treo.", f"điểm c, d khoản 3 Điều 326 {BLTTHS}")


def _frame_text(frame: PenaltyFrame) -> str:
    return f"{frame.prison_min_months}-{frame.prison_max_months} tháng tù"


def lighter_frame(article: LegalArticle, khoan: str) -> tuple[bool, PenaltyFrame | None]:
    """(is the lightest khoản, frame of the adjacent lighter khoản) - Điều 54 khoản 1 and 3."""
    lowest = min(article.khoans, key=int) == khoan
    lighter_key = str(int(khoan) - 1)
    lighter = parse_penalty_frame(article.khoans[lighter_key]) if not lowest and lighter_key in article.khoans else None
    return lowest, lighter


def conviction(decision: Verdict, case: CaseFile, pack: LegalPack, check: RuleCheck) -> None:
    charge = case.draft.charge
    if decision.dieu != charge.dieu:
        check.add("charge_article", "dieu", f"Chỉ được xét xử theo Điều {charge.dieu} {BLHS} mà Viện kiểm sát đã truy "
                  "tố.", f"khoản 1 Điều 298 {BLTTHS}")
        return
    article = pack.get(BLHS_DOCUMENT, decision.dieu)
    if article is None or not article.has_khoan(decision.khoan) or not is_penalty_khoan(article, decision.khoan):
        check.add("khoan_unknown", "khoan", f"Khoản {decision.khoan} Điều {decision.dieu} {BLHS} không phải khoản quy "
                  "định khung hình phạt của tội này.", f"Điều {decision.dieu} {BLHS}")
        return
    # Decision Q9: the corpus text of Điều 298 khoản 2 allows "khoản khác ... trong cùng một điều luật"
    # without saying lighter, so a heavier khoản is soft.
    if int(decision.khoan) > int(charge.khoan):
        check.add("khoan_heavier", "khoan", f"Khoản {decision.khoan} nặng hơn khoản {charge.khoan} mà Viện kiểm sát "
                  "đã truy tố. Khoản 2 Điều 298 cho phép xét xử theo khoản khác trong cùng điều luật; kiểm tra lại "
                  "căn cứ.", f"khoản 2 Điều 298 {BLTTHS}", f"khoản 3 Điều 298 {BLTTHS}")
    khoan = article.khoans[decision.khoan]
    for letter in decision.diem:
        if not article.has_diem(decision.khoan, letter):
            check.add("diem_unknown", "diem", f"Điểm {letter} không có trong khoản {decision.khoan} Điều "
                      f"{decision.dieu} {BLHS}.", f"Điều {decision.dieu} {BLHS}")
        elif FORBIDDEN_POINT_TEXT.search(khoan.diem_text(letter)):
            check.add("diem_minor", "diem", f"Điểm {letter} liên quan người dưới 18 tuổi, ngoài phạm vi mô phỏng.",
                      f"Điều {decision.dieu} {BLHS}")
    if decision.penalty_type == "khong":
        check.add("conviction_without_penalty", "penalty_type", "Đã tuyên có tội thì phải có hình phạt (miễn hình "
                  "phạt không thuộc phạm vi mô phỏng).", f"điểm d khoản 3 Điều 326 {BLTTHS}", f"Điều 59 {BLHS}")
        return

    frame = parse_penalty_frame(khoan)
    lowest, lighter = lighter_frame(article, decision.khoan)
    strong = sum(1 for m in decision.mitigating if m.khoan == "1")
    dieu_54_ok = decision.applies_dieu_54 and strong >= DIEU_54_MIN_MITIGATING
    if decision.applies_dieu_54 and strong < DIEU_54_MIN_MITIGATING:
        check.add("dieu54_conditions", "applies_dieu_54", "Áp dụng Điều 54 cần ít nhất hai tình tiết giảm nhẹ tại "
                  "khoản 1 Điều 51.", f"khoản 1 Điều 54 {BLHS}")
    if frame is None:
        check.flags.append("penalty_unchecked")
        check.add("penalty_unchecked", "penalty_type", "Hệ thống chưa kiểm được khung hình phạt của khoản này.",
                  f"Điều {decision.dieu} {BLHS}")

    months = decision.penalty_months
    if decision.penalty_type == "tu":
        _prison(decision, months, frame, lighter, lowest, check)
    elif decision.penalty_type == "cai_tao_khong_giam_giu":
        _non_custodial(months, frame, lighter, lowest, dieu_54_ok, check)
    elif decision.penalty_type == "phat_tien":
        _fine(decision, frame, lowest, dieu_54_ok, check)

    if decision.suspended:
        if decision.penalty_type != "tu" or (months or 0) > SUSPENDED_MAX_PRISON_MONTHS:
            check.add("suspended_prison", "suspended", "Án treo chỉ áp dụng khi xử phạt tù không quá 03 năm.",
                      f"khoản 1 Điều 65 {BLHS}")
        if decision.probation_months is None or not PROBATION_MIN_MONTHS <= decision.probation_months \
                <= PROBATION_MAX_MONTHS:
            check.add("probation_range", "probation_months", "Thời gian thử thách của án treo từ 01 năm đến 05 năm.",
                      f"khoản 1 Điều 65 {BLHS}")
        if not decision.mitigating:
            check.add("suspended_without_mitigating", "suspended", "Cho hưởng án treo căn cứ vào nhân thân và các tình "
                      "tiết giảm nhẹ; quyết định chưa nêu tình tiết giảm nhẹ nào.", f"khoản 1 Điều 65 {BLHS}")
    elif decision.probation_months is not None:
        check.add("probation_without_suspension", "probation_months", "Chỉ ấn định thời gian thử thách khi cho hưởng "
                  "án treo.", f"khoản 1 Điều 65 {BLHS}")
    measure = case.draft.defendant.preventive_measure.lower()
    if "tạm giam" in measure and (decision.penalty_type != "tu" or decision.suspended):
        check.add("release_needed", "penalty_type", "Bị cáo đang bị tạm giam mà hình phạt không phải tù hoặc được hưởng "
                  "án treo: Hội đồng xét xử phải tuyên trả tự do ngay tại phiên tòa.", f"Điều 328 {BLTTHS}")


def _prison(decision: Verdict, months: int | None, frame: PenaltyFrame | None, lighter: PenaltyFrame | None,
            lowest: bool, check: RuleCheck) -> None:
    if months is None or months <= 0:
        check.add("penalty_months", "penalty_months", "Cần nhập số tháng tù lớn hơn 0.", f"khoản 1 Điều 38 {BLHS}")
        return
    if not PRISON_MIN_MONTHS <= months <= PRISON_MAX_MONTHS:
        check.add("prison_general_range", "penalty_months", "Tù có thời hạn từ 03 tháng đến 20 năm.",
                  f"khoản 1 Điều 38 {BLHS}")
    if frame is None:
        return
    if months > frame.prison_max_months:
        check.add("above_frame", "penalty_months", f"Mức tù {months} tháng vượt mức cao nhất của khung "
                  f"({_frame_text(frame)}).", f"Điều {decision.dieu} {BLHS}")
    elif months < frame.prison_min_months:
        if not decision.applies_dieu_54:
            check.add("below_frame", "penalty_months", f"Mức tù {months} tháng dưới mức thấp nhất của khung "
                      f"({_frame_text(frame)}) mà không áp dụng Điều 54.", f"khoản 1 Điều 54 {BLHS}")
        elif not lowest and lighter is not None and months < lighter.prison_min_months:
            check.add("below_adjacent_frame", "penalty_months", f"Áp dụng Điều 54 thì mức tù vẫn phải trong khung "
                      f"hình phạt liền kề nhẹ hơn (thấp nhất {lighter.prison_min_months} tháng).",
                      f"khoản 1 Điều 54 {BLHS}")
        elif not lowest and lighter is None:
            check.flags.append("penalty_unchecked")
            check.add("adjacent_frame_unchecked", "penalty_months", "Hệ thống chưa kiểm được khung liền kề nhẹ hơn.",
                      f"khoản 1 Điều 54 {BLHS}")


def _non_custodial(months: int | None, frame: PenaltyFrame | None, lighter: PenaltyFrame | None, lowest: bool,
                   dieu_54_ok: bool, check: RuleCheck) -> None:
    if months is None or not NON_CUSTODIAL_MIN_MONTHS <= months <= NON_CUSTODIAL_MAX_MONTHS:
        check.add("non_custodial_range", "penalty_months", "Cải tạo không giam giữ từ 06 tháng đến 03 năm.",
                  f"khoản 1 Điều 36 {BLHS}")
    if frame is None:
        return
    if frame.prison_max_months > SERIOUS_MAX_MONTHS:
        check.add("non_custodial_class", "penalty_type", "Cải tạo không giam giữ chỉ áp dụng với tội ít nghiêm trọng "
                  "hoặc nghiêm trọng.", f"khoản 1 Điều 36 {BLHS}", f"khoản 1 Điều 9 {BLHS}")
        return
    if frame.non_custodial_max_months is not None:
        if months is not None and months > frame.non_custodial_max_months:
            check.add("non_custodial_frame", "penalty_months", f"Cải tạo không giam giữ của khoản này tối đa "
                      f"{frame.non_custodial_max_months} tháng.", f"khoản 1 Điều 36 {BLHS}")
        return
    # Not in this khoản: only through Điều 54 - into the adjacent lighter frame when it has this
    # penalty (khoản 1), or as "a lighter kind of penalty" when this is the lightest frame (khoản 3).
    lighter_has_it = lighter is not None and lighter.non_custodial_max_months is not None
    if not dieu_54_ok or not (lowest or lighter_has_it):
        check.add("non_custodial_not_in_frame", "penalty_type", "Khung hình phạt của khoản này không có cải tạo "
                  "không giam giữ; chỉ chuyển được khi đủ điều kiện Điều 54.", f"khoản 1, khoản 3 Điều 54 {BLHS}")


def _fine(decision: Verdict, frame: PenaltyFrame | None, lowest: bool, dieu_54_ok: bool, check: RuleCheck) -> None:
    if decision.fine_vnd is None or decision.fine_vnd < FINE_MIN_VND:
        check.add("fine_min", "fine_vnd", "Mức phạt tiền không được thấp hơn 1.000.000 đồng.", f"khoản 3 Điều 35 {BLHS}")
    if frame is None or frame.fine_as_main:
        return
    if frame.prison_max_months > SERIOUS_MAX_MONTHS or not (lowest and dieu_54_ok):
        check.add("fine_not_in_frame", "penalty_type", "Khung hình phạt của khoản này không có phạt tiền là hình phạt "
                  "chính.", f"khoản 1 Điều 35 {BLHS}", f"khoản 3 Điều 54 {BLHS}")


# --- Rules on fields only the Chủ tọa's form carries (exhibits, court fees) ------------------------

def exhibits(decision: ChairDecision, case: CaseFile, check: RuleCheck) -> None:
    physical = [e.id for e in case.draft.evidence if e.type == "vat_chung"]
    given = [x.evidence_id for x in decision.exhibits]
    basis = (f"điểm e khoản 3 Điều 326 {BLTTHS}", f"khoản 1 Điều 106 {BLTTHS}")
    for evidence_id in given:
        if evidence_id not in physical:
            check.add("exhibit_unknown", "exhibits", f"{evidence_id} không phải vật chứng trong hồ sơ.", *basis)
    if len(given) != len(set(given)):
        check.add("exhibit_duplicate", "exhibits", "Mỗi vật chứng chỉ có một cách xử lý.", *basis)
    missing = [e for e in physical if e not in given]
    if missing:
        check.add("exhibit_missing", "exhibits", f"Chưa quyết định xử lý vật chứng: {', '.join(missing)}.", *basis)
    if get_crime(case.crime_key).measure == "value_vnd" and any(x.disposition in CONFISCATIONS
                                                                  for x in decision.exhibits):
        check.add("exhibit_confiscated_property", "exhibits", "Nếu vật chứng là tài sản bị chiếm đoạt thì không tịch "
                  "thu mà trả lại cho chủ sở hữu hoặc người quản lý hợp pháp.", f"khoản 2 Điều 47 {BLHS}",
                  f"khoản 2, khoản 3 Điều 106 {BLTTHS}")


def civil_fee(decision: ChairDecision, check: RuleCheck) -> None:
    if decision.defendant_pays_civil_fee and (decision.civil_amount_vnd or 0) <= 0:
        check.add("civil_fee_without_claim", "defendant_pays_civil_fee", "Không có khoản bồi thường nào được quyết "
                  "định mà vẫn chọn án phí dân sự.", f"khoản 2 Điều 135 {BLTTHS}")


def acquittal_fees(decision: ChairDecision, case: CaseFile, check: RuleCheck) -> None:
    if decision.defendant_pays_criminal_fee:
        check.add("acquittal_criminal_fee", "defendant_pays_criminal_fee", "Bị cáo không có tội thì không phải chịu "
                  "án phí hình sự: án phí do người bị kết án hoặc Nhà nước chịu.", f"khoản 2 Điều 136 {BLTTHS}")
    charge = case.draft.charge
    if charge.dieu == "134" and charge.khoan == "1":
        check.add("acquittal_victim_fee", "defendant_pays_criminal_fee", "Vụ án khởi tố theo yêu cầu của bị hại (khoản "
                  "1 Điều 134 Bộ luật Hình sự): nếu bị cáo không có tội thì bị hại phải trả án phí.",
                  f"khoản 3 Điều 136 {BLTTHS}", f"khoản 1 Điều 155 {BLTTHS}")


# --- The AI nghị án: the shared rules on the Verdict fields -----------------------------------------

def check_ai_decision(decision: Verdict, case: CaseFile, pack: LegalPack) -> RuleCheck:
    """Every shared rule that applies to the Verdict fields, in the Chủ tọa's order."""
    check = RuleCheck()
    circumstances(decision, case, pack, check)
    fine_and_civil_amounts(decision, case, check)
    civil_over_claim(decision, case, check)
    if not decision.guilty:
        acquittal_penalty(decision, check)
    else:
        conviction(decision, case, pack, check)
    return check


def _months_text(months: int) -> str:
    return f"{months} tháng"


def hard_constraints_text(case: CaseFile, pack: LegalPack) -> str:
    """The hard limits of THIS case, computed by code from the charged khoản and Phần chung BLHS, for the
    nghị án prompt: the model is told the numbers instead of deriving them. Empty when the frame of the
    charged khoản cannot be parsed (then nothing is asserted)."""
    charge = case.draft.charge
    article = pack.get(BLHS_DOCUMENT, charge.dieu)
    if article is None or not article.has_khoan(charge.khoan):
        return ""
    frame = parse_penalty_frame(article.khoans[charge.khoan])
    if frame is None:
        return ""
    lowest, lighter = lighter_frame(article, charge.khoan)
    serious = frame.prison_max_months <= SERIOUS_MAX_MONTHS
    lines = [
        f"- Khung của khoản {charge.khoan} Điều {charge.dieu} Bộ luật Hình sự đã truy tố: phạt tù từ "
        f"{_months_text(frame.prison_min_months)} đến {_months_text(frame.prison_max_months)}"
        + (f"; hoặc cải tạo không giam giữ từ {NON_CUSTODIAL_MIN_MONTHS} đến "
           f"{_months_text(frame.non_custodial_max_months)}" if frame.non_custodial_max_months else "")
        + ". Xét xử theo khoản khác của cùng Điều chỉ khi chứng cứ tại phiên tòa chứng minh "
          "(khoản 2 Điều 298 Bộ luật Tố tụng hình sự).",
        f"- Phạt tù tối thiểu {PRISON_MIN_MONTHS} tháng (khoản 1 Điều 38 Bộ luật Hình sự).",
    ]
    if lowest:
        lines.append("- Đây là khung nhẹ nhất của Điều luật: chỉ khi áp dụng Điều 54 (ít nhất hai tình tiết giảm "
                     "nhẹ tại khoản 1 Điều 51) mới được xử dưới mức thấp nhất của khung hoặc chuyển sang hình phạt "
                     "khác thuộc loại nhẹ hơn (khoản 3 Điều 54 Bộ luật Hình sự).")
    elif lighter is not None:
        lines.append(f"- Dưới mức thấp nhất của khung chỉ khi áp dụng Điều 54 (ít nhất hai tình tiết giảm nhẹ tại "
                     f"khoản 1 Điều 51) và vẫn phải trong khung liền kề nhẹ hơn: phạt tù không dưới "
                     f"{_months_text(lighter.prison_min_months)}"
                     + (", hoặc cải tạo không giam giữ" if lighter.non_custodial_max_months and serious else "")
                     + " (khoản 1 Điều 54 Bộ luật Hình sự).")
    if not serious:
        lines.append("- Tội thuộc khoản này không phải tội ít nghiêm trọng hoặc nghiêm trọng: không được phạt cải tạo "
                     "không giam giữ, không phạt tiền là hình phạt chính (Điều 9, Điều 35, Điều 36 Bộ luật Hình sự).")
    lines += [
        f"- Cải tạo không giam giữ: penalty_months từ {NON_CUSTODIAL_MIN_MONTHS} đến {NON_CUSTODIAL_MAX_MONTHS} "
        f"(khoản 1 Điều 36 Bộ luật Hình sự). Phạt tiền là hình phạt chính: fine_vnd không dưới {FINE_MIN_VND} "
        "(khoản 3 Điều 35 Bộ luật Hình sự); ngoài trường hợp đó fine_vnd để null.",
        f"- Án treo: chỉ khi phạt tù không quá {SUSPENDED_MAX_PRISON_MONTHS} tháng; probation_months từ "
        f"{PROBATION_MIN_MONTHS} đến {PROBATION_MAX_MONTHS}; không có án treo thì probation_months để null "
        "(khoản 1 Điều 65 Bộ luật Hình sự).",
        "- Tình tiết giảm nhẹ chỉ thuộc khoản 1 Điều 51 (kèm điểm) hoặc khoản 2 Điều 51 (diem để trống); tình tiết "
        "tăng nặng chỉ thuộc khoản 1 Điều 52 (kèm điểm). Mỗi tình tiết có ít nhất một fact_id trong hồ sơ.",
    ]
    return "RÀNG BUỘC CỨNG CỦA VỤ ÁN NÀY (hệ thống đã tính sẵn):\n" + "\n".join(lines)
