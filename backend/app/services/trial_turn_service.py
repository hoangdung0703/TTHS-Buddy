"""AI turns of a mock-trial hearing (design doc Mục 2.3-2.4, 5).

The state machine decides WHICH slot is due; this module produces its utterances:
- template slots (Thư ký report, "no objection", the indictment when the AI is KSV, closing
  formulas, entering deliberation): code, 0 LLM calls;
- dialogue segments: ONE call writes the whole run of AI utterances up to the student's next turn,
  as JSON whose speaker_id is an enum built per slot that never contains the student's role;
- long speeches (luận tội, bào chữa, đối đáp, tuyên án): one call, one speaker, Rule 9 pair guard;
- nghị án: a structured Verdict, checked by trial_verdict_guard before tuyên án is written from it.

Guards on every AI output (one regeneration with feedback, then fail closed for hard violations):
speaker in the enum and not the student's role; lay speakers cite no Điều; legal speakers pass the
pair guard; no invented names or unknown placeholders; numbers (money, percent) match the case
file or the fact ledger (soft: flagged on the utterance, no regeneration). "Speaks for the student" is measured
only (decision 2026-10-19); structurally the student's id is never in the speaker enum. A court or
prosecutor office named other than the configured ones is flagged `office_name` (measured, chặng R1).

Bị cáo (chặng R3): a đoạn xen makes one call per question put to the student; its schema carries the
question in a separate field (cau_hoi_cho_nguoi_hoc) whose speaker enum holds the slot's askers
only, so no output can contain the defendant's answer. Content patterns of "the AI speaks for the
defendant" are measured only (decision 14), as are amounts in the student's own words that the case
file does not hold (`user_amount_off_file`, Mục 11.2.3).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.trial import VERDICT_RESPONSE_SCHEMA, CaseFile, Verdict
from app.prompts.trial_prompts import (
    AI_QA_GOALS,
    DEFENDANT_SLOT_INSTRUCTIONS,
    DEFENDANT_TESTIMONY_RULES,
    DEFENDANT_TURN_ASK,
    DEFENDANT_TURN_CLOSE,
    DEFENDANT_VERDICT_NOTE,
    OBSERVER_ROLE_LINE,
    OBSERVER_RULE_ONE,
    OFFICES_LINE,
    PLAYER_ROLE_LINE,
    PLAYER_RULE_ONE,
    SLOT_INSTRUCTIONS,
    TRIAL_SYSTEM_PROMPT,
    TUYEN_AN_INSTRUCTION,
    VERDICT_SYSTEM_PROMPT,
)
from app.services.trial_case_validator import (
    MONEY_PATTERN,
    PERCENT_PATTERN,
    declared_amounts,
    declared_percents,
    office_name_mismatches,
    parse_money,
)
from app.services.trial_config import (
    BLHS_DOCUMENT,
    DEFAULT_COURT_NAME,
    LEGACY_COURT_PLACEHOLDER,
    THINKING_LEVEL_DECISION,
    get_crime,
    procuracy_name,
)
from app.services.trial_defendant import (
    DECLINE_TEXT,
    INVITATIONS,
    OPT_OUT_TEXTS,
    fallback_question,
)
from app.services.trial_legal_pack import LegalPack
from app.services.trial_metrics import CallRecord, TrialCallRecorder
from app.services.trial_names import NAME_LIKE_PATTERN, placeholders_in
from app.services.trial_rule9 import (
    check_citations,
    extract_citations,
    lay_speaker_citations,
    mask_unverified_citations,
)
from app.services.trial_state_machine import (
    DEFENDANT_ROLE,
    LAY_IDS_PREFIXES,
    ROLE_LABELS,
    ROLE_TO_IDS,
    STEP_BY_NUMBER,
    CaseShape,
    SessionState,
    SlotSpec,
    TrialConflict,
    UserAction,
    ai_speaker_ids,
    apply_user_action,
    awaiting,
    complete_ai_turn,
    current_slot,
    debate_speaker_role,
    is_ai_debate,
    is_interleaved,
    is_user_slot,
    questions_left,
    skip_refusal_text,
    text_limits,
)
from app.services.trial_text_format import format_speech, format_utterance
from app.services.trial_verdict_guard import check_verdict, normalise_verdict

logger = get_logger(__name__)

DIALOGUE_TEMPERATURE = 0.7
SPEECH_TEMPERATURE = 0.6
VERDICT_TEMPERATURE = 0.2
MAX_ATTEMPTS = 2
TRANSCRIPT_CHAR_BUDGET = 20_000
# unknown_amount is hard since 2026-10-19 (B4 rerun conditions): a money amount the case does not
# hold must never come out of an AI character - a student asserting a false amount was echoed
# back in B4. unknown_percent stays a soft flag.
HARD_VIOLATIONS = frozenset({"speaker_not_allowed", "speaker_is_student", "lay_citation", "citation",
                             "invented_name", "unknown_placeholder", "empty", "schema", "missing_charge_citation",
                             "unknown_amount"})
# Only a card the legal team has approved is used: data/private/build_style_card.py writes
# style_card.draft.md, and a reviewer renames it to style_card.approved.md after reading it.
STYLE_CARD_PATH = Path(__file__).resolve().parents[3] / "data" / "private" / "style_card.approved.md"

_ID_TO_ROLE: dict[str, str] = {i: role for role, ids in ROLE_TO_IDS.items() if role != "hdxx" for i in ids}
LEGAL_SPEAKER_IDS = frozenset({"CHU_TOA", "HOI_THAM_1", "HOI_THAM_2", "KSV", "LUAT_SU", "THU_KY"})
# Guard flag of the utterance that holds a question put to the student in a đoạn xen; the state's
# pending_question points at the latest one. `question_fallback`: asked by code, not the model.
STUDENT_QUESTION_FLAG = "student_question"


def role_of(speaker_id: str) -> str:
    if speaker_id.startswith("NLC_"):
        return "nguoi_lam_chung"
    return _ID_TO_ROLE.get(speaker_id, "he_thong")


@dataclass
class Utterance:
    seq: int
    step: int
    speaker_id: str
    is_user: bool
    kind: str          # speech | procedural | notice
    text: str          # with {ID} placeholders for people
    guard_flags: list[str] = field(default_factory=list)
    addressee: str | None = None  # the person a student question is put to (step 5)


@dataclass
class TrialContext:
    case: CaseFile
    pack: LegalPack
    state: SessionState
    settings: Settings
    recorder: TrialCallRecorder
    transcript: list[Utterance] = field(default_factory=list)
    fact_ledger: list[dict[str, str]] = field(default_factory=list)
    verdict: Verdict | None = None
    verdict_flags: list[str] = field(default_factory=list)
    # Biên bản summaries (trial_record_summary), stored inside verdict_json once computed.
    record_summary: dict | None = None

    @property
    def student_id(self) -> str | None:
        """The student's participant id; None for Người xem, who plays no participant."""
        ids = ROLE_TO_IDS.get(self.state.user_role)
        return ids[0] if ids else None

    @property
    def court(self) -> str:
        name = self.case.court.name
        return DEFAULT_COURT_NAME if name == LEGACY_COURT_PLACEHOLDER else name

    def add(self, speaker_id: str, text: str, *, is_user: bool = False, kind: str = "speech",
            flags: list[str] | None = None, addressee: str | None = None) -> Utterance:
        utterance = Utterance(len(self.transcript) + 1, self.state.current_step, speaker_id, is_user, kind,
                              text, flags or [], addressee)
        self.transcript.append(utterance)
        return utterance


