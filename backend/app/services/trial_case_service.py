"""Case generation for "Phiên tòa giả định" (design doc Mục 3.2, 4).

Flow: deterministic legal pack by key (Qdrant, no embedding) -> one Gemini call with thinking
"low" and a responseSchema -> Pydantic CaseDraft -> code validator -> on failure ONE retry with
the validator's errors -> code-assigned names -> CaseFile. If the retry also fails, creation fails
and nothing is stored.

stream_create_case yields (event, payload) pairs in the same shape notes_ask_service uses, so the
POST /api/trials route (chặng 2) only adds auth, limits, SSE transport and persistence.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date, timedelta

from pydantic import ValidationError
from qdrant_client import QdrantClient

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.chat import ChatStreamStatusEvent
from app.models.trial import (
    CASE_DRAFT_RESPONSE_SCHEMA,
    CaseDraft,
    CaseFile,
    CaseKnobs,
    CaseOptions,
    CourtInfo,
)
from app.prompts.trial_prompts import (
    CASE_GENERATION_SYSTEM_PROMPT,
    build_case_generation_prompt,
    build_case_repair_prompt,
)
from app.services.trial_case_repair import REPAIR_SCHEMA, RepairNotApplied, apply_repair, repair_plan
from app.services.trial_case_validator import (
    DIACRITIC_ERROR,
    declared_amounts,
    declared_percents,
    error_label,
    expected_person_ids,
    normalise_draft_dict,
    validate_case_draft,
)
from app.services.trial_config import (
    ABSTRACT_PLACES,
    BLHS_DOCUMENT,
    BLTTHS_DOCUMENT,
    DEFAULT_COURT_NAME,
    PLEA_LABELS,
    THINKING_LEVEL_DECISION,
    CrimeConfig,
    get_crime,
)
from app.services.trial_legal_pack import LegalPack, build_pack, fetch_payloads, missing_keys, pack_request_for_crime
from app.services.trial_metrics import TrialCallRecorder
from app.services.trial_knobs import choose_knobs
from app.services.trial_names import COURT_ROLES, assign_names

logger = get_logger(__name__)

# First try, then at most ONE field repair, then a full regeneration; a third call only while the
# whole creation is still under THIRD_ATTEMPT_MAX_ELAPSED seconds (chặng 3G: target median <= 25 s).
# A repair that does not fix the draft therefore costs one short call, never the regeneration the
# previous policy (generate + regenerate) always had.
MAX_GENERATION_ATTEMPTS = 3
THIRD_ATTEMPT_MAX_ELAPSED = 30.0
CASE_TEMPERATURE = 0.8
CASE_REPAIR_TEMPERATURE = 0.4
INCIDENT_DAYS_BEFORE_HEARING = (150, 300)

STATUS_PREPARING = "Đang chuẩn bị hồ sơ pháp lý của vụ án..."
STATUS_DRAFTING = "Đang dựng hồ sơ vụ án giả định..."
STATUS_CHECKING = "Đang kiểm tra hồ sơ với văn bản luật..."


class CaseGenerationFailed(Exception):
    """Both attempts failed. Log `error_counts` only; `errors` (validator messages, which can quote
    short field values of the generated case) are for offline analysis, never for logs."""

    def __init__(self, errors_per_attempt: list[list[str]]):
        super().__init__(f"case generation failed after {len(errors_per_attempt)} attempts")
        self.errors = errors_per_attempt
        self.error_counts = [len(e) for e in errors_per_attempt]


@dataclass
class CaseCreation:
    case: CaseFile
    pack: LegalPack
    case_hash: str
    attempts: int
    errors_per_attempt: list[list[str]] = field(default_factory=list)


def _band_text(crime: CrimeConfig) -> str:
    unit = "đồng" if crime.measure == "value_vnd" else "% tổn thương cơ thể"
    pieces = []
    for band in crime.bands:
        upper = f"dưới {band.high:,}".replace(",", ".") if band.high is not None else "trở lên"
        span = f"từ {band.low:,}".replace(",", ".") + f" {upper} {unit}"
        if not band.allowed:
            pieces.append(f"{span}: KHÔNG được dùng")
        else:
            rule = " hoặc ".join(f"khoản {k}" for k in band.required_khoan)
            if band.required_diem:
                rule += f" (phải có điểm {band.required_diem})"
            pieces.append(f"{span}: {rule}")
    return "; ".join(pieces)


def case_hash(case: CaseFile) -> str:
    return hashlib.sha256(case.model_dump_json().encode("utf-8")).hexdigest()


async def load_pack_for_crime(crime: CrimeConfig, settings: Settings, qdrant_client: QdrantClient) -> LegalPack:
    request = pack_request_for_crime(crime)
    payloads = await asyncio.to_thread(fetch_payloads, qdrant_client, settings.qdrant_collection, request)
    pack = build_pack(payloads)
    missing = missing_keys(pack, request)
    if missing:
        # Corpus check 2026-10-19 found none; a gap here means the collection changed.
        raise RuntimeError(f"Legal pack incomplete: {len(missing)} articles missing")
    return pack


def knobs_text(knobs: CaseKnobs) -> str:
    aggravating = (", ".join(f"điểm {p} khoản 1" for p in knobs.aggravating_points) + " Điều 52 Bộ luật Hình sự"
                   if knobs.aggravating_points else "KHÔNG có tình tiết tăng nặng nào (aggravating = [])")
    mitigating = ", ".join(f"điểm {p}" for p in knobs.mitigating_points)
    return "\n".join([
        f"- Khoản truy tố: khoản {knobs.khoan} (chọn measure_value và điểm cho đúng khoản này).",
        f"- Lập trường bị cáo (defendant_plea = {knobs.plea}): {PLEA_LABELS[knobs.plea]}. Lời khai, thẻ nhân vật "
        f"và thái độ của bị cáo phải thể hiện đúng lập trường này.",
        "- Bồi thường trước khi xét xử: " + ("CÓ - bị cáo đã bồi thường một phần hoặc toàn bộ; compensation_vnd là "
                                            "số tiền đã bồi thường, có sự việc (fact) ghi nhận việc này."
                                            if knobs.has_compensation else "KHÔNG - compensation_vnd = null."),
        f"- Tình tiết tăng nặng: {aggravating}. Phải có sự việc (fact) làm căn cứ.",
        f"- Tình tiết giảm nhẹ khoản 1 Điều 51: đúng và chỉ các {mitigating}" if mitigating
        else "- Không có tình tiết giảm nhẹ tại khoản 1 Điều 51.",
        "- Có thể thêm tình tiết giảm nhẹ khoản 2 Điều 51 (diem để trống) nếu hợp lý.",
    ])


def _assemble_case(draft: CaseDraft, options: CaseOptions, knobs: CaseKnobs, settings: Settings, seed: int,
                   hearing: date, incident: date) -> CaseFile:
    people = [(p.id, label, p.gender) for p, label in (
        (draft.defendant, "Bị cáo"), (draft.victim, "Bị hại"),
        *((w, "Người làm chứng") for w in draft.witnesses),
        *(((draft.related_party, "Người có quyền lợi, nghĩa vụ liên quan"),) if draft.related_party else ()),
    )]
    rng = random.Random(seed)
    court_people = [(pid, label, rng.choice(("nam", "nu"))) for pid, label in COURT_ROLES.items()]
    participants = assign_names(court_people + people, seed)
    return CaseFile(
        crime_key=options.crime_key, options=options, knobs=knobs,
        court=CourtInfo(name=settings.trial_court_name or DEFAULT_COURT_NAME,
                        hearing_date=hearing.strftime("%d/%m/%Y"), venue=ABSTRACT_PLACES[0]),
        incident_date=incident.strftime("%d/%m/%Y"), participants=participants, draft=draft,
    )


async def create_case(options: CaseOptions, settings: Settings, qdrant_client: QdrantClient,
                      recorder: TrialCallRecorder, *, pack: LegalPack | None = None,
                      seed: int | None = None, today: date | None = None,
                      knobs: CaseKnobs | None = None) -> CaseCreation:
    crime = get_crime(options.crime_key)
    pack = pack or await load_pack_for_crime(crime, settings, qdrant_client)
    seed = seed if seed is not None else uuid.uuid4().int & 0xFFFFFFFF
    rng = random.Random(seed)
    hearing = today or date.today()
    incident = hearing - timedelta(days=rng.randint(*INCIDENT_DAYS_BEFORE_HEARING))
    knobs = knobs or choose_knobs(crime, pack, rng)

    # Everything the indictment may cite: the charged Điều, Điều 51/52 and BLTTHS Điều 243 (the
    # indictment's own legal basis). Spike 2026-10-19: without 243 in context the model cited
    # BLTTHS truy tố articles from memory, which the Rule 9 pair guard rightly rejected.
    legal_text = "\n\n".join(a.prompt_block() for a in (
        pack.get(BLHS_DOCUMENT, crime.dieu), pack.get(BLHS_DOCUMENT, "51"), pack.get(BLHS_DOCUMENT, "52"),
        pack.get(BLTTHS_DOCUMENT, "243"),
    ) if a is not None)
    errors_per_attempt: list[list[str]] = []
    retry_errors: list[str] | None = None
    previous_draft: str | None = None
    repair: tuple[dict, dict[str, list[str]]] | None = None   # (draft to repair, {field path: errors})
    repaired = False
    started = time.monotonic()
    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        if attempt == MAX_GENERATION_ATTEMPTS and time.monotonic() - started > THIRD_ATTEMPT_MAX_ELAPSED:
            break
        if repair is not None:
            base, plan = repair
            base_draft = CaseDraft.model_validate(base)
            result, record = await recorder.call(
                settings, call_type="case_repair", slot="case", attempt=attempt,
                system_prompt=CASE_GENERATION_SYSTEM_PROMPT,
                user_prompt=build_case_repair_prompt(
                    draft_json=json.dumps(base, ensure_ascii=False), plan=plan,
                    amounts=declared_amounts(base_draft, crime), percents=declared_percents(base_draft, crime),
                    legal_text=legal_text),
                response_schema=REPAIR_SCHEMA, thinking_level=None, temperature=CASE_REPAIR_TEMPERATURE,
            )
        else:
            prompt = build_case_generation_prompt(
                crime_name=crime.crime_name, dieu=crime.dieu, allowed_khoan=list(crime.allowed_khoan),
                band_text=_band_text(crime), person_ids=expected_person_ids(options),
                victim_present=options.victim_present, witness_count=options.witness_count,
                has_related_party=options.has_related_party, places=list(ABSTRACT_PLACES),
                incident_date=incident.strftime("%d/%m/%Y"), hearing_date=hearing.strftime("%d/%m/%Y"),
                legal_text=legal_text, retry_errors=retry_errors, constraints=knobs_text(knobs),
                previous_draft=previous_draft,
            )
            result, record = await recorder.call(
                settings, call_type="case_generation", slot="case", attempt=attempt,
                system_prompt=CASE_GENERATION_SYSTEM_PROMPT, user_prompt=prompt,
                response_schema=CASE_DRAFT_RESPONSE_SCHEMA, thinking_level=THINKING_LEVEL_DECISION,
                temperature=CASE_TEMPERATURE,
            )
        data: dict | None = None
        try:
            data = normalise_draft_dict(apply_repair(repair[0], repair[1], result.text) if repair is not None
                                        else json.loads(result.text))
            draft = CaseDraft.model_validate(data)
            errors = validate_case_draft(draft, options, crime, pack, knobs)
        except RepairNotApplied:
            draft, errors = None, ["Sửa trường không áp dụng được (không trường nào được viết lại)"]
        except (ValueError, ValidationError) as error:
            draft, errors = None, [f"JSON không hợp lệ theo schema: {type(error).__name__}"]
        errors_per_attempt.append(errors)
        record.guard_violations = [error_label(e) for e in errors]
        record.accepted = not errors
        if not errors and draft is not None:
            case = _assemble_case(draft, options, knobs, settings, seed, hearing, incident)
            return CaseCreation(case=case, pack=pack, case_hash=case_hash(case), attempts=attempt,
                                errors_per_attempt=errors_per_attempt)
        logger.info("Trial case attempt %d rejected with %d validation errors", attempt, len(errors))
        usable = draft is not None
        if repair is not None:
            # This call was the single field repair. If its answer was unusable, regenerate on top
            # of the draft it started from, with that draft's errors.
            repaired = True
            if not usable:
                data, errors, usable = repair[0], errors_per_attempt[-2], True
            repair = None
        elif usable and not repaired:
            plan = repair_plan(errors, draft.model_dump())
            if plan is not None:
                repair = (draft.model_dump(), plan)
                continue
        if any(DIACRITIC_ERROR in e for e in errors):
            # Chặng 3F: a draft written without diacritics is not repaired but regenerated from
            # scratch - asked to edit it, the model kept the unaccented style (seed 5006, chặng 3E).
            retry_errors, previous_draft = None, None
            continue
        retry_errors = errors
        # A6 (chặng 2): the retry fixes the previous draft instead of writing a new one - in A5 run 1
        # a from-scratch retry fixed the listed errors but broke requirements it had met before.
        previous_draft = json.dumps(data, ensure_ascii=False) if usable and data is not None else None
    raise CaseGenerationFailed(errors_per_attempt)


async def stream_create_case(options: CaseOptions, settings: Settings, qdrant_client: QdrantClient,
                             recorder: TrialCallRecorder, holder: dict) -> AsyncIterator[tuple[str, object]]:
    """SSE-ready wrapper: status events, then `holder["creation"]` is set for the route to persist.
    Errors propagate; the route turns them into its `error` event exactly as notes.py does."""
    yield ("status", ChatStreamStatusEvent(message=STATUS_PREPARING))
    crime = get_crime(options.crime_key)
    pack = await load_pack_for_crime(crime, settings, qdrant_client)
    yield ("status", ChatStreamStatusEvent(message=STATUS_DRAFTING))
    holder["creation"] = await create_case(options, settings, qdrant_client, recorder, pack=pack)
    yield ("status", ChatStreamStatusEvent(message=STATUS_CHECKING))
