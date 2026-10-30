"""Checks on the Chủ tọa's own decision (chặng R4, design doc Mục 11.4.4, plan KE-HOACH-CHU-TOA.md Mục 3).

Feedback, never a score (decision 17): an ERROR blocks "Chốt quyết định" because no real judgment
could contain it; a WARNING is shown and the student may still lock the decision. Every finding
names the field it is about and its legal basis, checked against ingestion/chunks.json.

These rules apply to the student's decision only (decision Q10): the AI nghị án of the other roles
keeps trial_verdict_guard.check_verdict unchanged, so their measured behaviour does not move. The
gaps found in that older guard (Điều 54 khoản 1 and 3, Điều 38, Điều 35, Điều 298) are listed as
backlog in the design doc, not fixed there.

Where the corpus is silent the rule stays a warning: the fee schedule (Nghị quyết 326/2016/UBTVQH14)
and the civil-law principle that compensation does not exceed the claim are not in the corpus.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.models.trial import CaseFile, ChairDecision
from app.services.trial_config import BLHS_DOCUMENT, FORBIDDEN_POINT_TEXT, get_crime
from app.services.trial_legal_pack import LegalPack
from app.services.trial_verdict_guard import (
    NON_CUSTODIAL_MIN_MONTHS,
    PROBATION_MAX_MONTHS,
    PROBATION_MIN_MONTHS,
    SUSPENDED_MAX_PRISON_MONTHS,
    PenaltyFrame,
    parse_penalty_frame,
)

BLHS = "Bộ luật Hình sự"
BLTTHS = "Bộ luật Tố tụng hình sự"
# BLHS Điều 38 khoản 1: "mức tối thiểu là 03 tháng và mức tối đa là 20 năm".
PRISON_MIN_MONTHS, PRISON_MAX_MONTHS = 3, 240
# BLHS Điều 35 khoản 3: "không được thấp hơn 1.000.000 đồng".
FINE_MIN_VND = 1_000_000
# BLHS Điều 9 khoản 1: "nghiêm trọng" ends at a frame maximum of 07 năm tù; cải tạo không giam giữ
# (Điều 36 khoản 1) and phạt tiền as the main penalty (Điều 35 khoản 1 điểm a) stop there.
SERIOUS_MAX_MONTHS = 84
DIEU_54_MIN_MITIGATING = 2
REASONING_MIN_CHARS, REASONING_MAX_CHARS = 200, 2000
CONFISCATIONS = frozenset({"tich_thu_sung_ngan_sach", "tich_thu_tieu_huy"})
# The khoản that list circumstances: Điều 51 khoản 1 (điểm a-x) and khoản 2 ("tình tiết khác", no
# điểm); Điều 52 khoản 1. Điều 51 khoản 3 and Điều 52 khoản 2 are rules about circumstances, not ones.
CIRCUMSTANCE_KHOANS = {"51": ("1", "2"), "52": ("1",)}


def is_penalty_khoan(article, khoan: str) -> bool:
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
class DecisionCheck:
    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    def error(self, code: str, field_: str, message: str, *basis: str) -> None:
        self.errors.append(Finding(code, field_, message, list(basis)))

    def warn(self, code: str, field_: str, message: str, *basis: str) -> None:
        self.warnings.append(Finding(code, field_, message, list(basis)))

    def as_dict(self) -> dict:
        return {"errors": [asdict(f) for f in self.errors], "warnings": [asdict(f) for f in self.warnings],
                "flags": list(self.flags)}

    @property
    def ok(self) -> bool:
        return not self.errors


def check_decision(decision: ChairDecision, case: CaseFile, pack: LegalPack) -> DecisionCheck:
    check = DecisionCheck()
    _circumstances(decision, case, pack, check)
    _reasoning(decision, check)
    _exhibits(decision, case, check)
    if decision.fine_vnd is not None and decision.penalty_type != "phat_tien":
        check.error("fine_not_main", "fine_vnd", "Chỉ ghi số tiền phạt khi hình phạt chính là phạt tiền; hình phạt "
                    "bổ sung chưa có trong bản mô phỏng.", f"khoản 1 Điều 35 {BLHS}")
    if decision.civil_amount_vnd is not None and decision.civil_amount_vnd < 0:
        check.error("civil_negative", "civil_amount_vnd", "Số tiền bồi thường không được âm.", f"khoản 1 Điều 48 {BLHS}")
    _civil(decision, case, check)
    if not decision.guilty:
        _acquittal(decision, case, check)
    else:
        _conviction(decision, case, pack, check)
    return check


# --- Parts of the check ---------------------------------------------------------------------------

def _circumstances(decision: ChairDecision, case: CaseFile, pack: LegalPack, check: DecisionCheck) -> None:
    fact_ids = {f.id for f in case.draft.facts}
    for label, dieu, items in (("mitigating", "51", decision.mitigating), ("aggravating", "52", decision.aggravating)):
        article = pack.get(BLHS_DOCUMENT, dieu)
        for index, item in enumerate(items):
            where = f"{label}[{index}]"
            if article is None or not article.has_khoan(item.khoan) or item.khoan not in CIRCUMSTANCE_KHOANS[dieu]:
                check.error("circumstance_unknown", where, f"Khoản {item.khoan} Điều {dieu} {BLHS} không tồn tại.",
                            f"Điều {dieu} {BLHS}")
            # A khoản without điểm (Điều 51 khoản 2, "tình tiết khác") takes an empty điểm.
            elif article.khoans[item.khoan].diem and (not item.diem or not article.has_diem(item.khoan, item.diem)):
                check.error("circumstance_unknown", where, f"Điểm {item.diem or '(trống)'} khoản {item.khoan} Điều "
                            f"{dieu} {BLHS} không tồn tại.", f"Điều {dieu} {BLHS}")
            if not item.fact_ids:
                check.error("circumstance_no_fact", where, "Mỗi tình tiết phải gắn với ít nhất một sự việc trong hồ sơ.",
                            f"khoản 2 Điều 326 {BLTTHS}")
            unknown = [f for f in item.fact_ids if f not in fact_ids]
            if unknown:
                check.error("circumstance_unknown_fact", where, f"Sự việc không có trong hồ sơ: {', '.join(unknown)}.",
                            f"khoản 2 Điều 326 {BLTTHS}")
    if any(m.khoan == "2" for m in decision.mitigating):
        check.warn("mitigating_other_reason", "mitigating", "Tình tiết giảm nhẹ theo khoản 2 Điều 51 phải được ghi rõ "
                   "lý do trong bản án: nêu lý do trong phần nhận định.", f"khoản 2 Điều 51 {BLHS}")
    if decision.guilty and decision.aggravating and decision.diem:
        check.warn("aggravating_frame_overlap", "aggravating", "Kiểm tra lại: tình tiết đã là dấu hiệu định khung hình "
                   "phạt thì không được coi là tình tiết tăng nặng.", f"khoản 2 Điều 52 {BLHS}")


def _reasoning(decision: ChairDecision, check: DecisionCheck) -> None:
    length = len(decision.reasoning_summary.strip())
    if not REASONING_MIN_CHARS <= length <= REASONING_MAX_CHARS:
        check.error("reasoning_length", "reasoning_summary", f"Nhận định cần từ {REASONING_MIN_CHARS} đến "
                    f"{REASONING_MAX_CHARS} ký tự (hiện có {length}).", f"điểm d khoản 2 Điều 260 {BLTTHS}")


def _exhibits(decision: ChairDecision, case: CaseFile, check: DecisionCheck) -> None:
    physical = [e.id for e in case.draft.evidence if e.type == "vat_chung"]
    given = [x.evidence_id for x in decision.exhibits]
    basis = (f"điểm e khoản 3 Điều 326 {BLTTHS}", f"khoản 1 Điều 106 {BLTTHS}")
    for evidence_id in given:
        if evidence_id not in physical:
            check.error("exhibit_unknown", "exhibits", f"{evidence_id} không phải vật chứng trong hồ sơ.", *basis)
    if len(given) != len(set(given)):
        check.error("exhibit_duplicate", "exhibits", "Mỗi vật chứng chỉ có một cách xử lý.", *basis)
    missing = [e for e in physical if e not in given]
    if missing:
        check.error("exhibit_missing", "exhibits", f"Chưa quyết định xử lý vật chứng: {', '.join(missing)}.", *basis)
    if get_crime(case.crime_key).measure == "value_vnd" and any(x.disposition in CONFISCATIONS
                                                                  for x in decision.exhibits):
        check.warn("exhibit_confiscated_property", "exhibits", "Nếu vật chứng là tài sản bị chiếm đoạt thì không tịch "
                   "thu mà trả lại cho chủ sở hữu hoặc người quản lý hợp pháp.", f"khoản 2 Điều 47 {BLHS}",
                   f"khoản 2, khoản 3 Điều 106 {BLTTHS}")


def _civil(decision: ChairDecision, case: CaseFile, check: DecisionCheck) -> None:
    amount = decision.civil_amount_vnd or 0
    claim = case.draft.civil_claim
    # Soft only (decision Q11): "không vượt yêu cầu" is a civil-law rule the corpus does not hold.
    if amount > 0 and (claim is None or amount > claim.amount_vnd):
        check.warn("civil_over_claim", "civil_amount_vnd", "Số tiền bồi thường lớn hơn số tiền bị hại yêu cầu trong hồ "
                   "sơ.", f"Điều 30 {BLTTHS}", f"khoản 1 Điều 48 {BLHS}")
    if decision.defendant_pays_civil_fee and amount <= 0:
        check.warn("civil_fee_without_claim", "defendant_pays_civil_fee", "Không có khoản bồi thường nào được quyết "
                   "định mà vẫn chọn án phí dân sự.", f"khoản 2 Điều 135 {BLTTHS}")


def _acquittal(decision: ChairDecision, case: CaseFile, check: DecisionCheck) -> None:
    if decision.penalty_type != "khong" or decision.suspended:
        check.error("acquittal_with_penalty", "penalty_type", "Tuyên không phạm tội thì không có hình phạt và không có "
                    "án treo.", f"điểm c, d khoản 3 Điều 326 {BLTTHS}")
    if decision.defendant_pays_criminal_fee:
        check.error("acquittal_criminal_fee", "defendant_pays_criminal_fee", "Bị cáo không có tội thì không phải chịu "
                    "án phí hình sự: án phí do người bị kết án hoặc Nhà nước chịu.", f"khoản 2 Điều 136 {BLTTHS}")
    charge = case.draft.charge
    if charge.dieu == "134" and charge.khoan == "1":
        check.warn("acquittal_victim_fee", "defendant_pays_criminal_fee", "Vụ án khởi tố theo yêu cầu của bị hại (khoản "
                   "1 Điều 134 Bộ luật Hình sự): nếu bị cáo không có tội thì bị hại phải trả án phí.",
                   f"khoản 3 Điều 136 {BLTTHS}", f"khoản 1 Điều 155 {BLTTHS}")


def _frame_text(frame: PenaltyFrame) -> str:
    return f"{frame.prison_min_months}-{frame.prison_max_months} tháng tù"


def _conviction(decision: ChairDecision, case: CaseFile, pack: LegalPack, check: DecisionCheck) -> None:
    charge = case.draft.charge
    if decision.dieu != charge.dieu:
        check.error("charge_article", "dieu", f"Chỉ được xét xử theo Điều {charge.dieu} {BLHS} mà Viện kiểm sát đã truy "
                    "tố.", f"khoản 1 Điều 298 {BLTTHS}")
        return
    article = pack.get(BLHS_DOCUMENT, decision.dieu)
    if article is None or not article.has_khoan(decision.khoan) or not is_penalty_khoan(article, decision.khoan):
        check.error("khoan_unknown", "khoan", f"Khoản {decision.khoan} Điều {decision.dieu} {BLHS} không phải khoản quy "
                    "định khung hình phạt của tội này.", f"Điều {decision.dieu} {BLHS}")
        return
    # Decision Q9: the corpus text of Điều 298 khoản 2 allows "khoản khác ... trong cùng một điều luật"
    # without saying lighter, so a heavier khoản is a warning, not an error.
    if int(decision.khoan) > int(charge.khoan):
        check.warn("khoan_heavier", "khoan", f"Khoản {decision.khoan} nặng hơn khoản {charge.khoan} mà Viện kiểm sát "
                   "đã truy tố. Khoản 2 Điều 298 cho phép xét xử theo khoản khác trong cùng điều luật; kiểm tra lại "
                   "căn cứ.", f"khoản 2 Điều 298 {BLTTHS}", f"khoản 3 Điều 298 {BLTTHS}")
    khoan = article.khoans[decision.khoan]
    for letter in decision.diem:
        if not article.has_diem(decision.khoan, letter):
            check.error("diem_unknown", "diem", f"Điểm {letter} không có trong khoản {decision.khoan} Điều "
                        f"{decision.dieu} {BLHS}.", f"Điều {decision.dieu} {BLHS}")
        elif FORBIDDEN_POINT_TEXT.search(khoan.diem_text(letter)):
            check.error("diem_minor", "diem", f"Điểm {letter} liên quan người dưới 18 tuổi, ngoài phạm vi mô phỏng.",
                        f"Điều {decision.dieu} {BLHS}")
    if decision.penalty_type == "khong":
        check.error("conviction_without_penalty", "penalty_type", "Đã tuyên có tội thì phải có hình phạt (miễn hình "
                    "phạt không thuộc phạm vi mô phỏng).", f"điểm d khoản 3 Điều 326 {BLTTHS}", f"Điều 59 {BLHS}")
        return

    frame = parse_penalty_frame(khoan)
    lowest = min(article.khoans, key=int) == decision.khoan
    lighter_key = str(int(decision.khoan) - 1)
    lighter = parse_penalty_frame(article.khoans[lighter_key]) if not lowest and lighter_key in article.khoans else None
    strong = sum(1 for m in decision.mitigating if m.khoan == "1")
    dieu_54_ok = decision.applies_dieu_54 and strong >= DIEU_54_MIN_MITIGATING
    if decision.applies_dieu_54 and strong < DIEU_54_MIN_MITIGATING:
        check.error("dieu54_conditions", "applies_dieu_54", "Áp dụng Điều 54 cần ít nhất hai tình tiết giảm nhẹ tại "
                    "khoản 1 Điều 51.", f"khoản 1 Điều 54 {BLHS}")
    if frame is None:
        check.flags.append("penalty_unchecked")
        check.warn("penalty_unchecked", "penalty_type", "Hệ thống chưa kiểm được khung hình phạt của khoản này.",
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
            check.error("suspended_prison", "suspended", "Án treo chỉ áp dụng khi xử phạt tù không quá 03 năm.",
                        f"khoản 1 Điều 65 {BLHS}")
        if decision.probation_months is None or not PROBATION_MIN_MONTHS <= decision.probation_months \
                <= PROBATION_MAX_MONTHS:
            check.error("probation_range", "probation_months", "Thời gian thử thách của án treo từ 01 năm đến 05 năm.",
                        f"khoản 1 Điều 65 {BLHS}")
        if not decision.mitigating:
            check.warn("suspended_without_mitigating", "suspended", "Cho hưởng án treo căn cứ vào nhân thân và các tình "
                       "tiết giảm nhẹ; quyết định chưa nêu tình tiết giảm nhẹ nào.", f"khoản 1 Điều 65 {BLHS}")
    elif decision.probation_months is not None:
        check.error("probation_without_suspension", "probation_months", "Chỉ ấn định thời gian thử thách khi cho hưởng "
                    "án treo.", f"khoản 1 Điều 65 {BLHS}")
    measure = case.draft.defendant.preventive_measure.lower()
    if "tạm giam" in measure and (decision.penalty_type != "tu" or decision.suspended):
        check.warn("release_needed", "penalty_type", "Bị cáo đang bị tạm giam mà hình phạt không phải tù hoặc được hưởng "
                   "án treo: Hội đồng xét xử phải tuyên trả tự do ngay tại phiên tòa.", f"Điều 328 {BLTTHS}")


def _prison(decision: ChairDecision, months: int | None, frame: PenaltyFrame | None, lighter: PenaltyFrame | None,
            lowest: bool, check: DecisionCheck) -> None:
    if months is None or months <= 0:
        check.error("penalty_months", "penalty_months", "Cần nhập số tháng tù lớn hơn 0.", f"khoản 1 Điều 38 {BLHS}")
        return
    if not PRISON_MIN_MONTHS <= months <= PRISON_MAX_MONTHS:
        check.error("prison_general_range", "penalty_months", "Tù có thời hạn từ 03 tháng đến 20 năm.",
                    f"khoản 1 Điều 38 {BLHS}")
    if frame is None:
        return
    if months > frame.prison_max_months:
        check.error("above_frame", "penalty_months", f"Mức tù {months} tháng vượt mức cao nhất của khung "
                    f"({_frame_text(frame)}).", f"Điều {decision.dieu} {BLHS}")
    elif months < frame.prison_min_months:
        if not decision.applies_dieu_54:
            check.error("below_frame", "penalty_months", f"Mức tù {months} tháng dưới mức thấp nhất của khung "
                        f"({_frame_text(frame)}) mà không áp dụng Điều 54.", f"khoản 1 Điều 54 {BLHS}")
        elif not lowest and lighter is not None and months < lighter.prison_min_months:
            check.error("below_adjacent_frame", "penalty_months", f"Áp dụng Điều 54 thì mức tù vẫn phải trong khung "
                        f"hình phạt liền kề nhẹ hơn (thấp nhất {lighter.prison_min_months} tháng).",
                        f"khoản 1 Điều 54 {BLHS}")
        elif not lowest and lighter is None:
            check.flags.append("penalty_unchecked")
            check.warn("adjacent_frame_unchecked", "penalty_months", "Hệ thống chưa kiểm được khung liền kề nhẹ hơn.",
                       f"khoản 1 Điều 54 {BLHS}")


def _non_custodial(months: int | None, frame: PenaltyFrame | None, lighter: PenaltyFrame | None, lowest: bool,
                   dieu_54_ok: bool, check: DecisionCheck) -> None:
    if months is None or not NON_CUSTODIAL_MIN_MONTHS <= months <= 36:
        check.error("non_custodial_range", "penalty_months", "Cải tạo không giam giữ từ 06 tháng đến 03 năm.",
                    f"khoản 1 Điều 36 {BLHS}")
    if frame is None:
        return
    if frame.prison_max_months > SERIOUS_MAX_MONTHS:
        check.error("non_custodial_class", "penalty_type", "Cải tạo không giam giữ chỉ áp dụng với tội ít nghiêm trọng "
                    "hoặc nghiêm trọng.", f"khoản 1 Điều 36 {BLHS}", f"khoản 1 Điều 9 {BLHS}")
        return
    if frame.non_custodial_max_months is not None:
        if months is not None and months > frame.non_custodial_max_months:
            check.error("non_custodial_frame", "penalty_months", f"Cải tạo không giam giữ của khoản này tối đa "
                        f"{frame.non_custodial_max_months} tháng.", f"khoản 1 Điều 36 {BLHS}")
        return
    # Not in this khoản: only through Điều 54 - into the adjacent lighter frame when it has this
    # penalty (khoản 1), or as "a lighter kind of penalty" when this is the lightest frame (khoản 3).
    lighter_has_it = lighter is not None and lighter.non_custodial_max_months is not None
    if not dieu_54_ok or not (lowest or lighter_has_it):
        check.error("non_custodial_not_in_frame", "penalty_type", "Khung hình phạt của khoản này không có cải tạo "
                    "không giam giữ; chỉ chuyển được khi đủ điều kiện Điều 54.", f"khoản 1, khoản 3 Điều 54 {BLHS}")


def _fine(decision: ChairDecision, frame: PenaltyFrame | None, lowest: bool, dieu_54_ok: bool,
          check: DecisionCheck) -> None:
    if decision.fine_vnd is None or decision.fine_vnd < FINE_MIN_VND:
        check.error("fine_min", "fine_vnd", "Mức phạt tiền không được thấp hơn 1.000.000 đồng.", f"khoản 3 Điều 35 {BLHS}")
    if frame is None or frame.fine_as_main:
        return
    if frame.prison_max_months > SERIOUS_MAX_MONTHS or not (lowest and dieu_54_ok):
        check.error("fine_not_in_frame", "penalty_type", "Khung hình phạt của khoản này không có phạt tiền là hình phạt "
                    "chính.", f"khoản 1 Điều 35 {BLHS}", f"khoản 3 Điều 54 {BLHS}")