class TrialGuardFailure(Exception):
    """An AI output failed a hard guard twice. The hearing pauses at the same slot; the route
    (chặng 2) shows a notice and lets the student retry. `violations` holds labels only."""

    def __init__(self, slot: str, violations: list[str]):
        super().__init__(f"guard failure in slot {slot}")
        self.slot = slot
        self.violations = violations


class _SegmentUtterance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    speaker_id: str
    text: str


class _NewFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    about: str
    fact: str


class _SegmentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    utterances: list[_SegmentUtterance]
    new_facts: list[_NewFact] = []


class _Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    speaker_id: str
    text: str


class _InterleavedOut(_SegmentOut):
    cau_hoi_cho_nguoi_hoc: _Question | None = None


class _SpeechOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


def _segment_schema(speakers: tuple[str, ...]) -> dict:
    return {
        "type": "OBJECT",
        "properties": {
            "utterances": {"type": "ARRAY", "items": {
                "type": "OBJECT",
                "properties": {"speaker_id": {"type": "STRING", "enum": list(speakers)}, "text": {"type": "STRING"}},
                "required": ["speaker_id", "text"]}},
            "new_facts": {"type": "ARRAY", "items": {
                "type": "OBJECT", "properties": {"about": {"type": "STRING"}, "fact": {"type": "STRING"}},
                "required": ["about", "fact"]}},
        },
        "required": ["utterances", "new_facts"],
    }


def _interleaved_schema(speakers: tuple[str, ...], askers: tuple[str, ...]) -> dict:
    """Đoạn xen: the segment schema plus ONE optional question for the student, last by construction.
    Neither enum holds the student's id."""
    schema = _segment_schema(speakers)
    schema["properties"]["cau_hoi_cho_nguoi_hoc"] = {
        "type": "OBJECT", "nullable": True,
        "properties": {"speaker_id": {"type": "STRING", "enum": list(askers)}, "text": {"type": "STRING"}},
        "required": ["speaker_id", "text"]}
    schema["required"] = [*schema["required"], "cau_hoi_cho_nguoi_hoc"]
    return schema


_SPEECH_SCHEMA = {"type": "OBJECT", "properties": {"text": {"type": "STRING"}}, "required": ["text"]}


# --- Prompt assembly ------------------------------------------------------------------------------

def _name_to_placeholder(text: str, case: CaseFile) -> str:
    """Student text uses the rendered names; the model works on placeholders only."""
    for participant in sorted(case.participants.values(), key=lambda p: -len(p.name)):
        text = text.replace(participant.name, "{" + participant.id + "}")
    return text


