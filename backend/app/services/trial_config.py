"""Configuration for "Phiên tòa giả định" (docs/phien-toa-gia-dinh/THIET-KE.md).

Everything the legal team is expected to review lives here as plain data: the crime whitelist,
which khoản of each crime a learning case may be built on, the value/injury bands that decide
the khoản, the court name and the limits. Code elsewhere reads these and
never hardcodes a crime, a khoản or a threshold of its own.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

BLHS_DOCUMENT = "Văn bản hợp nhất BLHS 2015.pdf"
BLTTHS_DOCUMENT = "Bộ luật TTHS.pdf"

# Display names used in prompts and accepted by the Rule 9 pair guard. Kept short on purpose: the
# prompt asks every citation to carry one of these exact forms.
LAW_SHORT_NAMES: dict[str, str] = {
    BLHS_DOCUMENT: "Bộ luật Hình sự",
    BLTTHS_DOCUMENT: "Bộ luật Tố tụng hình sự",
}

# Court of first instance for every learning case. BLTTHS Điều 268 khoản 1 (amended by Luật
# 99/2025/QH15) gives Tòa án nhân dân khu vực first-instance jurisdiction over crimes whose highest
# penalty bracket is at most 20 years; every allowed khoản below is (highest: 10 years, Điều 171
# khoản 2). Luật Tổ chức TAND 34/2024 Điều 4 khoản 1 điểm c names the level; "khu vực 1, tỉnh X"
# keeps the abstract province of ABSTRACT_PLACES. Overridable through TRIAL_COURT_NAME.
DEFAULT_COURT_NAME = "Tòa án nhân dân khu vực 1, tỉnh X"
COURT_PREFIX = "Tòa án nhân dân "
PROCURACY_PREFIX = "Viện kiểm sát nhân dân "
# Stored by cases generated before chặng R1; shown as the configured court instead.
LEGACY_COURT_PLACEHOLDER = "Tòa án nhân dân [tên Tòa án chờ nhóm luật xác nhận]"


def court_name(settings: object) -> str:
    """The configured court name; unset or blank means DEFAULT_COURT_NAME."""
    configured = (getattr(settings, "trial_court_name", None) or "").strip()
    return configured or DEFAULT_COURT_NAME


def procuracy_name(court: str) -> str:
    """The prosecutor office paired with a court. BLTTHS Điều 239 khoản 1 ties the power to
    prosecute to the court competent to try the case, so it is the same-level Viện kiểm sát:
    "Tòa án nhân dân khu vực 1, tỉnh X" -> "Viện kiểm sát nhân dân khu vực 1, tỉnh X"."""
    if not court.startswith(COURT_PREFIX) or court == LEGACY_COURT_PLACEHOLDER:
        court = DEFAULT_COURT_NAME
    return PROCURACY_PREFIX + court.removeprefix(COURT_PREFIX)

# Abstract place names (decision 2026-10-19): never a real ward/province.
ABSTRACT_PLACES: tuple[str, ...] = (
    "phường A, tỉnh X", "phường B, tỉnh X", "xã C, tỉnh X", "phường D, tỉnh Y", "xã E, tỉnh Y",
)

# Limits (decision 2026-10-19). Enforced by the session repository (chặng 2).
MAX_CASES_PER_DAY = 5
# Cases created per Vietnam calendar day by ALL users together (decision 2026-10-29, Mục 11.8 item
# 22). Overridable through TRIAL_GLOBAL_DAILY_CASE_LIMIT.
DEFAULT_GLOBAL_DAILY_CASE_LIMIT = 100
MAX_ACTIVE_SESSIONS = 3
ABANDON_AFTER_DAYS = 14

# Model policy (decision 2026-10-19): settings.gemini_chat_model only, never the complex model.
# Thinking "low" only for the three calls that decide something; ordinary dialogue sends no
# thinking config at all.
THINKING_LEVEL_DECISION = "low"

# Any khoản/điểm whose own text matches this is off limits for a learning case: no minors in any
# role and no circumstance built on a victim's age (decision 2026-10-19). Checked against the real
# chunk text, so a point like Điều 134 khoản 1 điểm c ("Đối với người dưới 16 tuổi...") is
# rejected without anyone having to list it by hand.
FORBIDDEN_POINT_TEXT = re.compile(r"dưới\s+1[68]\s+tuổi|chưa\s+thành\s+niên|trẻ\s+em", re.IGNORECASE)

# Penalty patterns that disqualify a khoản from the whitelist entirely.
FORBIDDEN_PENALTY_TEXT = re.compile(r"tử\s+hình", re.IGNORECASE)

MIN_PERSON_AGE = 18
MAX_PERSON_AGE = 80


@dataclass(frozen=True)
class ValueBand:
    """A property-value (VND) or injury-percent range and the khoản/điểm it requires.

    `low` inclusive, `high` exclusive (None = no upper bound). `required_khoan` is the khoản the
    charge must be under when the number falls in this band; `required_diem` (optional) a điểm the
    charge must list. `allowed=False` marks a band the learning cases must not reach."""
    low: int
    high: int | None
    required_khoan: tuple[str, ...]
    required_diem: str | None = None
    allowed: bool = True


@dataclass(frozen=True)
class CrimeConfig:
    key: str
    dieu: str
    crime_name: str
    # Which khoản a generated case may charge under. Restricted to the lower khoản for a
    # first-instance learning case; the legal team may widen it.
    allowed_khoan: tuple[str, ...]
    # "value_vnd" for property crimes, "injury_percent" for Điều 134.
    measure: str
    bands: tuple[ValueBand, ...] = field(default_factory=tuple)
    has_victim_by_nature: bool = True


_FIFTY_M = 50_000_000
_TWO_HUNDRED_M = 200_000_000

_PROPERTY_BANDS = (
    ValueBand(0, _FIFTY_M, ("1", "2")),
    ValueBand(_FIFTY_M, _TWO_HUNDRED_M, ("2",), required_diem="c"),
    ValueBand(_TWO_HUNDRED_M, None, (), allowed=False),
)

# Decision 2026-10-19: 173, 174, 134, 171 only.
CRIMES: dict[str, CrimeConfig] = {
    "blhs_173": CrimeConfig("blhs_173", "173", "Tội trộm cắp tài sản", ("1", "2"), "value_vnd", _PROPERTY_BANDS),
    "blhs_174": CrimeConfig("blhs_174", "174", "Tội lừa đảo chiếm đoạt tài sản", ("1", "2"), "value_vnd",
                            _PROPERTY_BANDS),
    "blhs_171": CrimeConfig("blhs_171", "171", "Tội cướp giật tài sản", ("1", "2"), "value_vnd", _PROPERTY_BANDS),
    "blhs_134": CrimeConfig(
        "blhs_134", "134",
        "Tội cố ý gây thương tích hoặc gây tổn hại cho sức khỏe của người khác",
        ("1", "2"), "injury_percent",
        (
            ValueBand(1, 11, ("1",)),
            ValueBand(11, 31, ("1", "2")),
            ValueBand(31, 61, ("2",), required_diem="a"),
            ValueBand(61, None, (), allowed=False),
        ),
    ),
}

# Phần chung BLHS + BLTTHS articles every case carries (design doc Mục 4). BLTTHS is keyed by step
# group so a turn only sees its own slice.
BLHS_GENERAL_PART: tuple[str, ...] = ("32", "35", "36", "38", "46", "47", "48", "50", "51", "52", "54", "65")

# 243 (quyết định truy tố bằng bản cáo trạng) is what an indictment cites as its own basis. 13 (suy đoán
# vô tội) and 106 (xử lý vật chứng) were cited naturally by the defence/prosecution in the B4 rerun
# (2026-10-19) and rejected only because no slice held them; they now belong to the speech slices.
BLTTHS_ROLE_ARTICLES: tuple[str, ...] = ("13", "42", "45", "46", "47", "61", "62", "65", "66", "72", "73", "106",
                                         "243")

BLTTHS_STEP_SLICES: dict[str, tuple[str, ...]] = {
    "opening": tuple(str(n) for n in range(288, 307)),       # steps 1-3
    "questioning": tuple(str(n) for n in range(307, 319)),   # steps 4-5
    # steps 6-11; 331/333 so the tuyên án can state the right to appeal and its time limit.
    "closing": tuple(str(n) for n in range(319, 330)) + ("258", "260", "298", "331", "333"),
}

STEP_TO_SLICE: dict[int, str] = {1: "opening", 2: "opening", 3: "opening", 4: "questioning",
                                 5: "questioning", **{s: "closing" for s in range(6, 12)}}


def get_crime(crime_key: str) -> CrimeConfig:
    try:
        return CRIMES[crime_key]
    except KeyError as error:
        raise ValueError(f"Unknown or disallowed crime_key: {crime_key}") from error


# --- Diversity knobs (chặng 2, A2) -----------------------------------------------------------------
# Code, not the model, decides the shape of each case: khoản, plea, aggravating yes/no, compensation
# yes/no, and which Điều 51 points apply. The pools below are CANDIDATES for the legal team to
# review; every point is also re-checked against the real Điều 51/52 text and the minors filter.

Plea = str  # "nhan_toan_bo" | "nhan_mot_phan" | "choi_toi"
PLEAS: tuple[str, ...] = ("nhan_toan_bo", "nhan_mot_phan", "choi_toi")
PLEA_LABELS: dict[str, str] = {
    "nhan_toan_bo": "nhận tội toàn bộ",
    "nhan_mot_phan": "nhận một phần hành vi, chối một phần",
    "choi_toi": "không nhận tội",
}

# Điều 51 khoản 1 points that fit a single adult defendant in these four crimes. Conditions:
# b needs compensation; r/s need a full admission; t needs at least a partial admission;
# i ("lần đầu, ít nghiêm trọng") only under a khoản whose maximum is <= 3 years; e only for 134.
MITIGATING_POOL: tuple[str, ...] = ("a", "b", "e", "g", "h", "i", "r", "s", "t", "v", "x")
MITIGATING_NEEDS_COMPENSATION = frozenset({"b"})
MITIGATING_NEEDS_FULL_ADMISSION = frozenset({"r", "s"})
MITIGATING_NEEDS_SOME_ADMISSION = frozenset({"t"})
MITIGATING_LESS_SERIOUS_ONLY = frozenset({"i"})
MITIGATING_CRIME_ONLY: dict[str, frozenset[str]] = {"e": frozenset({"134"})}
# Khoản whose maximum penalty is <= 3 years (tội ít nghiêm trọng, BLHS Điều 9).
LESS_SERIOUS_KHOAN: dict[str, frozenset[str]] = {"173": frozenset({"1"}), "174": frozenset({"1"}),
                                                 "134": frozenset({"1"}), "171": frozenset()}

# Điều 52 khoản 1 points per crime, excluding those that are already định khung elements of the
# allowed khoản (Điều 52 khoản 2: no double counting) - e.g. "có tổ chức"/"chuyên nghiệp" for the
# property crimes' khoản 2, "côn đồ" for Điều 134.
AGGRAVATING_POOL: dict[str, tuple[str, ...]] = {
    "173": ("g", "h", "l"),
    "174": ("g", "h", "l"),
    "171": ("g", "h", "l"),
    "134": ("đ", "g", "h"),
}

MIN_EVIDENCE = 4
MIN_INDICTMENT_WORDS = 300
MIN_STATEMENT_WORDS = 25
# Two pre-trial statements whose word sets overlap at least this much count as the same content.
MAX_STATEMENT_SIMILARITY = 0.7


# --- Per-slot legal slices (chặng 2, A4) -----------------------------------------------------------
# Spike 2026-10-19: long-speech prompts carried the whole closing slice (all of Phần chung BLHS plus
# BLTTHS 319-333), ~17K tokens median. Each slot below loads only what that speech needs; "@charge"
# stands for the charged Điều. Slots not listed fall back to the step-group slice.
CHARGE = "@charge"
_SENTENCING = (CHARGE, "50", "51", "52", "54", "65", "38", "36", "35", "46", "47", "48")
SLOT_LEGAL_SLICES: dict[str, dict[str, tuple[str, ...]]] = {
    "luan_toi": {BLTTHS_DOCUMENT: ("106", "319", "320", "321"), BLHS_DOCUMENT: _SENTENCING},
    "bao_chua": {BLTTHS_DOCUMENT: ("13", "320", "322"), BLHS_DOCUMENT: (CHARGE, "50", "51", "54", "65", "36", "38")},
    "doi_dap": {BLTTHS_DOCUMENT: ("13", "322", "323"), BLHS_DOCUMENT: (CHARGE, "51", "52", "54", "65")},
    "nghi_an": {BLTTHS_DOCUMENT: ("298", "326"), BLHS_DOCUMENT: _SENTENCING},
    "tuyen_an": {BLTTHS_DOCUMENT: ("106", "260", "298", "327", "331", "333"), BLHS_DOCUMENT: _SENTENCING},
    "bi_hai_trinh_bay": {BLTTHS_DOCUMENT: ("320",), BLHS_DOCUMENT: (CHARGE,)},
    "loi_sau_cung": {BLTTHS_DOCUMENT: ("324",), BLHS_DOCUMENT: (CHARGE,)},
}
# KSV answering the defendant's tranh luận turn (chặng R3) argues like the đối đáp.
SLOT_LEGAL_SLICES["bi_cao_tranh_luan"] = SLOT_LEGAL_SLICES["doi_dap"]
