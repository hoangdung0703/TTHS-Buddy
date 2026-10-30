"""The 11-step state machine for "Phiên tòa giả định" (design doc Mục 2.1).

Pure logic, no I/O: the session repository (chặng 2) loads a SessionState, calls these functions,
and persists the result with "update ... where id = $1 and version = $expected". The LLM never
touches state: it only writes the utterances of slots this module hands to the AI, so no prompt,
injection or model mistake can skip xét hỏi or tranh luận.

Each step is data (StepSpec) holding its slots in the order the law prescribes. A slot names the
ROLE that acts in it; at runtime a slot whose role equals the student's role is a student turn and
every other slot is an AI turn. One script therefore serves every role - adding the Bị cáo or Chủ
tọa role later needs UI for that role's actions, not a new engine.

Người xem (chặng R1, design doc Mục 11.1) is a role with no participant id: every slot is an AI
slot, the student only advances between steps, and the đối đáp of step 8 becomes a fixed number of
AI rounds (AI_DEBATE_ROUNDS), each speech a separate AI turn.

Thư ký (chặng R2, design doc Mục 11.3) speaks once: the step-1 attendance report, which is a template
slot for every other role. Every later slot is an AI slot, as for Người xem; the clerk's real work
(notes, parts IV.2 and IV.3 of the biên bản) goes through trial_clerk, never through this machine.

Bị cáo (chặng R3, design doc Mục 11.2) answers inside AI slots ("đoạn xen", Mục 11.0b): khai mạc,
the HĐXX questioning, the KSV and luật sư questioning and lời sau cùng stop at each question put to
the student, who answers ("speak") or, while being questioned, declines ("decline"); a per-slot cap
(SlotSpec.max_questions) bounds the questions and so the calls. Two optional turns exist for this
role only (SlotSpec.user_roles): bổ sung bào chữa (step 7) and tranh luận with a KSV reply (step 8).

Chủ tọa (chặng R4, design doc Mục 11.4, plan KE-HOACH-CHU-TOA.md) presides: from step 2 on, every step
is one "preside" slot owned by the student, who performs the step's procedural items, asks, invites
the AI parts and moves on with "advance" once every required item is done. Its own state
(PresideState) is kept on SessionState.preside; the rules live in trial_presiding, which this module
calls for that role only.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from typing import Literal

Role = Literal["chu_toa", "hoi_tham", "thu_ky", "ksv", "luat_su", "bi_cao", "bi_hai",
               "nguoi_lam_chung", "nguoi_lq", "hdxx"]
SlotKind = Literal["template", "segment", "speech", "indictment", "qa_loop", "long_speech", "debate",
                   "deliberation", "preside"]
Requirement = Literal["witnesses", "victim_present", "related_party"]
# Roles a student may take (the database check of migration 0013 allows the same list).
UserRole = Literal["chu_toa", "thu_ky", "ksv", "luat_su", "bi_cao", "nguoi_xem"]

ROLE_LABELS: dict[str, str] = {
    "chu_toa": "Chủ tọa", "hoi_tham": "Hội thẩm", "thu_ky": "Thư ký", "ksv": "Kiểm sát viên",
    "luat_su": "Luật sư bào chữa", "bi_cao": "Bị cáo", "bi_hai": "Bị hại",
    "nguoi_lam_chung": "Người làm chứng", "nguoi_lq": "Người có quyền lợi, nghĩa vụ liên quan",
    "hdxx": "Hội đồng xét xử",
    "nguoi_xem": "Người xem",
    # Speaker of the lines code writes in a Chủ tọa session (pauses): never the student's id.
    "he_thong": "Hệ thống",
}

# Participant ids per role; witnesses expand to NLC_1..NLC_n.
ROLE_TO_IDS: dict[str, tuple[str, ...]] = {
    "chu_toa": ("CHU_TOA",), "hoi_tham": ("HOI_THAM_1", "HOI_THAM_2"), "thu_ky": ("THU_KY",),
    "ksv": ("KSV",), "luat_su": ("LUAT_SU",), "bi_cao": ("BI_CAO",), "bi_hai": ("BI_HAI",),
    "nguoi_lq": ("NLQ",), "hdxx": ("CHU_TOA", "HOI_THAM_1", "HOI_THAM_2"),
}
LAY_IDS_PREFIXES = ("BI_CAO", "BI_HAI", "NLC_", "NLQ")
# Roles whose stage is enabled: the API accepts no other (config.user_roles is built from this).
ENABLED_USER_ROLES: frozenset[str] = frozenset({"ksv", "luat_su", "nguoi_xem", "thu_ky", "bi_cao", "chu_toa"})
# Observes only: no participant id, never speaks, every slot is an AI slot.
OBSERVER_ROLE = "nguoi_xem"
# Speaks only the step-1 report, then writes parts IV.2 and IV.3 of the biên bản (trial_clerk).
CLERK_ROLE = "thu_ky"
# Answers inside AI slots (đoạn xen) and may decline a question (trial_defendant).
DEFENDANT_ROLE = "bi_cao"
_DEFENDANT_ONLY = frozenset({DEFENDANT_ROLE})
# Presides over the hearing from step 2 on (trial_presiding).
PRESIDING_ROLE = "chu_toa"
SYSTEM_SPEAKER_ID = "HE_THONG"
# Who answers the questions of a qa_loop the AI asks.
_QA_ANSWER_ROLES = ("bi_cao", "bi_hai", "nguoi_lam_chung", "nguoi_lq")
# Đối đáp when neither side is the student: KSV then luật sư per round (decision 2026-10-29, item 3).
AI_DEBATE_ROUNDS = 1


@dataclass(frozen=True)
class SlotSpec:
    key: str
    role: Role
    kind: SlotKind
    # AI segments: who may speak (role names; "nguoi_lam_chung" expands to the case's witnesses).
    speakers: tuple[str, ...] = ()
    requires: Requirement | None = None
    min_user_turns: int = 0
    max_user_turns: int = 1
    min_chars: int = 0
    # Student slots only: overrides the default maximum of text_limits.
    max_chars: int | None = None
    # Debate only: the other side.
    opponent: Role | None = None
    # The slot exists only when the student's role is in this set; None = every role (Mục 11.0a).
    user_roles: frozenset[str] | None = None
    # Đoạn xen (Mục 11.0b), when the student's role answers in this AI slot: at most `max_questions`
    # questions are put to the student, the AI is held to ask at least `min_questions` (code asks
    # a fixed question otherwise), `decline` allows "Từ chối trả lời", and `close_on_cap` ends the
    # slot on the last answer with no further AI call (lời sau cùng: no question after it).
    # Questioning caps (decision 13, lowered 2026-10-30): HĐXX 4, KSV 3, luật sư 3 = 10 questions;
    # khai mạc (2) and lời sau cùng (1) are procedural turns outside that total.
    max_questions: int = 0
    min_questions: int = 0
    decline: bool = False
    close_on_cap: bool = False


@dataclass(frozen=True)
class StepSpec:
    number: int
    title: str
    legal_basis: tuple[str, ...]  # BLTTHS Điều numbers
    slots: tuple[SlotSpec, ...]


STEPS: tuple[StepSpec, ...] = (
    StepSpec(1, "Thư ký báo cáo sự có mặt", ("300", "288", "289", "290", "291", "292", "293"), (
        # A code template when the AI is Thư ký; the student's prefilled report when the student is
        # (Mục 11.3.1: 100-3.000 characters).
        SlotSpec("bao_cao_co_mat", "thu_ky", "template", min_user_turns=1, min_chars=100, max_chars=3000),
    )),
    StepSpec(2, "Khai mạc phiên tòa", ("301", "302", "303", "304", "305"), (
        SlotSpec("khai_mac", "chu_toa", "segment", speakers=("chu_toa", "bi_cao"), max_questions=2,
                 min_questions=2),
        SlotSpec("y_kien_ksv_thay_doi", "ksv", "speech", min_user_turns=0),
        SlotSpec("y_kien_ls_thay_doi", "luat_su", "speech", min_user_turns=0),
        SlotSpec("cam_doan_nlc", "chu_toa", "segment", speakers=("chu_toa", "nguoi_lam_chung"),
                 requires="witnesses"),
    )),
    StepSpec(3, "Công bố cáo trạng", ("306",), (
        SlotSpec("cong_bo_cao_trang", "ksv", "indictment", min_user_turns=1, min_chars=100),
    )),
    StepSpec(4, "Hội đồng xét xử xét hỏi", ("307", "308", "309", "310", "311", "312"), (
        SlotSpec("hdxx_hoi_bi_cao", "chu_toa", "segment", speakers=("chu_toa", "hoi_tham", "bi_cao"),
                 max_questions=4, min_questions=1, decline=True),
        SlotSpec("hdxx_hoi_nguoi_khac", "chu_toa", "segment",
                 speakers=("chu_toa", "hoi_tham", "bi_hai", "nguoi_lam_chung", "nguoi_lq")),
    )),
    StepSpec(5, "Kiểm sát viên và luật sư xét hỏi", ("307", "309", "310", "311", "317", "318"), (
        SlotSpec("ksv_hoi", "ksv", "qa_loop", min_user_turns=1, max_user_turns=8, max_questions=3, decline=True),
        SlotSpec("ls_hoi", "luat_su", "qa_loop", min_user_turns=1, max_user_turns=8, max_questions=3, decline=True),
        SlotSpec("ket_thuc_xet_hoi", "chu_toa", "template"),
    )),
    StepSpec(6, "Kiểm sát viên luận tội", ("319", "320", "321"), (
        SlotSpec("luan_toi", "ksv", "long_speech", min_user_turns=1, min_chars=300),
    )),
    StepSpec(7, "Luật sư bào chữa", ("320", "322"), (
        SlotSpec("bao_chua", "luat_su", "long_speech", min_user_turns=1, min_chars=300),
        # Điều 320 khoản 2 BLTTHS: the defendant may add to the defence. Optional ("end_slot").
        SlotSpec("moi_bi_cao_bo_sung", "chu_toa", "template", user_roles=_DEFENDANT_ONLY),
        SlotSpec("bi_cao_bo_sung_bao_chua", "bi_cao", "speech", max_chars=3000, user_roles=_DEFENDANT_ONLY),
        SlotSpec("bi_hai_trinh_bay", "chu_toa", "segment", speakers=("chu_toa", "bi_hai"),
                 requires="victim_present"),
    )),
    StepSpec(8, "Tranh luận, đối đáp", ("322",), (
        SlotSpec("doi_dap", "ksv", "debate", opponent="luat_su", min_user_turns=1, max_user_turns=3),
        # Điều 322 BLTTHS: one optional turn of the defendant, answered by one KSV speech.
        SlotSpec("moi_bi_cao_tranh_luan", "chu_toa", "template", user_roles=_DEFENDANT_ONLY),
        SlotSpec("bi_cao_tranh_luan", "bi_cao", "debate", opponent="ksv", max_user_turns=1, max_chars=3000,
                 user_roles=_DEFENDANT_ONLY),
        SlotSpec("ket_thuc_tranh_luan", "chu_toa", "template"),
    )),
    StepSpec(9, "Bị cáo nói lời sau cùng", ("324",), (
        SlotSpec("loi_sau_cung", "chu_toa", "segment", speakers=("chu_toa", "bi_cao"), max_questions=1,
                 min_questions=1, close_on_cap=True, max_chars=3000),
    )),
    StepSpec(10, "Nghị án", ("326",), (
        SlotSpec("vao_nghi_an", "chu_toa", "template"),
        SlotSpec("nghi_an", "hdxx", "deliberation"),
    )),
    StepSpec(11, "Tuyên án", ("327", "260", "298"), (
        SlotSpec("tuyen_an", "chu_toa", "long_speech"),
    )),
)
STEP_BY_NUMBER: dict[int, StepSpec] = {s.number: s for s in STEPS}
LAST_STEP = len(STEPS)
# Chủ tọa: the only slot of steps 2-11. Step 1 keeps the Thư ký template slot of every role.
PRESIDE_SLOT = SlotSpec("preside", "chu_toa", "preside")
FIRST_PRESIDED_STEP = 2


@dataclass(frozen=True)
class CaseShape:
    victim_present: bool
    witness_count: int
    has_related_party: bool

    def satisfies(self, requirement: Requirement | None) -> bool:
        if requirement is None:
            return True
        return {"witnesses": self.witness_count > 0, "victim_present": self.victim_present,
                "related_party": self.has_related_party}[requirement]

    def ids_for_role(self, role: str) -> tuple[str, ...]:
        if role == "nguoi_lam_chung":
            return tuple(f"NLC_{i}" for i in range(1, self.witness_count + 1))
        if role == "bi_hai" and not self.victim_present:
            return ()
        if role == "nguoi_lq" and not self.has_related_party:
            return ()
        return ROLE_TO_IDS[role]

    def lay_present_ids(self) -> tuple[str, ...]:
        ids = ["BI_CAO"]
        ids += list(self.ids_for_role("bi_hai"))
        ids += list(self.ids_for_role("nguoi_lam_chung"))
        ids += list(self.ids_for_role("nguoi_lq"))
        return tuple(ids)


@dataclass(frozen=True)
class PresideJob:
    """AI work owed in a Chủ tọa session. kind: "answer" (to the student's question or remark),
    "invite" (an AI part the student invited; `key` is the item), "assessor" (Hội thẩm comments on
    the decision draft) or "pronounce_draft" (the judgment text written from the locked decision).
    `progress` counts the speeches already stored of a two-speech invite (one debate round)."""
    kind: Literal["answer", "invite", "assessor", "pronounce_draft"]
    key: str = ""
    addressee: str | None = None
    progress: int = 0


@dataclass(frozen=True)
class PresideState:
    """Chủ tọa only, stored in mock_trial_sessions.user_work["preside"] and written with the version
    (no migration). `done`, `questions`, `remarks` and `rounds` are per step."""
    done: tuple[str, ...] = ()
    questions: int = 0
    remarks: int = 0
    rounds: int = 0
    job: PresideJob | None = None
    # Điều 323 BLTTHS: once per hearing, from step 8 back to a short step 5, then step 8 again.
    returned: bool = False
    in_return: bool = False
    decided: bool = False
    drafted: bool = False


@dataclass(frozen=True)
class SessionState:
    user_role: UserRole
    shape: CaseShape
    current_step: int = 1
    slot_index: int = 0
    version: int = 0
    status: Literal["active", "completed", "abandoned"] = "active"
    slot_user_turns: int = 0
    # True while the AI owes a reply inside a loop slot (an answer, a debate response) or the
    # AI owns the slot outright.
    pending_ai: bool = False
    # Chủ tọa only; None for every other role.
    preside: PresideState | None = None


class TrialConflict(Exception):
    """Maps to HTTP 409. `code` is stable and safe to log; never contains student text."""

    def __init__(self, code: str, state: SessionState, detail: dict | None = None):
        super().__init__(code)
        self.code = code
        self.state = state
        # Extra keys of the 409 body (e.g. missing_items): keys and labels only, never student text.
        self.detail = detail or {}


def active_slots(step: int, shape: CaseShape, user_role: str | None = None) -> tuple[SlotSpec, ...]:
    """Slots of `step` for this case shape and, when given, this student role (SlotSpec.user_roles)."""
    if user_role == PRESIDING_ROLE and step >= FIRST_PRESIDED_STEP:
        return (PRESIDE_SLOT,)
    return tuple(s for s in STEP_BY_NUMBER[step].slots if shape.satisfies(s.requires)
                 and (s.user_roles is None or user_role is None or user_role in s.user_roles))


def current_slot(state: SessionState) -> SlotSpec | None:
    slots = active_slots(state.current_step, state.shape, state.user_role)
    return slots[state.slot_index] if state.slot_index < len(slots) else None


def is_user_slot(slot: SlotSpec, user_role: str) -> bool:
    if slot.kind == "debate":
        return user_role in (slot.role, slot.opponent)
    return slot.role == user_role


def is_interleaved(slot: SlotSpec, user_role: str) -> bool:
    """An AI slot that stops at each question put to the student (đoạn xen, Mục 11.0b): the student's
    role answers in it - a speaker of a dialogue segment, or the person questioned in a qa_loop the
    AI runs - and the slot has a question cap."""
    if slot.max_questions <= 0 or is_user_slot(slot, user_role):
        return False
    answerers = slot.speakers if slot.kind == "segment" else _QA_ANSWER_ROLES if slot.kind == "qa_loop" else ()
    return user_role in answerers


def ai_speaker_ids(slot: SlotSpec, state: SessionState) -> tuple[str, ...]:
    """The enum of speaker ids an AI segment for this slot may use - never the student's role."""
    user_ids = set(ROLE_TO_IDS.get(state.user_role, ()))
    ids: list[str] = []
    for role in slot.speakers:
        ids.extend(i for i in state.shape.ids_for_role(role) if i not in user_ids)
    return tuple(dict.fromkeys(ids))


def _enter(state: SessionState) -> SessionState:
    """Normalise after moving onto a slot: AI-owned slots and debates the AI opens are pending."""
    slot = current_slot(state)
    if slot is None:
        if state.current_step == LAST_STEP:
            return replace(state, status="completed", pending_ai=False)
        return replace(state, pending_ai=False)
    if not is_user_slot(slot, state.user_role):
        return replace(state, pending_ai=True)
    if slot.kind == "debate" and state.user_role != slot.role and state.slot_user_turns == 0:
        return replace(state, pending_ai=True)  # the AI side opens the debate
    return replace(state, pending_ai=False)


def is_ai_debate(slot: SlotSpec, user_role: str) -> bool:
    """A debate neither side of which is the student: AI_DEBATE_ROUNDS rounds of AI speeches."""
    return slot.kind == "debate" and not is_user_slot(slot, user_role)


def debate_speaker_role(slot: SlotSpec, speeches_done: int) -> str:
    """AI-AI debate: the slot's own role (KSV) opens each round, the opponent answers."""
    assert slot.opponent is not None
    return slot.role if speeches_done % 2 == 0 else slot.opponent


def new_session(user_role: UserRole, shape: CaseShape) -> SessionState:
    if user_role not in ENABLED_USER_ROLES:
        raise ValueError(f"Role not enabled: {user_role}")
    preside = PresideState() if user_role == PRESIDING_ROLE else None
    return _enter(SessionState(user_role=user_role, shape=shape, preside=preside))


def is_presiding(state: SessionState) -> bool:
    """A Chủ tọa session past step 1: trial_presiding's rules apply, not the slot script's."""
    return state.user_role == PRESIDING_ROLE and state.current_step >= FIRST_PRESIDED_STEP


def _next_slot(state: SessionState) -> SessionState:
    return _enter(replace(state, slot_index=state.slot_index + 1, slot_user_turns=0, pending_ai=False,
                          version=state.version + 1))


def awaiting(state: SessionState) -> Literal["ai", "user", "none"]:
    if state.status != "active":
        return "none"
    return "ai" if state.pending_ai else "user"


def step_complete(state: SessionState) -> bool:
    return current_slot(state) is None


PRESIDE_ACTIONS: frozenset[str] = frozenset({"item", "ask", "invite", "remark", "return_to_questioning", "decide",
                                             "prepare_pronouncement", "pronounce"})


@dataclass(frozen=True)
class UserAction:
    kind: Literal["speak", "end_slot", "advance", "decline", "item", "ask", "invite", "remark",
                  "return_to_questioning", "decide", "prepare_pronouncement", "pronounce"]
    expected_step: int
    expected_version: int
    text: str | None = None
    addressee: str | None = None
    target_step: int | None = None
    # Chủ tọa: the procedural item an "item" or "invite" action performs.
    item: str | None = None


@dataclass(frozen=True)
class ActionOutcome:
    state: SessionState
    # "accepted" (the action counted), or "skip_refused" (the student asked, in words, to jump
    # ahead: their utterance is recorded and Chủ tọa answers with a canned reminder - no LLM call).
    result: Literal["accepted", "skip_refused"]
    skip_target: int | None = None


def allowed_actions(state: SessionState) -> list[str]:
    if awaiting(state) != "user":
        return []
    if is_presiding(state):
        from app.services import trial_presiding  # imports this module, so resolved at call time
        return trial_presiding.allowed_actions(state)
    slot = current_slot(state)
    if slot is None:
        return [f"advance:{state.current_step + 1}"]
    actions: list[str] = []
    if is_interleaved(slot, state.user_role):   # a question is pending: answer it (or decline it)
        return ["speak", "decline"] if slot.decline else ["speak"]
    if slot.kind == "qa_loop":
        actions.append("speak:" + "|".join(state.shape.lay_present_ids()))
        if state.slot_user_turns >= slot.min_user_turns:
            actions.append("end_slot")
    elif slot.kind == "debate":
        if state.slot_user_turns < slot.max_user_turns:
            actions.append("speak")
        if state.slot_user_turns >= slot.min_user_turns:
            actions.append("end_slot")
    else:
        actions.append("speak")
        if slot.min_user_turns == 0:
            actions.append("end_slot")
    return actions


# Student text length per slot (characters). Single source: the turn route enforces it and the
# state sent to the client carries it (text_limits), so the frontend never derives it.
SHORT_TEXT_MAX_CHARS = 1500
LONG_TEXT_MAX_CHARS = 6000
LONG_TEXT_SLOT_KINDS = frozenset({"long_speech", "debate", "indictment"})


def text_limits(state: SessionState) -> tuple[int, int] | None:
    """(min, max) characters for the student's next "speak", or None when speaking is not allowed."""
    if not any(a == "speak" or a.startswith("speak:") for a in allowed_actions(state)):
        return None
    slot = current_slot(state)
    assert slot is not None
    if slot.max_chars is not None:
        return max(1, slot.min_chars), slot.max_chars
    return (max(1, slot.min_chars),
            LONG_TEXT_MAX_CHARS if slot.kind in LONG_TEXT_SLOT_KINDS else SHORT_TEXT_MAX_CHARS)


def apply_user_action(state: SessionState, action: UserAction) -> ActionOutcome:
    if state.status != "active":
        raise TrialConflict("not_active", state)
    if action.expected_version != state.version:
        raise TrialConflict("version_mismatch", state)
    if action.expected_step != state.current_step:
        raise TrialConflict("step_mismatch", state)
    if awaiting(state) != "user":
        raise TrialConflict("not_your_turn", state)
    if state.user_role == OBSERVER_ROLE and action.kind != "advance":
        raise TrialConflict("action_not_allowed", state)
    if is_presiding(state):
        from app.services import trial_presiding  # imports this module, so resolved at call time
        return trial_presiding.apply_action(state, action)
    if action.kind in PRESIDE_ACTIONS:
        raise TrialConflict("action_not_allowed", state)
    slot = current_slot(state)

    if action.kind == "advance":
        if action.target_step != state.current_step + 1:
            raise TrialConflict("skip_not_allowed", state)
        if slot is not None:
            raise TrialConflict("slot_not_finished", state)
        return ActionOutcome(_enter(replace(state, current_step=state.current_step + 1, slot_index=0,
                                            slot_user_turns=0, version=state.version + 1)), "accepted")

    if slot is None:
        raise TrialConflict("action_not_allowed", state)

    if is_interleaved(slot, state.user_role):
        return _answer_question(state, slot, action)
    if action.kind == "decline":
        raise TrialConflict("action_not_allowed", state)

    if action.kind == "end_slot":
        if slot.kind not in ("qa_loop", "debate", "speech") or state.slot_user_turns < slot.min_user_turns:
            raise TrialConflict("slot_not_finished", state)
        return ActionOutcome(_next_slot(state), "accepted")

    # speak
    text = (action.text or "").strip()
    if not text:
        raise TrialConflict("empty_text", state)
    skip_target = detect_skip_request(text, state.current_step)
    if skip_target is not None:
        return ActionOutcome(replace(state, version=state.version + 1), "skip_refused", skip_target)
    if slot.kind == "qa_loop":
        if action.addressee not in state.shape.lay_present_ids():
            raise TrialConflict("missing_addressee", state)
        if state.slot_user_turns >= slot.max_user_turns:
            raise TrialConflict("turn_limit", state)
        return ActionOutcome(replace(state, pending_ai=True, version=state.version + 1), "accepted")
    if slot.kind == "debate":
        if state.slot_user_turns >= slot.max_user_turns:
            raise TrialConflict("turn_limit", state)
        if state.user_role == slot.role:
            return ActionOutcome(replace(state, pending_ai=True, version=state.version + 1), "accepted")
        turns = state.slot_user_turns + 1
        moved = replace(state, slot_user_turns=turns, version=state.version + 1)
        if turns >= slot.max_user_turns:
            return ActionOutcome(_next_slot(moved), "accepted")
        return ActionOutcome(replace(moved, pending_ai=True), "accepted")
    if len(text) < slot.min_chars:
        raise TrialConflict("text_too_short", state)
    return ActionOutcome(_next_slot(state), "accepted")


def _answer_question(state: SessionState, slot: SlotSpec, action: UserAction) -> ActionOutcome:
    """The student's answer to (or refusal of) the question pending in a đoạn xen. Each counts as
    one of the slot's questions; the AI goes on unless the slot closes on its last answer."""
    if action.kind == "decline":
        if not slot.decline:
            raise TrialConflict("action_not_allowed", state)
    elif action.kind == "speak":
        text = (action.text or "").strip()
        if not text:
            raise TrialConflict("empty_text", state)
        skip_target = detect_skip_request(text, state.current_step)
        if skip_target is not None:
            return ActionOutcome(replace(state, version=state.version + 1), "skip_refused", skip_target)
        if len(text) < slot.min_chars:
            raise TrialConflict("text_too_short", state)
    else:   # a question cannot be skipped
        raise TrialConflict("action_not_allowed", state)
    answered = replace(state, slot_user_turns=state.slot_user_turns + 1, version=state.version + 1)
    if slot.close_on_cap and answered.slot_user_turns >= slot.max_questions:
        return ActionOutcome(_next_slot(answered), "accepted")
    return ActionOutcome(replace(answered, pending_ai=True), "accepted")


def questions_left(state: SessionState) -> int:
    """Đoạn xen: questions the AI may still put to the student in the current slot."""
    slot = current_slot(state)
    return max(0, slot.max_questions - state.slot_user_turns) if slot else 0


def complete_ai_turn(state: SessionState, asked_student: bool = False) -> SessionState:
    """Called once the AI output for the pending turn has passed its guards and been stored.
    `asked_student`: in a đoạn xen, the output ends with a question to the student, who answers
    next; otherwise the slot is over."""
    if awaiting(state) != "ai":
        raise TrialConflict("not_ai_turn", state)
    if is_presiding(state):
        from app.services import trial_presiding  # imports this module, so resolved at call time
        return trial_presiding.complete_job(state)
    slot = current_slot(state)
    assert slot is not None
    if is_interleaved(slot, state.user_role):
        if asked_student and questions_left(state) > 0:
            return replace(state, pending_ai=False, version=state.version + 1)
        return _next_slot(state)
    if slot.kind == "qa_loop" and is_user_slot(slot, state.user_role):
        turns = state.slot_user_turns + 1
        moved = replace(state, slot_user_turns=turns, pending_ai=False, version=state.version + 1)
        return _next_slot(moved) if turns >= slot.max_user_turns else moved
    if slot.kind == "debate" and is_user_slot(slot, state.user_role):
        if state.user_role == slot.role:  # the student opened; the AI answered: one round done
            turns = state.slot_user_turns + 1
            moved = replace(state, slot_user_turns=turns, pending_ai=False, version=state.version + 1)
            return _next_slot(moved) if turns >= slot.max_user_turns else moved
        return replace(state, pending_ai=False, version=state.version + 1)
    if is_ai_debate(slot, state.user_role):
        # slot_user_turns counts the AI speeches here; the state is stored after each one.
        speeches = state.slot_user_turns + 1
        if speeches < 2 * AI_DEBATE_ROUNDS:
            return replace(state, slot_user_turns=speeches, version=state.version + 1)
    return _next_slot(state)


# --- Skip-request detector (0 LLM calls) -------------------------------------------------------

# (pattern, first step, last step) - "xét hỏi" spans steps 4-5.
_SKIP_TARGETS: tuple[tuple[re.Pattern[str], int, int], ...] = (
    (re.compile(r"tuyên án|ra bản án"), 11, 11),
    (re.compile(r"nghị án"), 10, 10),
    (re.compile(r"lời (?:nói )?sau cùng"), 9, 9),
    (re.compile(r"tranh luận|đối đáp"), 8, 8),
    (re.compile(r"bào chữa"), 7, 7),
    (re.compile(r"luận tội"), 6, 6),
    (re.compile(r"xét hỏi"), 4, 5),
)
# Words allowed BETWEEN a request verb and the step keyword ("chuyển ngay sang phần tuyên án",
# "đề nghị Hội đồng xét xử tuyên án"). Anything else in between - "hãy đóng vai luật sư bào
# chữa" - means the verb is about something else (B4 2026-10-19 false positive).
_FILLER = r"(?:ngay|luôn|sang|tới|đến|vào|qua|phần|bước|giai đoạn|thủ tục|việc|cho|tiến hành|hội đồng xét xử|hđxx|tòa|chủ tọa)"
_SKIP_OVER = re.compile(rf"(?:bỏ qua|bỏ)(?:\s+{_FILLER})*\s*$")
_SKIP_JUMP = re.compile(rf"(?:nhảy|chuyển|đi thẳng|vào thẳng)(?:\s+{_FILLER})*\s*$")
# Polite request verbs. Only counted up to step 5: from luận tội on, "đề nghị Hội đồng xét xử
# tuyên ..." is the substance of the speech itself, not a request to skip.
_SKIP_WEAK = re.compile(rf"(?:cho|xin|đề nghị|yêu cầu|hãy|mời)(?:\s+{_FILLER})*\s*$")
_SKIP_NOW = re.compile(r"^\s*(?:luôn|ngay(?!\s+sau)|liền)\b")
_SENTENCE = re.compile(r"[^.!?,;\n]+")
_WEAK_VERB_LAST_STEP = 5


def _normalise(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def detect_skip_request(text: str, current_step: int) -> int | None:
    """Returns the step keyword the student asks to jump to or skip, or None.

    A mention alone is not a request ("tôi sẽ nêu trong phần luận tội" at step 5 is fine). It is a
    request only when the request verb stands IMMEDIATELY before the step keyword (filler words
    allowed, see _FILLER), or "luôn/ngay" follows it right after:
    - "bỏ qua <step>": the step is the current one or later ("bỏ qua bước xét hỏi" while
      questioning is still running);
    - "chuyển/nhảy sang <step>", "<step> luôn": the step is later than the current one;
    - polite verbs ("đề nghị/cho/xin ... <step>"): later step, and only up to step 5.
    Steps are never entered by talking, whatever this returns."""
    for sentence in _SENTENCE.findall(_normalise(text)):
        for pattern, first, last in _SKIP_TARGETS:
            for match in pattern.finditer(sentence):
                before = sentence[:match.start()].rstrip()
                after = sentence[match.end():]
                if _SKIP_OVER.search(before) and last >= current_step:
                    return first
                if first <= current_step:
                    continue
                if _SKIP_JUMP.search(before) or _SKIP_NOW.search(after):
                    return first
                if current_step <= _WEAK_VERB_LAST_STEP and _SKIP_WEAK.search(before):
                    return first
    return None


def skip_refusal_text(state: SessionState) -> str:
    step = STEP_BY_NUMBER[state.current_step]
    return (f"Phiên tòa đang ở phần \"{step.title.lower()}\". Hội đồng xét xử chỉ chuyển sang phần "
            f"tiếp theo khi phần này kết thúc theo đúng trình tự tố tụng; không thể bỏ qua phần xét hỏi "
            f"hay tranh luận. Đề nghị {ROLE_LABELS[state.user_role]} tiếp tục phần hiện tại.")