def _sanitise_student_text(text: str) -> str:
    return text.replace("<<<", "‹‹‹").replace(">>>", "›››")


def _case_block(case: CaseFile) -> str:
    people = {pid: p.role for pid, p in case.participants.items()}
    return json.dumps({"toa_an": case.court.model_dump(), "ngay_xay_ra": case.incident_date,
                       "nguoi_tham_gia": people, "ho_so": case.draft.model_dump()}, ensure_ascii=False)


def _transcript_block(ctx: TrialContext) -> str:
    """Whole current step plus, from earlier steps, the student's words and the long speeches;
    oldest earlier lines are dropped first when over budget."""
    step = ctx.state.current_step
    lines: list[tuple[bool, str]] = []
    for u in ctx.transcript:
        if u.kind == "notice":
            continue
        label = f"[Bước {u.step}] {{{u.speaker_id}}} ({ROLE_LABELS.get(role_of(u.speaker_id), 'Hệ thống')})"
        if u.is_user:
            masked, _ = mask_unverified_citations(_name_to_placeholder(u.text, ctx.case), ctx.pack,
                                                  ROLE_LABELS[ctx.state.user_role])
            body = f"<<<LOI_NGUOI_HOC\n{_sanitise_student_text(masked)}\n>>>"
        else:
            body = u.text
        keep_always = u.step == step
        lines.append((keep_always, f"{label}: {body}"))
    total = sum(len(text) for _, text in lines)
    out: list[str] = []
    for keep, text in lines:
        if not keep and total > TRANSCRIPT_CHAR_BUDGET:
            total -= len(text)
            continue
        out.append(text)
    return "\n".join(out) if out else "(chưa có)"


def context_pack(ctx: TrialContext, slot_key: str) -> LegalPack:
    """What Rule 9 is checked against for one AI call: exactly the articles in its prompt (the
    slot's slice), plus pack articles the STUDENT cited in the transcript the model was shown - the
    model may legitimately answer "Điều X mà Kiểm sát viên viện dẫn...". Rule 9: cite only what is
    in the context."""
    charged = ctx.case.draft.charge.dieu
    articles = {a.key: a for a in ctx.pack.slice_for_slot(slot_key, ctx.state.current_step, charged)}
    # The case file is in EVERY prompt, so what it cites is context for every slot: the charged
    # Điều, Điều 51/52 when it lists circumstances, and every article its indictment cites.
    # B4 2026-10-19: without this, Chủ tọa reading the charge at khai mạc ("điểm c khoản 2 Điều
    # 173 Bộ luật Hình sự") failed the guard 124 times - the opening slice holds BLTTHS only.
    for dieu in (charged, *(("51",) if ctx.case.draft.mitigating else ()), *(("52",) if ctx.case.draft.aggravating else ())):
        article = ctx.pack.get(BLHS_DOCUMENT, dieu)
        if article is not None:
            articles[article.key] = article
    allowed_full = ctx.pack.allowed_pairs()
    cited_texts = [ctx.case.draft.indictment_text] + [u.text for u in ctx.transcript if u.is_user]
    for text in cited_texts:
        for citation in extract_citations(text):
            docs = [citation.law] if citation.law else [d for d, n in allowed_full if n == citation.dieu]
            for doc in docs:
                article = ctx.pack.get(doc, citation.dieu) if doc else None
                if article is not None:
                    articles[article.key] = article
    return ctx.pack.subset(articles.values())


def _user_prompt(ctx: TrialContext, instruction: str, speakers: tuple[str, ...], slot_key: str) -> str:
    charged = ctx.case.draft.charge.dieu
    legal = "\n\n".join(a.prompt_block() for a in
                         ctx.pack.slice_for_slot(slot_key, ctx.state.current_step, charged))
    step = STEP_BY_NUMBER[ctx.state.current_step]
    ledger = "\n".join(f"- {{{f['about']}}}: {f['fact']}" for f in ctx.fact_ledger) or "(trống)"
    allowed = ", ".join("{" + s + "}" for s in speakers)
    return "\n\n".join([
        "=== HỒ SƠ VỤ ÁN ===\n" + _case_block(ctx.case),
        "=== QUY ĐỊNH PHÁP LUẬT ===\n" + legal,
        "=== SỔ DỮ KIỆN ===\n" + ledger,
        "=== DIỄN BIẾN PHIÊN TÒA ===\n" + _transcript_block(ctx),
        f"=== CHỈ DẪN LƯỢT ===\nĐang ở bước {step.number}: {step.title}.\n{instruction}\n"
        f"Chỉ những người sau được nói: {allowed}.",
    ])


def _system_prompt(ctx: TrialContext, base: str = TRIAL_SYSTEM_PROMPT) -> str:
    offices = OFFICES_LINE.format(court=ctx.court, procuracy=procuracy_name(ctx.court))
    if ctx.student_id is None:
        return base.format(role_line=OBSERVER_ROLE_LINE, rule_one=OBSERVER_RULE_ONE, offices_line=offices)
    role = {"user_role_label": ROLE_LABELS[ctx.state.user_role], "user_role_id": "{" + ctx.student_id + "}"}
    return base.format(role_line=PLAYER_ROLE_LINE.format(**role), rule_one=PLAYER_RULE_ONE.format(**role),
                       offices_line=offices)


