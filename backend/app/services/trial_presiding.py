"""The Chủ tọa role (chặng R4, design doc Mục 11.4, decisions 13-21 of 11.8, plan KE-HOACH-CHU-TOA.md).

From step 2 on, a Chủ tọa session has one "preside" slot per step (trial_state_machine.PRESIDE_SLOT).
The student performs the step's procedural items (ProcedureItem): an "item" is a procedural
statement, an "ask" a question to one person, an "invite" starts an AI part (luận tội, đối đáp...).
Required items must be done before "advance"; the order the law imposes is encoded with `first`,
`last` and `after`. Everything here is pure (no I/O, no LLM):
- the catalogue of items per step, with the BLTTHS articles they follow (checked against
  ingestion/chunks.json, see the plan's Phụ lục A);
- the state rules (allowed_actions, apply_action, complete_job), called by trial_state_machine for
  this role only;
- the "Dùng lời mẫu" templates and the procedural answers written by code: 0 LLM calls
  (decisions Q2, Q5). They are drafts until the legal team approves them (TEMPLATES_REVIEWED);
- the measure-only pattern of an AI line taking over the presiding (usurps_presiding, decision 14).

The AI never speaks as CHU_TOA: the student's id is never in a speaker enum, and every line the code
writes on its own in this role (pauses) uses SYSTEM_SPEAKER_ID.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

from app.models.trial import CaseFile
from app.services.trial_defendant import FALLBACK_QUESTIONS, INVITATIONS
from app.services.trial_names import render
from app.services.trial_state_machine import (
    ActionOutcome,
    CaseShape,
    PresideJob,
    PresideState,
    SessionState,
    TrialConflict,
    UserAction,
    _enter,
)

# --- Limits (decision 13 and Mục 11.4.1) ---------------------------------------------------------
STEP4_MAX_QUESTIONS = 10
RETURN_MAX_QUESTIONS = 3          # Điều 323 return: each side at most 3 questions (Mục 11.4.6)
REMARKS_PER_STEP = 5
REMARK_STEPS = range(2, 10)       # no "phát biểu khác" while deliberating (10) or pronouncing (11)
ITEM_MAX_CHARS = 3000
QUESTION_MAX_CHARS = 1500
REMARK_MAX_CHARS = 1500
REASONING_MIN_CHARS, REASONING_MAX_CHARS = 200, 2000
TEXT_LIMITS = {"item": (1, ITEM_MAX_CHARS), "ask": (1, QUESTION_MAX_CHARS), "remark": (1, REMARK_MAX_CHARS),
               "reasoning": (REASONING_MIN_CHARS, REASONING_MAX_CHARS)}
# Two rounds is a limit of the simulation: Điều 322 khoản 3 BLTTHS says "Chủ toạ phiên tòa không được
# hạn chế thời gian tranh luận" (decision Q12: say so to the student).
DEBATE_ROUNDS_NOTE = ("Giới hạn tối đa 2 vòng đối đáp là giới hạn của bản mô phỏng. Theo khoản 3 Điều 322 Bộ luật "
                      "Tố tụng hình sự, Chủ tọa phiên tòa không được hạn chế thời gian tranh luận.")
TEMPLATES_REVIEWED = False

Requirement = Literal["witnesses", "victim_present", "victim_absent", "related_party", "others_present"]
ItemKind = Literal["item", "ask", "invite", "return", "decide", "pronounce"]


@dataclass(frozen=True)
class ProcedureItem:
    key: str
    label: str
    kind: ItemKind
    required: bool
    basis: tuple[str, ...]            # BLTTHS Điều numbers
    requires: Requirement | None = None
    first: bool = False               # nothing else in the step before it
    last: bool = False                # only once every other required item is done
    after: tuple[str, ...] = ()       # only once these are done
    ai_calls: int = 0                 # LLM calls of the response (0 = written by code)
    note: str | None = None


_I = ProcedureItem
STEP_ITEMS: dict[int, tuple[ProcedureItem, ...]] = {
    2: (
        _I("khai_mac", "Khai mạc, đọc quyết định đưa vụ án ra xét xử", "item", True, ("301",), first=True),
        _I("kiem_tra_can_cuoc", "Kiểm tra căn cước bị cáo", "item", True, ("301",)),
        _I("kiem_tra_co_mat", "Kiểm tra sự có mặt, giới thiệu thành phần", "item", True, ("301",)),
        _I("giai_thich_quyen", "Phổ biến quyền và nghĩa vụ", "item", True, ("301",)),
        _I("hoi_thay_doi", "Hỏi đề nghị thay đổi người tiến hành tố tụng", "item", True, ("302",)),
        _I("cam_doan_nlc", "Người làm chứng cam đoan, cách ly người làm chứng", "item", True, ("304",),
           requires="witnesses"),
        # Điều 305 says "phải hỏi"; optional until the legal team decides (decision Q6).
        _I("hoi_yeu_cau", "Hỏi yêu cầu triệu tập thêm, xem xét chứng cứ, hoãn phiên tòa", "item", False, ("305",)),
    ),
    3: (
        _I("moi_cong_bo_cao_trang", "Mời Kiểm sát viên công bố cáo trạng", "invite", True, ("306",)),
    ),
    4: (
        _I("hoi_bi_cao", "Hỏi bị cáo (ít nhất 1 câu)", "ask", True, ("307", "309"), ai_calls=1),
        _I("cong_bo_loi_khai_bi_hai", "Công bố lời khai của bị hại vắng mặt", "item", True, ("308",),
           requires="victim_absent"),
        _I("hoi_nguoi_khac", "Hỏi bị hại, người làm chứng, người có quyền lợi, nghĩa vụ liên quan", "ask", False,
           ("310", "311"), requires="others_present", ai_calls=1),
        _I("moi_hoi_tham_hoi", "Mời Hội thẩm hỏi", "invite", False, ("307",), ai_calls=1),
    ),
    5: (
        _I("moi_ksv_hoi", "Mời Kiểm sát viên xét hỏi", "invite", True, ("307",), ai_calls=1),
        _I("moi_ls_hoi", "Mời luật sư xét hỏi", "invite", True, ("307",), ai_calls=1),
        _I("ket_thuc_xet_hoi", "Kết thúc xét hỏi", "item", True, ("318",), last=True),
    ),
    6: (
        _I("moi_luan_toi", "Mời Kiểm sát viên trình bày luận tội", "invite", True, ("320", "321"), ai_calls=1),
    ),
    7: (
        _I("moi_bao_chua", "Mời luật sư bào chữa", "invite", True, ("320",), ai_calls=1),
        _I("moi_bi_hai_trinh_bay", "Mời bị hại trình bày", "invite", True, ("320",), requires="victim_present",
           ai_calls=1),
        _I("hoi_bi_cao_bo_sung", "Hỏi bị cáo có bổ sung ý kiến bào chữa", "invite", False, ("320",), ai_calls=1),
    ),
    8: (
        _I("moi_doi_dap", "Mời đối đáp (vòng 1)", "invite", True, ("322",), ai_calls=2),
        _I("vong_2", "Mời đối đáp thêm (vòng 2)", "invite", False, ("322",), after=("moi_doi_dap",), ai_calls=2,
           note=DEBATE_ROUNDS_NOTE),
        _I("tro_lai_xet_hoi", "Trở lại việc xét hỏi (một lần mỗi phiên)", "return", False, ("323",),
           after=("moi_doi_dap",)),
        _I("ket_thuc_tranh_luan", "Kết thúc tranh luận", "item", True, ("324",), last=True),
    ),
    9: (
        _I("moi_loi_sau_cung", "Cho bị cáo nói lời sau cùng", "invite", True, ("324",), ai_calls=1),
    ),
    10: (
        _I("vao_nghi_an", "Vào phòng nghị án", "item", True, ("326",), first=True),
        _I("y_kien_hoi_tham", "Nghe ý kiến Hội thẩm về bản nháp quyết định", "invite", False, ("326",),
           ai_calls=1),
        _I("chot_quyet_dinh", "Chốt quyết định", "decide", True, ("326",)),
    ),
    11: (
        _I("tuyen_an", "Tuyên án", "pronounce", True, ("327",), ai_calls=1),
    ),
}
# Điều 323 return: a short step 5 (questions and invitations optional, closing required).
RETURN_ITEMS: tuple[ProcedureItem, ...] = (
    _I("hoi_lai", "Hỏi lại (tối đa 3 câu)", "ask", False, ("323",), ai_calls=1),
    _I("moi_ksv_hoi", "Mời Kiểm sát viên hỏi (tối đa 3 câu)", "invite", False, ("307",), ai_calls=1),
    _I("moi_ls_hoi", "Mời luật sư hỏi (tối đa 3 câu)", "invite", False, ("307",), ai_calls=1),
    _I("ket_thuc_xet_hoi", "Kết thúc xét hỏi", "item", True, ("318",), last=True),
)
# Which AI part an invitation runs (trial_turn_service): an existing slot or a presiding-only part.
INVITE_PARTS: dict[str, str] = {
    "moi_cong_bo_cao_trang": "cong_bo_cao_trang", "moi_hoi_tham_hoi": "hoi_tham_hoi", "moi_ksv_hoi": "ksv_hoi",
    "moi_ls_hoi": "ls_hoi", "moi_luan_toi": "luan_toi", "moi_bao_chua": "bao_chua",
    "moi_bi_hai_trinh_bay": "bi_hai_trinh_bay", "hoi_bi_cao_bo_sung": "bi_cao_bo_sung", "moi_doi_dap": "doi_dap",
    "vong_2": "doi_dap", "moi_loi_sau_cung": "loi_sau_cung", "y_kien_hoi_tham": "assessor",
}
DEBATE_ITEMS = frozenset({"moi_doi_dap", "vong_2"})
SPEECHES_PER_ROUND = 2


# --- Catalogue -------------------------------------------------------------------------------------

def _satisfied(requirement: Requirement | None, shape: CaseShape) -> bool:
    if requirement is None:
        return True
    if requirement == "victim_absent":
        return not shape.victim_present
    if requirement == "others_present":
        return len(shape.lay_present_ids()) > 1
    return shape.satisfies(requirement)


def items_for(state: SessionState) -> tuple[ProcedureItem, ...]:
    preside = _preside(state)
    items = RETURN_ITEMS if state.current_step == 5 and preside.in_return else STEP_ITEMS[state.current_step]
    return tuple(i for i in items if _satisfied(i.requires, state.shape)
                 and not (i.kind == "return" and preside.returned))


def _preside(state: SessionState) -> PresideState:
    assert state.preside is not None, "Chủ tọa session without PresideState"
    return state.preside


def missing_required(state: SessionState) -> list[str]:
    done = _preside(state).done
    return [i.key for i in items_for(state) if i.required and i.key not in done]


def is_available(state: SessionState, item: ProcedureItem) -> bool:
    preside = _preside(state)
    done = preside.done
    if item.key in done and item.kind != "ask":   # questions may go on until the cap
        return False
    items = items_for(state)
    if any(i.first and i.key not in done for i in items if i.key != item.key):
        return False
    if item.last and any(i.required and i.key not in done for i in items if i.key != item.key):
        return False
    if any(key not in done for key in item.after):
        return False
    if item.kind == "ask":
        return bool(ask_addressees(state, item))
    if item.kind == "return":
        return "ket_thuc_tranh_luan" not in done and preside.rounds >= 1
    if item.key == "y_kien_hoi_tham":
        return "vao_nghi_an" in done and not preside.decided
    if item.kind == "decide":
        return "vao_nghi_an" in done and not preside.decided
    if item.kind == "pronounce":
        return preside.decided
    if item.key in DEBATE_ITEMS:   # only after a whole earlier round, never while one is half done
        return preside.job is None
    return True


def _question_cap(state: SessionState) -> int:
    return RETURN_MAX_QUESTIONS if _preside(state).in_return else STEP4_MAX_QUESTIONS


def ask_addressees(state: SessionState, item: ProcedureItem | None = None) -> tuple[str, ...]:
    """Who the student may question now (step 4, or the short step 5 of an Điều 323 return)."""
    preside = _preside(state)
    if not (state.current_step == 4 or (state.current_step == 5 and preside.in_return)):
        return ()
    if preside.questions >= _question_cap(state):
        return ()
    people = state.shape.lay_present_ids()
    if item is not None and item.key == "hoi_bi_cao":
        return ("BI_CAO",)
    if item is not None and item.key == "hoi_nguoi_khac":
        return tuple(p for p in people if p != "BI_CAO")
    return people


def remark_addressees(state: SessionState) -> tuple[str, ...]:
    """Who a "phát biểu khác" may be put to; empty when no remark is allowed. Điều 324 khoản 2 BLTTHS:
    "Không được đặt câu hỏi khi bị cáo nói lời sau cùng" - the defendant is left out once invited."""
    preside = _preside(state)
    if state.current_step not in REMARK_STEPS or preside.remarks >= REMARKS_PER_STEP:
        return ()
    if state.current_step == 2 and "khai_mac" not in preside.done:
        return ()
    people = ("KSV", "LUAT_SU", *state.shape.lay_present_ids())
    if state.current_step == 9 and "moi_loi_sau_cung" in preside.done:
        people = tuple(p for p in people if p != "BI_CAO")
    return people


def remark_allowed(state: SessionState) -> bool:
    preside = _preside(state)
    return (state.current_step in REMARK_STEPS and preside.remarks < REMARKS_PER_STEP
            and not (state.current_step == 2 and "khai_mac" not in preside.done))


def advance_target(state: SessionState) -> int:
    return 8 if state.current_step == 5 and _preside(state).in_return else state.current_step + 1


# --- State rules (called by trial_state_machine) ---------------------------------------------------

def allowed_actions(state: SessionState) -> list[str]:
    """The student's actions in a presided step (awaiting == "user"). "decide" is listed whenever
    the step allows it; the route drops it while the stored draft has hard errors."""
    preside = _preside(state)
    available = [i for i in items_for(state) if is_available(state, i)]
    actions: list[str] = []
    items = [i.key for i in available if i.kind == "item"]
    if items:
        actions.append("item:" + "|".join(items))
    asks = ask_addressees(state) if any(i.kind == "ask" for i in available) else ()
    if asks:
        actions.append("ask:" + "|".join(asks))
    invites = [i.key for i in available if i.kind == "invite"]
    if invites:
        actions.append("invite:" + "|".join(invites))
    if remark_allowed(state):
        actions.append("remark")
    if any(i.kind == "return" for i in available):
        actions.append("return_to_questioning")
    if any(i.kind == "decide" for i in available):
        actions.append("decide")
    if any(i.kind == "pronounce" for i in available):
        actions.append("pronounce" if preside.drafted else "prepare_pronouncement")
    if state.current_step < 11 and not missing_required(state):
        actions.append(f"advance:{advance_target(state)}")
    return actions


def _bumped(state: SessionState, preside: PresideState, **changes) -> SessionState:
    return replace(state, preside=preside, pending_ai=preside.job is not None, version=state.version + 1, **changes)


def _check_length(state: SessionState, text: str | None, limit: int, *, required: bool) -> None:
    stripped = (text or "").strip()
    if required and not stripped:
        raise TrialConflict("empty_text", state)
    if len(stripped) > limit:
        raise TrialConflict("text_too_long", state)


def _find(state: SessionState, key: str | None, kinds: tuple[str, ...]) -> ProcedureItem:
    preside = _preside(state)
    item = next((i for i in items_for(state) if i.key == key and i.kind in kinds), None)
    if item is None:
        raise TrialConflict("item_not_available", state, {"item": key})
    if item.key in preside.done and item.kind != "ask":
        raise TrialConflict("item_done", state, {"item": key})
    if not is_available(state, item):
        raise TrialConflict("item_not_available", state, {"item": key})
    return item


def apply_action(state: SessionState, action: UserAction) -> ActionOutcome:
    """Status, version, step and turn are already checked by trial_state_machine.apply_user_action."""
    preside = _preside(state)
    kind = action.kind
    step = state.current_step

    if kind == "advance":
        if step == 11:
            raise TrialConflict("action_not_allowed", state)
        if action.target_step != advance_target(state):
            raise TrialConflict("skip_not_allowed", state)
        missing = missing_required(state)
        if missing:
            raise TrialConflict("procedure_incomplete", state, {"missing_items": missing})
        fresh = replace(preside, done=(), questions=0, remarks=0, rounds=0, in_return=False, job=None)
        moved = replace(state, current_step=advance_target(state), slot_index=0, slot_user_turns=0, preside=fresh,
                        version=state.version + 1)
        return ActionOutcome(_enter(moved), "accepted")

    if kind in ("item", "invite"):
        item = _find(state, action.item, ("item",) if kind == "item" else ("invite",))
        _check_length(state, action.text, ITEM_MAX_CHARS, required=False)
        job = None
        if item.kind == "invite" and item.ai_calls:
            job = PresideJob("assessor" if item.key == "y_kien_hoi_tham" else "invite", item.key)
        return ActionOutcome(_bumped(state, replace(preside, done=(*preside.done, item.key), job=job)), "accepted")

    if kind == "ask":
        item_key = _ask_item(state, action.addressee)
        _check_length(state, action.text, QUESTION_MAX_CHARS, required=True)
        done = preside.done if item_key in preside.done else (*preside.done, item_key)
        job = PresideJob("answer", item_key, action.addressee)
        return ActionOutcome(_bumped(state, replace(preside, done=done, questions=preside.questions + 1, job=job)),
                             "accepted")

    if kind == "remark":
        if not remark_allowed(state):
            raise TrialConflict("turn_limit" if step in REMARK_STEPS else "action_not_allowed", state)
        if action.addressee is not None and action.addressee not in remark_addressees(state):
            raise TrialConflict("missing_addressee", state)
        _check_length(state, action.text, REMARK_MAX_CHARS, required=True)
        job = PresideJob("answer", "remark", action.addressee) if action.addressee else None
        return ActionOutcome(_bumped(state, replace(preside, remarks=preside.remarks + 1, job=job)), "accepted")

    if kind == "return_to_questioning":
        if step != 8:
            raise TrialConflict("return_not_allowed", state)
        if preside.returned:
            raise TrialConflict("return_used", state)
        item = next((i for i in items_for(state) if i.kind == "return"), None)
        if item is None or not is_available(state, item):
            raise TrialConflict("return_not_allowed", state)
        _check_length(state, action.text, ITEM_MAX_CHARS, required=False)
        back = replace(preside, done=(), questions=0, remarks=0, rounds=0, job=None, returned=True, in_return=True)
        return ActionOutcome(_enter(replace(state, current_step=5, slot_index=0, slot_user_turns=0, preside=back,
                                            version=state.version + 1)), "accepted")

    if kind == "decide":
        _find(state, "chot_quyet_dinh", ("decide",))
        return ActionOutcome(_bumped(state, replace(preside, decided=True, done=(*preside.done, "chot_quyet_dinh"))),
                             "accepted")

    if kind == "prepare_pronouncement":
        if step != 11 or not preside.decided or preside.drafted:
            raise TrialConflict("action_not_allowed", state)
        return ActionOutcome(_bumped(state, replace(preside, job=PresideJob("pronounce_draft", "tuyen_an"))),
                             "accepted")

    if kind == "pronounce":
        if step != 11 or not preside.drafted:
            raise TrialConflict("pronouncement_missing", state)
        done = replace(preside, done=(*preside.done, "tuyen_an"))
        return ActionOutcome(replace(state, preside=done, status="completed", pending_ai=False,
                                     version=state.version + 1), "accepted")

    raise TrialConflict("action_not_allowed", state)


def _ask_item(state: SessionState, addressee: str | None) -> str:
    """The checklist item a question counts for, or 409 when no question may be put to `addressee`."""
    if not ask_addressees(state):
        cap_hit = state.current_step == 4 or (state.current_step == 5 and _preside(state).in_return)
        raise TrialConflict("turn_limit" if cap_hit else "action_not_allowed", state)
    if addressee not in ask_addressees(state):
        raise TrialConflict("missing_addressee", state)
    if _preside(state).in_return:
        return "hoi_lai"
    return "hoi_bi_cao" if addressee == "BI_CAO" else "hoi_nguoi_khac"


def with_job(state: SessionState, job: PresideJob) -> SessionState:
    """Adds AI work to an action the state rules accepted without one (an identity question in the
    student's own words: the template question gets a code answer instead)."""
    return replace(state, preside=replace(_preside(state), job=job), pending_ai=True)


def complete_job(state: SessionState) -> SessionState:
    """The AI output of the pending job passed its guards and was stored. A debate round is two
    speeches, the state being stored after each one."""
    preside = _preside(state)
    job = preside.job
    assert job is not None, "no job pending"
    if job.kind == "invite" and job.key in DEBATE_ITEMS:
        if job.progress + 1 < SPEECHES_PER_ROUND:
            return _bumped(state, replace(preside, job=replace(job, progress=job.progress + 1)))
        return _bumped(state, replace(preside, job=None, rounds=preside.rounds + 1))
    if job.kind == "pronounce_draft":
        return _bumped(state, replace(preside, job=None, drafted=True))
    return _bumped(state, replace(preside, job=None))


# --- Stored form (user_work["preside"]) ------------------------------------------------------------

def preside_to_dict(preside: PresideState) -> dict[str, Any]:
    data = asdict(preside)
    data["done"] = list(preside.done)
    return data


def preside_from_dict(data: dict[str, Any] | None) -> PresideState:
    if not data:
        return PresideState()
    job = data.get("job")
    return PresideState(done=tuple(data.get("done") or ()), questions=data.get("questions", 0),
                        remarks=data.get("remarks", 0), rounds=data.get("rounds", 0),
                        job=PresideJob(**job) if job else None, returned=data.get("returned", False),
                        in_return=data.get("in_return", False), decided=data.get("decided", False),
                        drafted=data.get("drafted", False))


# --- "Dùng lời mẫu": templates and procedural answers written by code (0 LLM calls) ----------------
# Placeholder form ({BI_CAO}); rendered with full names for the student, kept as placeholders when
# stored as an AI participant's line. Article numbers are BLTTHS ones checked against the corpus.

_CHAIR_TEMPLATES: dict[str, str] = {
    "kiem_tra_can_cuoc": FALLBACK_QUESTIONS["khai_mac"][0],
    "giai_thich_quyen": "",            # built per case: only the people present (see _rights)
    "hoi_thay_doi": ("Chủ tọa hỏi Kiểm sát viên, bị cáo, người bào chữa và những người tham gia tố tụng có mặt: có ai "
                     "đề nghị thay đổi Thẩm phán, Hội thẩm, Kiểm sát viên, Thư ký phiên tòa hay không? (Điều 302 Bộ "
                     "luật Tố tụng hình sự)"),
    "moi_cong_bo_cao_trang": "Mời Kiểm sát viên {KSV} công bố bản cáo trạng.",
    "hoi_bi_cao": FALLBACK_QUESTIONS["hdxx_hoi_bi_cao"][0],
    "moi_hoi_tham_hoi": "Mời các Hội thẩm nhân dân tham gia xét hỏi.",
    "moi_ksv_hoi": "Mời Kiểm sát viên {KSV} tham gia xét hỏi.",
    "moi_ls_hoi": "Mời luật sư {LUAT_SU} tham gia xét hỏi.",
    "ket_thuc_xet_hoi": ("Xét thấy các tình tiết của vụ án đã được xem xét đầy đủ, Kiểm sát viên, bị cáo, người bào "
                         "chữa và những người tham gia tố tụng không còn yêu cầu xét hỏi thêm, Hội đồng xét xử tuyên "
                         "bố kết thúc phần xét hỏi, chuyển sang phần tranh luận."),
    "moi_luan_toi": "Mời Kiểm sát viên {KSV} trình bày bản luận tội.",
    "moi_bao_chua": "Mời luật sư {LUAT_SU} trình bày lời bào chữa cho bị cáo.",
    "moi_bi_hai_trinh_bay": "Mời bị hại {BI_HAI} trình bày ý kiến để bảo vệ quyền và lợi ích của mình.",
    "hoi_bi_cao_bo_sung": INVITATIONS["moi_bi_cao_bo_sung"],
    "moi_doi_dap": ("Mời Kiểm sát viên {KSV} đối đáp với ý kiến của người bào chữa; sau đó luật sư {LUAT_SU} có quyền "
                    "đáp lại."),
    "vong_2": "Mời Kiểm sát viên và luật sư đối đáp thêm về những ý kiến chưa được tranh luận.",
    "tro_lai_xet_hoi": ("Xét thấy qua tranh luận còn có tình tiết của vụ án chưa được hỏi, chưa được làm sáng tỏ, Hội "
                        "đồng xét xử quyết định trở lại việc xét hỏi."),
    "ket_thuc_tranh_luan": ("Xét thấy không còn ý kiến nào khác, Hội đồng xét xử tuyên bố kết thúc phần tranh "
                            "luận."),
    "moi_loi_sau_cung": "Bị cáo {BI_CAO} được nói lời sau cùng trước khi Hội đồng xét xử vào phòng nghị án.",
    "vao_nghi_an": "Hội đồng xét xử vào phòng nghị án. Đề nghị mọi người giữ trật tự chờ tuyên án.",
}

# Procedural answers (decision Q5): the same whatever the student's own wording of the item.
_NO_CHANGE = {"KSV": "Viện kiểm sát không có đề nghị thay đổi người tiến hành tố tụng.",
              "LUAT_SU": "Tôi không có đề nghị thay đổi người tiến hành tố tụng.",
              "BI_CAO": "Bị cáo không có đề nghị thay đổi người tiến hành tố tụng."}
_NO_REQUEST = {"KSV": "Viện kiểm sát không có yêu cầu.", "LUAT_SU": "Tôi không có yêu cầu.",
               "BI_CAO": "Bị cáo không có yêu cầu."}
WITNESS_OATH = "Tôi xin cam đoan khai báo trung thực."


def _charge(case: CaseFile) -> str:
    charge = case.draft.charge
    diem = f"điểm {', '.join(charge.diem)} " if charge.diem else ""
    return f"{charge.crime_name.lower()} theo {diem}khoản {charge.khoan} Điều {charge.dieu} Bộ luật Hình sự"


def _present_line(shape: CaseShape) -> str:
    present = ["Kiểm sát viên {KSV}", "bị cáo {BI_CAO}", "luật sư {LUAT_SU} bào chữa cho bị cáo"]
    if shape.victim_present:
        present.append("bị hại {BI_HAI}")
    present += [f"người làm chứng {{NLC_{i}}}" for i in range(1, shape.witness_count + 1)]
    if shape.has_related_party:
        present.append("người có quyền lợi, nghĩa vụ liên quan {NLQ}")
    line = "Có mặt: " + "; ".join(present) + "."
    if not shape.victim_present:
        line += " Vắng mặt: bị hại {BI_HAI}, có đơn đề nghị xét xử vắng mặt."
    return line


def _rights(shape: CaseShape) -> str:
    """Only the articles, not their wording: the legal team approves the sentence (decision Q13)."""
    parts = ["bị cáo theo Điều 61"]
    if shape.victim_present:
        parts.append("bị hại theo Điều 62")
    if shape.has_related_party:
        parts.append("người có quyền lợi, nghĩa vụ liên quan theo Điều 65")
    if shape.witness_count:
        parts.append("người làm chứng theo Điều 66")
    return ("Hội đồng xét xử phổ biến quyền và nghĩa vụ của những người tham gia tố tụng có mặt tại phiên tòa: "
            + "; ".join(parts) + " Bộ luật Tố tụng hình sự. Những người tham gia tố tụng có quyền và nghĩa vụ "
            "theo đúng các điều luật này trong suốt phiên tòa.")


def _victim_statement(case: CaseFile) -> str:
    summary = next((s.summary for s in case.draft.pretrial_statements if s.person_id == "BI_HAI"), "")
    return ("Do bị hại {BI_HAI} vắng mặt, Hội đồng xét xử công bố lời khai của bị hại trong giai đoạn điều tra "
            "(điểm d khoản 2 Điều 308 Bộ luật Tố tụng hình sự): " + summary)


def template_placeholders(key: str, case: CaseFile, shape: CaseShape) -> str | None:
    """The "Dùng lời mẫu" text of an item, placeholder form; None when the item has none."""
    if key == "khai_mac":
        return (f"Hôm nay, {case.court.name} mở phiên tòa xét xử sơ thẩm công khai vụ án hình sự đối với bị cáo "
                f"{{BI_CAO}}, bị Viện kiểm sát truy tố về {_charge(case)}. Tôi tuyên bố khai mạc phiên tòa và đọc "
                "quyết định đưa vụ án ra xét xử (số hiệu giả định).")
    if key == "kiem_tra_co_mat":
        return ("Hội đồng xét xử kiểm tra sự có mặt của những người được triệu tập theo báo cáo của Thư ký phiên tòa. "
                + _present_line(shape) + " Thành phần Hội đồng xét xử gồm: Thẩm phán - Chủ tọa phiên tòa {CHU_TOA}; "
                "Hội thẩm nhân dân {HOI_THAM_1} và {HOI_THAM_2}; Thư ký phiên tòa {THU_KY}.")
    if key == "giai_thich_quyen":
        return _rights(shape)
    if key == "cam_doan_nlc":
        people = ", ".join(f"{{NLC_{i}}}" for i in range(1, shape.witness_count + 1))
        return (f"Đề nghị người làm chứng {people} cam đoan khai báo trung thực. Hội đồng xét xử quyết định cách ly "
                "người làm chứng: người làm chứng chưa được hỏi không được nghe lời khai của người khác (Điều 304 Bộ "
                "luật Tố tụng hình sự).")
    if key == "hoi_yeu_cau":
        text = ("Có ai yêu cầu triệu tập thêm người làm chứng hoặc yêu cầu đưa thêm vật chứng, tài liệu ra xem xét hay "
                "không?")
        if not shape.victim_present:
            text += " Bị hại {BI_HAI} vắng mặt; có ai yêu cầu hoãn phiên tòa hay không?"
        return text + " (Điều 305 Bộ luật Tố tụng hình sự)"
    if key == "cong_bo_loi_khai_bi_hai":
        return _victim_statement(case)
    return _CHAIR_TEMPLATES.get(key) or None


def template_text(key: str, case: CaseFile, shape: CaseShape) -> str | None:
    """Rendered with full names, as the student would say it."""
    text = template_placeholders(key, case, shape)
    return render(text, case.participants) if text else None


def code_answers(key: str, shape: CaseShape, *, own_identity_question: bool) -> list[tuple[str, str]]:
    """(speaker_id, placeholder text) of the procedural answers code writes after an item.
    The identity answer is code only when the student used the template question (decision Q5);
    a question in the student's own words gets an AI answer instead."""
    if key == "kiem_tra_can_cuoc" and not own_identity_question:
        return [("BI_CAO", "")]   # filled by the caller with trial_defendant.identity_prefill
    if key == "hoi_thay_doi":
        return list(_NO_CHANGE.items())
    if key == "cam_doan_nlc":
        return [(f"NLC_{i}", WITNESS_OATH) for i in range(1, shape.witness_count + 1)]
    if key == "hoi_yeu_cau":
        return list(_NO_REQUEST.items())
    return []


# --- Measure-only guard: an AI line taking over the presiding (decision 14) ------------------------

_USURPS = re.compile(
    r"tuyên bố (?:kết thúc|khai mạc|tạm ngừng)|chuyển sang phần|cho (?:phép )?chuyển sang"
    r"|hội đồng xét xử\s+(?:đã\s+|quyết định\s+)?(?:quyết định|chấp nhận|cho phép|bác)"
    r"|chủ tọa\s+(?:đã\s+|vừa\s+)?(?:đồng ý|cho phép|chấp nhận|quyết định)"
    r"|mời\s+(?:\{[A-Z_0-9]+\}|kiểm sát viên|luật sư|bị cáo|bị hại|người làm chứng)\s+(?:trình bày|phát biểu|tiếp tục)",
    re.IGNORECASE)
# A party asking the panel for something is not taking over: "đề nghị Hội đồng xét xử chấp nhận...".
_REQUEST_BEFORE = re.compile(r"(?:đề nghị|kiến nghị|mong|xin|yêu cầu|kính đề nghị|kính mong)\s*(?:\S+\s+){0,2}$",
                             re.IGNORECASE)


def usurps_presiding(text: str) -> bool:
    for match in _USURPS.finditer(text):
        if not _REQUEST_BEFORE.search(text[max(0, match.start() - 40):match.start()]):
            return True
    return False


# --- View for the client ---------------------------------------------------------------------------

def presiding_view(state: SessionState, case: CaseFile) -> dict[str, Any]:
    preside = _preside(state)
    items = []
    for item in items_for(state):
        items.append({
            "key": item.key, "label": item.label, "kind": item.kind, "required": item.required,
            "done": item.key in preside.done, "available": awaiting_user(state) and is_available(state, item),
            "template": template_text(item.key, case, state.shape), "basis": list(item.basis),
            "ai_calls": item.ai_calls, "note": item.note,
        })
    questioning = state.current_step == 4 or (state.current_step == 5 and preside.in_return)
    return {
        "step": state.current_step, "items": items, "missing_required": missing_required(state),
        "counters": {
            "questions_left": max(0, _question_cap(state) - preside.questions) if questioning else 0,
            "remarks_left": max(0, REMARKS_PER_STEP - preside.remarks) if state.current_step in REMARK_STEPS else 0,
            "debate_rounds": preside.rounds,
        },
        "ask_addressees": list(ask_addressees(state)), "remark_addressees": list(remark_addressees(state)),
        "limits": {k: {"min": lo, "max": hi} for k, (lo, hi) in TEXT_LIMITS.items()},
        "return_available": "return_to_questioning" in allowed_actions(state) if awaiting_user(state) else False,
        "returned": preside.returned, "in_return": preside.in_return,
        "templates_reviewed": TEMPLATES_REVIEWED,
    }


def awaiting_user(state: SessionState) -> bool:
    return state.status == "active" and not state.pending_ai