# --- Guards ---------------------------------------------------------------------------------------

def _known_numbers(ctx: TrialContext) -> tuple[set[int], set[int]]:
    crime = get_crime(ctx.case.crime_key)
    amounts = declared_amounts(ctx.case.draft, crime)
    percents = declared_percents(ctx.case.draft, crime)
    for fact in ctx.fact_ledger:
        amounts.update(parse_money(m.group(1)) for m in MONEY_PATTERN.finditer(fact["fact"]))
        percents.update(int(m.group(1)) for m in PERCENT_PATTERN.finditer(fact["fact"]))
    if ctx.verdict is not None:
        if ctx.verdict.civil_amount_vnd:
            amounts.add(ctx.verdict.civil_amount_vnd)
        if ctx.verdict.fine_vnd:
            amounts.add(ctx.verdict.fine_vnd)
    return amounts, percents


_SPEAKS_FOR_STUDENT = {
    "KSV": re.compile(r"(?:\{KSV\}|kiểm sát viên)\s+(?:đã\s+|vừa\s+|cũng\s+)?(?:thừa nhận|đồng ý|xác nhận|rút)",
                      re.IGNORECASE),
    "LUAT_SU": re.compile(r"(?:\{LUAT_SU\}|luật sư)\s+(?:đã\s+|vừa\s+|cũng\s+)?(?:thừa nhận|đồng ý|xác nhận|rút)",
                          re.IGNORECASE),
    # Thư ký (chặng R2): another speaker reporting in the clerk's place ("Thư ký báo cáo: ..."). A
    # reference to the report already made ("Thư ký đã báo cáo") is not matched.
    "THU_KY": re.compile(r"(?:\{THU_KY\}|thư ký(?: phiên tòa)?)\s+(?:xin\s+)?(?:báo cáo|thừa nhận|xác nhận)",
                         re.IGNORECASE),
    # Bị cáo (Mục 11.2.6): another speaker stating what the defendant admitted or said.
    "BI_CAO": re.compile(r"(?:\{BI_CAO\}|bị cáo)\s+(?:đã|vừa|cũng)\s+(?:thừa nhận|nhận tội|khai rằng|xác nhận|đồng ý)"
                         r"|như\s+(?:\{BI_CAO\}|bị cáo)\s+vừa\s+khai", re.IGNORECASE),
}
# The defendant's latest words admit something: the BI_CAO pattern above is then not counted.
# Negated forms ("không thừa nhận", "chưa đúng") are removed first, so they admit nothing.
_ADMISSION = re.compile(r"thừa nhận|nhận tội|xác nhận|đồng ý|\bnhận\b|\bđúng\b", re.IGNORECASE)
_NEGATED_ADMISSION = re.compile(r"\b(?:không|chưa)\s+(?:hề\s+)?(?:thừa nhận|nhận tội|xác nhận|đồng ý|nhận|đúng)",
                                re.IGNORECASE)


def _student_just_admitted(ctx: TrialContext) -> bool:
    last = next((u for u in reversed(ctx.transcript) if u.is_user), None)
    return (last is not None and last.kind == "speech"
            and bool(_ADMISSION.search(_NEGATED_ADMISSION.sub(" ", last.text))))


def _check_utterance(ctx: TrialContext, speaker_id: str, text: str, allowed: tuple[str, ...],
                     mode: str = "lenient", pack: LegalPack | None = None) -> tuple[list[str], list[str]]:
    """(hard/soft violation labels, measure-only flags) for one utterance."""
    violations: list[str] = []
    flags: list[str] = []
    if not text.strip():
        violations.append("empty")
    if speaker_id == ctx.student_id:
        violations.append("speaker_is_student")
    elif speaker_id not in allowed:
        violations.append("speaker_not_allowed")
    if speaker_id.startswith(LAY_IDS_PREFIXES):
        if lay_speaker_citations(text):
            violations.append("lay_citation")
    else:
        violations += [f"citation:{v.label()}" for v in check_citations(text, pack or ctx.pack, mode)]  # type: ignore[arg-type]
    known = set(ctx.case.participants)
    if placeholders_in(text) - known:
        violations.append("unknown_placeholder")
    if NAME_LIKE_PATTERN.search(text):
        violations.append("invented_name")
    amounts, percents = _known_numbers(ctx)
    if speaker_id in LEGAL_SPEAKER_IDS and pack is not None:
        # Thresholds and fine ranges quoted from the articles in this call's context are not case facts.
        amounts = amounts | {parse_money(m.group(1)) for a in pack.articles.values()
                             for m in MONEY_PATTERN.finditer(a.text)}
    if any(parse_money(m.group(1)) not in amounts for m in MONEY_PATTERN.finditer(text)):
        violations.append("unknown_amount")
    if any(int(m.group(1)) not in percents for m in PERCENT_PATTERN.finditer(text)):
        violations.append("unknown_percent")
    pattern = _SPEAKS_FOR_STUDENT.get(ctx.student_id or "")
    if pattern and speaker_id != ctx.student_id and pattern.search(text) and not (
            ctx.student_id == "BI_CAO" and _student_just_admitted(ctx)):
        flags.append("speaks_for_student")
    if office_name_mismatches(text, ctx.court):
        flags.append("office_name")
    return violations, flags


def _trim_answer(question: str, student_id: str) -> tuple[str, bool]:
    """Cuts a question at a line written as the student's answer ("{BI_CAO}: ..." or "Bị cáo: ..."):
    the schema leaves no field for the answer, but the model can still type one into the question.
    Returns the question and whether anything was cut (flagged `question_trimmed`)."""
    if not student_id:
        return question, False
    label = re.escape(ROLE_LABELS[role_of(student_id)])
    match = re.search(rf"(?:\{{{student_id}\}}\s*:|(?:^|\n)\s*{label}\s*:)", question, re.IGNORECASE)
    if match is None or not question[:match.start()].strip():
        return question, False
    return question[:match.start()].rstrip(), True


def _is_hard(violation: str) -> bool:
    return violation.split(":")[0] in HARD_VIOLATIONS


def _feedback(violations: list[str]) -> str:
    return ("\n\nBẢN TRƯỚC BỊ TỪ CHỐI vì: " + "; ".join(sorted(set(violations))) +
            ". Viết lại, tuân thủ đúng quy tắc (chỉ viện dẫn Điều trong QUY ĐỊNH PHÁP LUẬT kèm tên luật; người "
            "không chuyên không nêu số Điều; không nêu số tiền nào không có trong hồ sơ - nếu người học nêu số "
            "sai thì đính chính bằng con số trong hồ sơ, không nhắc lại số sai; chỉ dùng placeholder có trong hồ sơ).")


# --- Generation primitives ------------------------------------------------------------------------

async def _generate_segment(ctx: TrialContext, slot_key: str, instruction: str,
                            speakers: tuple[str, ...], askers: tuple[str, ...] | None = None) -> list[Utterance]:
    """One dialogue call. `askers` is set in a đoạn xen: the output may end with one question to the
    student by one of them, stored last and flagged STUDENT_QUESTION_FLAG; an empty tuple (the
    question cap is reached) asks nothing, and any question the model still returns is dropped. A
    đoạn xen may also return no line at all: the slot just ends."""
    feedback = ""
    last_violations: list[str] = []
    schema = _interleaved_schema(speakers, askers) if askers else _segment_schema(speakers)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result, record = await ctx.recorder.call(
            ctx.settings, call_type="dialogue", slot=slot_key, attempt=attempt,
            system_prompt=_system_prompt(ctx), user_prompt=_user_prompt(ctx, instruction, speakers, slot_key) + feedback,
            response_schema=schema, thinking_level=None, temperature=DIALOGUE_TEMPERATURE,
        )
        try:
            out = _InterleavedOut.model_validate(json.loads(result.text))
        except (ValueError, ValidationError):
            record.guard_violations, record.accepted = ["schema"], False
            last_violations = ["schema"]
            feedback = _feedback(["schema"])
            continue
        pack = context_pack(ctx, slot_key)
        for utterance in out.utterances:  # layout by code, before the guards (content unchanged)
            utterance.text = format_utterance(utterance.text)
        checked = [(u, *_check_utterance(ctx, u.speaker_id, u.text, speakers, pack=pack)) for u in out.utterances]
        question = out.cau_hoi_cho_nguoi_hoc if askers else None
        if question is not None:
            question.text, trimmed = _trim_answer(format_utterance(question.text), ctx.student_id or "")
            vs, flags = _check_utterance(ctx, question.speaker_id, question.text, askers, pack=pack)
            checked.append((question, vs, [*flags, *(["question_trimmed"] if trimmed else []),
                                           STUDENT_QUESTION_FLAG]))
        violations = [v for _, vs, _ in checked for v in vs] or ([] if checked or askers is not None else ["empty"])
        record.guard_violations = violations
        hard = [v for v in violations if _is_hard(v)]
        if hard and attempt < MAX_ATTEMPTS:
            record.accepted = False
            last_violations = violations
            feedback = _feedback(violations)
            continue
        if hard:
            record.accepted = False
            raise TrialGuardFailure(slot_key, violations)
        produced = []
        for utterance, vs, flags in checked:
            produced.append(ctx.add(utterance.speaker_id, utterance.text, flags=[*vs, *flags]))
        amounts, _ = _known_numbers(ctx)
        for fact in out.new_facts:
            # A new "fact" carrying a money amount the case does not hold would make that amount
            # legitimate for every later turn (the ledger feeds _known_numbers): dropped.
            if fact.about in ctx.case.participants and all(
                    parse_money(m.group(1)) in amounts for m in MONEY_PATTERN.finditer(fact.fact)):
                ctx.fact_ledger.append({"about": fact.about, "fact": fact.fact})
        return produced
    raise TrialGuardFailure(slot_key, last_violations)


async def _generate_speech(ctx: TrialContext, slot_key: str, instruction: str, speaker_id: str, *,
                           mode: str, thinking_level: str | None, extra_check=None) -> Utterance:
    feedback = ""
    last: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result, record = await ctx.recorder.call(
            ctx.settings, call_type="long_speech", slot=slot_key, attempt=attempt,
            system_prompt=_system_prompt(ctx), user_prompt=_user_prompt(ctx, instruction, (speaker_id,), slot_key) + feedback,
            response_schema=_SPEECH_SCHEMA, thinking_level=thinking_level, temperature=SPEECH_TEMPERATURE,
        )
        try:
            text = format_speech(_SpeechOut.model_validate(json.loads(result.text)).text, multi_paragraph=True)
        except (ValueError, ValidationError):
            record.guard_violations, record.accepted, last = ["schema"], False, ["schema"]
            feedback = _feedback(["schema"])
            continue
        violations, flags = _check_utterance(ctx, speaker_id, text, (speaker_id,), mode,
                                             pack=context_pack(ctx, slot_key))
        if extra_check is not None:
            violations += extra_check(text)
        record.guard_violations = violations
        hard = [v for v in violations if _is_hard(v)]
        if hard:
            record.accepted = False
            last = violations
            if attempt < MAX_ATTEMPTS:
                feedback = _feedback(violations)
                continue
            raise TrialGuardFailure(slot_key, violations)
        return ctx.add(speaker_id, text, flags=[*violations, *flags])
    raise TrialGuardFailure(slot_key, last)


# --- Templates (0 LLM calls) ----------------------------------------------------------------------

def attendance_report(shape: CaseShape) -> str:
    """The Thư ký's step-1 report: the AI's words when the AI is Thư ký, the prefilled draft the
    student edits when the student is (Mục 11.3.1)."""
    present = ["Kiểm sát viên {KSV}", "bị cáo {BI_CAO}", "luật sư {LUAT_SU} bào chữa cho bị cáo"]
    absent: list[str] = []
    if shape.victim_present:
        present.append("bị hại {BI_HAI}")
    else:
        absent.append("bị hại {BI_HAI} vắng mặt, có đơn đề nghị xét xử vắng mặt")
    present += [f"người làm chứng {{NLC_{i}}}" for i in range(1, shape.witness_count + 1)]
    if shape.has_related_party:
        present.append("người có quyền lợi, nghĩa vụ liên quan {NLQ}")
    text = ("Thưa Hội đồng xét xử, theo giấy triệu tập của Tòa án, tại phiên tòa hôm nay có mặt: "
            + "; ".join(present) + ".")
    if absent:
        text += " Vắng mặt: " + "; ".join(absent) + "."
    return text + " Thư ký phiên tòa đã phổ biến nội quy phiên tòa. Báo cáo Hội đồng xét xử."


_TEMPLATES = {
    "y_kien_ksv_thay_doi": ("KSV", "Viện kiểm sát không có đề nghị thay đổi người tiến hành tố tụng."),
    "y_kien_ls_thay_doi": ("LUAT_SU", "Tôi không có đề nghị thay đổi người tiến hành tố tụng."),
    "ket_thuc_xet_hoi": ("CHU_TOA", "Xét thấy các tình tiết của vụ án đã được xem xét đầy đủ, Hội đồng xét xử "
                                    "tuyên bố kết thúc phần xét hỏi, chuyển sang phần tranh luận."),
    "ket_thuc_tranh_luan": ("CHU_TOA", "Xét thấy không còn ý kiến nào khác, Hội đồng xét xử tuyên bố kết thúc "
                                       "phần tranh luận."),
    "vao_nghi_an": ("CHU_TOA", "Hội đồng xét xử vào phòng nghị án. Đề nghị mọi người giữ trật tự chờ tuyên án."),
}


# --- Verdict --------------------------------------------------------------------------------------

async def _deliberate(ctx: TrialContext) -> None:
    feedback = ""
    last: list[str] = []
    base = VERDICT_SYSTEM_PROMPT + (DEFENDANT_VERDICT_NOTE if ctx.state.user_role == DEFENDANT_ROLE else "")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result, record = await ctx.recorder.call(
            ctx.settings, call_type="verdict", slot="nghi_an", attempt=attempt,
            system_prompt=_system_prompt(ctx, base),
            user_prompt=_user_prompt(ctx, "Hội đồng xét xử nghị án và trả về quyết định có cấu trúc.",
                                     ("CHU_TOA", "HOI_THAM_1", "HOI_THAM_2"), "nghi_an") + feedback,
            response_schema=VERDICT_RESPONSE_SCHEMA, thinking_level=THINKING_LEVEL_DECISION,
            temperature=VERDICT_TEMPERATURE,
        )
        try:
            verdict = normalise_verdict(Verdict.model_validate(json.loads(result.text)), ctx.case)
        except (ValueError, ValidationError):
            record.guard_violations, record.accepted, last = ["schema"], False, ["schema"]
            feedback = _feedback(["schema"])
            continue
        check = check_verdict(verdict, ctx.case, ctx.pack)
        record.guard_violations = [*check.errors, *check.flags]
        if check.errors:
            record.accepted = False
            last = check.errors
            feedback = "\n\nQUYẾT ĐỊNH TRƯỚC BỊ TỪ CHỐI vì:\n" + "\n".join(f"- {e}" for e in check.errors)
            continue
        ctx.verdict, ctx.verdict_flags = verdict, check.flags
        return
    raise TrialGuardFailure("nghi_an", last)


def _style_card() -> str:
    """Optional, legal-team-approved style card from data/private/ (absent in CI/production)."""
    try:
        return "\n\nTHẺ VĂN PHONG (chỉ học cấu trúc và giọng văn, không chép nội dung):\n" + \
            STYLE_CARD_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


def _charge_citation_check(ctx: TrialContext):
    def check(text: str) -> list[str]:
        if ctx.verdict is None or not ctx.verdict.guilty:
            return []
        found = any(c.dieu == ctx.verdict.dieu and c.law == BLHS_DOCUMENT and ctx.verdict.khoan in c.khoan
                    for c in extract_citations(text))
        return [] if found else ["missing_charge_citation"]
    return check


# --- Slot dispatch --------------------------------------------------------------------------------

async def run_ai_turn(ctx: TrialContext) -> list[Utterance]:
    """Produce the AI output owed for the current slot, then advance the state machine."""
    slot = current_slot(ctx.state)
    assert slot is not None and awaiting(ctx.state) == "ai"
    produced = await _dispatch(ctx, slot)
    asked = bool(produced) and STUDENT_QUESTION_FLAG in produced[-1].guard_flags
    ctx.state = complete_ai_turn(ctx.state, asked_student=asked)
    return produced


async def _dispatch(ctx: TrialContext, slot: SlotSpec) -> list[Utterance]:
    state = ctx.state
    if slot.key == "bao_cao_co_mat":
        return [ctx.add("THU_KY", attendance_report(state.shape), kind="procedural")]
    if slot.key in _TEMPLATES:
        speaker, text = _TEMPLATES[slot.key]
        return [ctx.add(speaker, text, kind="procedural")]
    if slot.key in INVITATIONS:
        return [ctx.add("CHU_TOA", INVITATIONS[slot.key], kind="procedural")]
    if is_interleaved(slot, state.user_role):
        return await _interleaved_turn(ctx, slot)
    if slot.kind == "indictment":  # AI is KSV: the indictment is read verbatim from the case file
        return [ctx.add("KSV", ctx.case.draft.indictment_text)]
    if slot.kind == "segment":
        speakers = ai_speaker_ids(slot, state)
        return await _generate_segment(ctx, slot.key, SLOT_INSTRUCTIONS[slot.key].format(), speakers)
    if slot.kind == "qa_loop":
        if is_user_slot(slot, state.user_role):  # answer the student's last question
            question = next(u for u in reversed(ctx.transcript) if u.is_user)
            addressee = question.addressee or "BI_CAO"
            instruction = SLOT_INSTRUCTIONS["answer_question"].format(
                asker_label=ROLE_LABELS[state.user_role], addressee_id="{" + addressee + "}")
            return await _generate_segment(ctx, slot.key + ":answer", instruction, (addressee, "CHU_TOA"))
        asker = ROLE_TO_IDS[slot.role][0]
        speakers = (asker, *state.shape.lay_present_ids())
        instruction = SLOT_INSTRUCTIONS["ai_qa_loop"].format(
            asker_label=ROLE_LABELS[slot.role], asker_id="{" + asker + "}", goal=AI_QA_GOALS[asker])
        return await _generate_segment(ctx, slot.key, instruction, speakers)
    if slot.kind == "long_speech":
        if slot.key == "tuyen_an":
            await _deliberate_if_needed(ctx)
            assert ctx.verdict is not None
            instruction = TUYEN_AN_INSTRUCTION.format() + "\n\nQUYẾT ĐỊNH NGHỊ ÁN:\n" + \
                ctx.verdict.model_dump_json(exclude={"reasoning_summary"}) + \
                "\nNhận định (dùng để viết phần nhận định): " + ctx.verdict.reasoning_summary + _style_card()
            return [await _generate_speech(ctx, slot.key, instruction, "CHU_TOA", mode="strict",
                                           thinking_level=THINKING_LEVEL_DECISION,
                                           extra_check=_charge_citation_check(ctx))]
        speaker = ROLE_TO_IDS[slot.role][0]
        return [await _generate_speech(ctx, slot.key, SLOT_INSTRUCTIONS[slot.key].format(), speaker,
                                       mode="lenient", thinking_level=None)]
    if is_ai_debate(slot, state.user_role):
        # One speech per AI turn; each answers the other side's latest view (the bào chữa for the
        # first KSV speech).
        side = debate_speaker_role(slot, state.slot_user_turns)
        other = slot.opponent if side == slot.role else slot.role
        speaker = ROLE_TO_IDS[side][0]
        instruction = SLOT_INSTRUCTIONS["doi_dap"].format(
            speaker_id="{" + speaker + "}", opponent_label=ROLE_LABELS[other])
        return [await _generate_speech(ctx, slot.key, instruction, speaker, mode="lenient", thinking_level=None)]
    if slot.kind == "debate":   # the student's side spoke (or opens): the other side answers
        speaker = ROLE_TO_IDS[slot.opponent if state.user_role == slot.role else slot.role][0]
        instruction = SLOT_INSTRUCTIONS["doi_dap"].format(
            speaker_id="{" + speaker + "}", opponent_label=ROLE_LABELS[state.user_role])
        return [await _generate_speech(ctx, slot.key, instruction, speaker, mode="lenient", thinking_level=None)]
    if slot.kind == "deliberation":
        await _deliberate(ctx)
        return []
    raise ValueError(f"No handler for slot {slot.key}")


async def _interleaved_turn(ctx: TrialContext, slot: SlotSpec) -> list[Utterance]:
    """One call of a đoạn xen (Mục 11.0b): the AI lines up to the next question for the student, or
    the close of the slot once the cap is reached. Below `min_questions`, a slot the model closed
    without asking gets the fixed question from trial_defendant (0 extra calls)."""
    state = ctx.state
    student = ctx.student_id or ""
    if slot.kind == "qa_loop":
        asker = ROLE_TO_IDS[slot.role][0]
        speakers = (asker, *(i for i in state.shape.lay_present_ids() if i != student))
        askers: tuple[str, ...] = (asker,)
        instruction = DEFENDANT_SLOT_INSTRUCTIONS[slot.key].format(goal=AI_QA_GOALS[asker])
    else:
        speakers = ai_speaker_ids(slot, state)
        askers = tuple(i for i in speakers if not i.startswith(LAY_IDS_PREFIXES))
        instruction = DEFENDANT_SLOT_INSTRUCTIONS[slot.key].format()
    left = questions_left(state)
    if left > 0:
        turn = DEFENDANT_TURN_ASK.format(number=state.slot_user_turns + 1, cap=slot.max_questions)
    else:
        askers, turn = (), DEFENDANT_TURN_CLOSE.format()
    instruction = "\n".join([instruction, DEFENDANT_TESTIMONY_RULES.format(), turn])
    produced = await _generate_segment(ctx, slot.key, instruction, speakers, askers)
    asked = bool(produced) and STUDENT_QUESTION_FLAG in produced[-1].guard_flags
    if not asked and left > 0 and state.slot_user_turns < slot.min_questions:
        produced.append(ctx.add("CHU_TOA", fallback_question(slot.key, state.slot_user_turns),
                                flags=["question_fallback", STUDENT_QUESTION_FLAG]))
    return produced


async def _deliberate_if_needed(ctx: TrialContext) -> None:
    if ctx.verdict is None:
        await _deliberate(ctx)


async def run_until_user(ctx: TrialContext) -> list[Utterance]:
    produced: list[Utterance] = []
    while awaiting(ctx.state) == "ai":
        produced += await run_ai_turn(ctx)
    return produced


def _student_flags(ctx: TrialContext, text: str) -> list[str]:
    """Measure-only flags on the student's own words, never shown to the client. Bị cáo: an amount or
    percent the case file does not hold (Mục 11.2.3) - recorded verbatim, never added to the ledger."""
    if ctx.state.user_role != DEFENDANT_ROLE:
        return []
    amounts, percents = _known_numbers(ctx)
    if (any(parse_money(m.group(1)) not in amounts for m in MONEY_PATTERN.finditer(text))
            or any(int(m.group(1)) not in percents for m in PERCENT_PATTERN.finditer(text))):
        return ["user_amount_off_file"]
    return []


def apply_student_action(ctx: TrialContext, action: UserAction) -> list[Utterance]:
    """Validate and record the student's action. Raises TrialConflict (409) on any rule break.
    The student's text is stored verbatim; masking applies only when it is put into a prompt."""
    limits = text_limits(ctx.state)
    if action.kind == "speak" and action.text and limits is not None and len(action.text) > limits[1]:
        raise TrialConflict("text_too_long", ctx.state)
    slot = current_slot(ctx.state)
    outcome = apply_user_action(ctx.state, action)
    produced: list[Utterance] = []
    if action.kind == "speak" and action.text:
        text = action.text.strip()
        produced.append(ctx.add(ctx.student_id, text, is_user=True, addressee=action.addressee,
                                flags=_student_flags(ctx, text)))
    elif action.kind == "decline":
        produced.append(ctx.add(ctx.student_id, DECLINE_TEXT, is_user=True, kind="procedural", flags=["declined"]))
    elif action.kind == "end_slot" and slot is not None and slot.key in OPT_OUT_TEXTS:
        produced.append(ctx.add(ctx.student_id, OPT_OUT_TEXTS[slot.key], is_user=True, kind="procedural"))
    ctx.state = outcome.state
    if outcome.result == "skip_refused":
        produced.append(ctx.add("CHU_TOA", skip_refusal_text(ctx.state), kind="notice", flags=["skip_refused"]))
    return produced
