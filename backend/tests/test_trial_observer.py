"""Unit tests for chặng R1: the Người xem role (design doc Mục 11.1), SlotSpec.user_roles, the AI-AI
debate, the procedure notes and the configured court/prosecutor names. No Gemini call."""
from __future__ import annotations

import asyncio
import json
import unittest
from dataclasses import dataclass, field, replace
from types import SimpleNamespace

from pydantic import ValidationError

from app.models.trial import CaseDraft
from app.models.trial_api import TrialCreateRequest
from app.services.gemini_client import GeminiJsonResult
from app.services.trial_case_frame import offices_text
from app.services.trial_case_validator import error_label, office_name_mismatches, validate_case_draft
from app.services.trial_config import BLTTHS_STEP_SLICES, DEFAULT_COURT_NAME, court_name, get_crime, procuracy_name
from app.services.trial_metrics import CallRecord, TrialCallRecorder
from app.services.trial_procedure_notes import MAX_NOTE_WORDS, PROCEDURE_NOTES, PROCEDURE_NOTES_REVIEWED, procedure_note
from app.services.trial_session_service import state_out
from app.services.trial_state_machine import (
    AI_DEBATE_ROUNDS,
    ENABLED_USER_ROLES,
    STEPS,
    CaseShape,
    SlotSpec,
    StepSpec,
    TrialConflict,
    UserAction,
    active_slots,
    ai_speaker_ids,
    allowed_actions,
    apply_user_action,
    awaiting,
    complete_ai_turn,
    current_slot,
    is_user_slot,
    new_session,
    text_limits,
)
from app.services import trial_state_machine
from app.services.trial_turn_service import TrialContext, _check_utterance, _system_prompt, run_ai_turn
from tests.trial_fixtures import pack_for, valid_case_file, valid_draft_dict, valid_knobs, valid_options

SHAPE = CaseShape(victim_present=True, witness_count=2, has_related_party=True)
COURT = "Tòa án nhân dân khu vực 3, tỉnh Y"


def _drive(state, on_ai=complete_ai_turn):
    """Runs a whole Người xem hearing on the state machine alone; returns every state seen while it
    was the student's turn."""
    seen = []
    while state.status == "active":
        if awaiting(state) == "ai":
            state = on_ai(state)
            continue
        seen.append(state)
        state = apply_user_action(state, UserAction("advance", state.current_step, state.version,
                                                    target_step=state.current_step + 1)).state
    return state, seen


class ObserverStateMachineTests(unittest.TestCase):
    def test_role_enabled_and_no_slot_is_the_students(self):
        self.assertIn("nguoi_xem", ENABLED_USER_ROLES)
        for step in STEPS:
            for slot in active_slots(step.number, SHAPE, "nguoi_xem"):
                self.assertFalse(is_user_slot(slot, "nguoi_xem"), slot.key)

    def test_only_advance_between_steps_and_text_limits_null(self):
        final, seen = _drive(new_session("nguoi_xem", SHAPE))
        self.assertEqual(final.status, "completed")
        self.assertEqual(len(seen), 10)   # after steps 1-10; step 11 ends the hearing
        for state in seen:
            self.assertIsNone(current_slot(state))
            self.assertEqual(allowed_actions(state), [f"advance:{state.current_step + 1}"])
            self.assertIsNone(text_limits(state))

    def test_speak_and_end_slot_always_409(self):
        state = new_session("nguoi_xem", SHAPE)
        _, seen = _drive(state)
        for waiting in [state, *seen]:
            for kind in ("speak", "end_slot"):
                with self.assertRaises(TrialConflict) as caught:
                    apply_user_action(waiting, UserAction(kind, waiting.current_step, waiting.version, text="Tôi xin nói."))
                self.assertIn(caught.exception.code, ("action_not_allowed", "not_your_turn"))

    def test_ai_ai_debate_is_two_turns_ksv_then_luat_su(self):
        state = new_session("nguoi_xem", SHAPE)
        debate_turns = []

        def on_ai(s):
            slot = current_slot(s)
            if slot.key == "doi_dap":
                debate_turns.append(trial_state_machine.debate_speaker_role(slot, s.slot_user_turns))
            return complete_ai_turn(s)

        _drive(state, on_ai)
        self.assertEqual(debate_turns, ["ksv", "luat_su"] * AI_DEBATE_ROUNDS)

    def test_ksv_and_luat_su_debates_unchanged(self):
        ksv = replace(new_session("ksv", SHAPE), current_step=8, slot_index=0)
        self.assertEqual(awaiting(trial_state_machine._enter(ksv)), "user")
        ls = trial_state_machine._enter(replace(new_session("luat_su", SHAPE), current_step=8, slot_index=0))
        self.assertEqual(awaiting(ls), "ai")
        after = complete_ai_turn(ls)                   # AI KSV opened; the student answers
        self.assertEqual(awaiting(after), "user")
        self.assertEqual(after.slot_index, 0)

    def test_observer_speaker_enum_excludes_nobody(self):
        state = new_session("nguoi_xem", SHAPE)
        slot = STEPS[1].slots[0]   # khai mạc: chu_toa + bi_cao
        self.assertEqual(ai_speaker_ids(slot, state), ("CHU_TOA", "BI_CAO"))
        ksv_slot = next(s for s in STEPS[4].slots if s.key == "ksv_hoi")
        self.assertNotIn("KSV", ai_speaker_ids(replace(ksv_slot, speakers=("ksv", "bi_cao")), new_session("ksv", SHAPE)))

    def test_slot_user_roles_filters_by_role(self):
        extra = SlotSpec("chi_bi_cao", "chu_toa", "segment", speakers=("chu_toa",), user_roles=frozenset({"bi_cao"}))
        original = trial_state_machine.STEP_BY_NUMBER[9]
        patched = StepSpec(9, original.title, original.legal_basis, (*original.slots, extra))
        trial_state_machine.STEP_BY_NUMBER[9] = patched
        try:
            self.assertIn("chi_bi_cao", [s.key for s in active_slots(9, SHAPE, "bi_cao")])
            self.assertNotIn("chi_bi_cao", [s.key for s in active_slots(9, SHAPE, "ksv")])
            self.assertNotIn("chi_bi_cao", [s.key for s in active_slots(9, SHAPE, "nguoi_xem")])
        finally:
            trial_state_machine.STEP_BY_NUMBER[9] = original

    def test_request_accepts_only_enabled_roles(self):
        TrialCreateRequest(crime_key="blhs_173", user_role="nguoi_xem")
        for role in ("chu_toa", "admin"):
            with self.assertRaises(ValidationError):
                TrialCreateRequest(crime_key="blhs_173", user_role=role)
        with self.assertRaises(ValueError):
            new_session("chu_toa", SHAPE)


@dataclass
class _Recorder(TrialCallRecorder):
    answers: list[str] = field(default_factory=list)
    systems: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)

    async def call(self, settings, *, call_type, slot, attempt, system_prompt, user_prompt, response_schema,
                   thinking_level, temperature, **_):
        self.systems.append(system_prompt)
        self.prompts.append(user_prompt)
        record = CallRecord(call_type, slot, attempt, 0.0, 0, 0, 0, 0, thinking_level)
        self.records.append(record)
        return GeminiJsonResult(self.answers.pop(0), "fake", 0.0, 0, 0, 0, 0, "STOP"), record


def _ctx(role: str, answers: list[str] | None = None, court: str | None = None) -> TrialContext:
    case = valid_case_file()
    if court:
        case = case.model_copy(update={"court": case.court.model_copy(update={"name": court})})
    shape = CaseShape(victim_present=True, witness_count=1, has_related_party=False)
    return TrialContext(case=case, pack=pack_for("blhs_173"), state=new_session(role, shape), settings=None,
                        recorder=_Recorder(answers=answers or []))


SPEECH = json.dumps({"text": "Về ý kiến của phía bên kia:\n\nĐề nghị Hội đồng xét xử xem xét theo khoản 1 Điều "
                             "173 Bộ luật Hình sự."}, ensure_ascii=False)


class ObserverTurnTests(unittest.TestCase):
    def test_no_student_id_and_observer_system_prompt(self):
        ctx = _ctx("nguoi_xem", court=COURT)
        self.assertIsNone(ctx.student_id)
        prompt = _system_prompt(ctx)
        self.assertIn("quan sát", prompt)
        self.assertNotIn("không tự nhận thay", prompt)
        self.assertIn(COURT, prompt)
        self.assertIn("Viện kiểm sát nhân dân khu vực 3, tỉnh Y", prompt)
        self.assertNotIn("{", prompt.split("QUY TẮC BẮT BUỘC")[0].replace("{{", ""))

    def test_player_prompt_keeps_the_rule_and_gains_the_offices(self):
        prompt = _system_prompt(_ctx("ksv"))
        self.assertIn("Người học đang đóng vai Kiểm sát viên ({KSV})", prompt)
        self.assertIn("không tự nhận thay Kiểm sát viên — vai đó do người học đóng.", prompt)
        self.assertIn("Tòa án nhân dân [test]", prompt)

    def test_ai_debate_runs_two_separate_speeches(self):
        ctx = _ctx("nguoi_xem", answers=[SPEECH, SPEECH])
        ctx.state = trial_state_machine._enter(replace(ctx.state, current_step=8, slot_index=0, slot_user_turns=0))
        first = asyncio.run(run_ai_turn(ctx))
        self.assertEqual([u.speaker_id for u in first], ["KSV"])
        self.assertEqual(current_slot(ctx.state).key, "doi_dap")
        second = asyncio.run(run_ai_turn(ctx))
        self.assertEqual([u.speaker_id for u in second], ["LUAT_SU"])
        self.assertEqual(current_slot(ctx.state).key, "ket_thuc_tranh_luan")
        self.assertIn("Luật sư bào chữa", ctx.recorder.prompts[0].split("CHỈ DẪN LƯỢT")[1])
        self.assertIn("Kiểm sát viên", ctx.recorder.prompts[1].split("CHỈ DẪN LƯỢT")[1])

    def test_wrong_office_name_is_flagged_not_blocked(self):
        ctx = _ctx("nguoi_xem", court=COURT)
        _, flags = _check_utterance(ctx, "CHU_TOA", "Tòa án nhân dân tỉnh Y mở phiên tòa.", ("CHU_TOA",))
        self.assertIn("office_name", flags)
        violations, flags = _check_utterance(ctx, "CHU_TOA", f"{COURT} mở phiên tòa.", ("CHU_TOA",))
        self.assertNotIn("office_name", flags)
        self.assertEqual(violations, [])


class ProcedureNoteTests(unittest.TestCase):
    def test_eleven_short_notes_citing_hearing_articles(self):
        hearing_articles = {n for slice_ in BLTTHS_STEP_SLICES.values() for n in slice_}
        self.assertEqual(sorted(PROCEDURE_NOTES), list(range(1, 12)))
        for step, note in PROCEDURE_NOTES.items():
            self.assertLessEqual(len(note.text.split()), MAX_NOTE_WORDS, step)
            self.assertTrue(note.legal_basis)
            self.assertTrue(set(note.legal_basis) <= hearing_articles, (step, note.legal_basis))
        self.assertTrue(PROCEDURE_NOTES_REVIEWED)   # approved 2026-10-29 from the verification report

    def test_state_carries_the_note_for_observers_only(self):
        observer = state_out("00000000-0000-0000-0000-000000000001", new_session("nguoi_xem", SHAPE))
        self.assertEqual(observer.procedure_note.step, 1)
        self.assertEqual(observer.procedure_note.model_dump(), procedure_note(1))
        self.assertTrue(observer.procedure_note.reviewed)
        for role in ("ksv", "luat_su"):
            self.assertIsNone(state_out("00000000-0000-0000-0000-000000000001", new_session(role, SHAPE)).procedure_note)


class OfficeNameTests(unittest.TestCase):
    def test_defaults_and_derivation(self):
        self.assertEqual(court_name(SimpleNamespace(trial_court_name=None)), DEFAULT_COURT_NAME)
        self.assertEqual(court_name(SimpleNamespace(trial_court_name="  ")), DEFAULT_COURT_NAME)
        self.assertEqual(court_name(SimpleNamespace(trial_court_name=COURT)), COURT)
        self.assertEqual(DEFAULT_COURT_NAME, "Tòa án nhân dân khu vực 1, tỉnh X")
        self.assertEqual(procuracy_name(COURT), "Viện kiểm sát nhân dân khu vực 3, tỉnh Y")
        text = offices_text(COURT, procuracy_name(COURT))
        self.assertIn(COURT, text)
        self.assertIn("Viện kiểm sát nhân dân khu vực 3, tỉnh Y", text)

    def test_mismatch_detection(self):
        ok = ("VIỆN KIỂM SÁT NHÂN DÂN KHU VỰC 1, TỈNH X\nSố: 12/CT-VKS\n... truy tố ra Tòa án nhân dân khu vực 1, "
              "tỉnh X để xét xử. Viện kiểm sát nhân dân đã xem xét; Tòa án nhân dân tối cao; Viện kiểm sát cùng cấp.")
        self.assertEqual(office_name_mismatches(ok, DEFAULT_COURT_NAME), [])
        bad = "Viện kiểm sát nhân dân tỉnh X truy tố ra Toà án nhân dân khu vực 12, tỉnh X; Tòa án nhân dân huyện Z."
        self.assertEqual(office_name_mismatches(bad, DEFAULT_COURT_NAME),
                         ["viện kiểm sát nhân dân tỉnh x", "toà án nhân dân khu vực 12, tỉnh x",
                          "tòa án nhân dân huyện z"])

    def test_validator_rejects_other_offices_only_when_a_court_is_given(self):
        draft_dict = valid_draft_dict()
        draft_dict["indictment_text"] = "VIỆN KIỂM SÁT NHÂN DÂN TỈNH X\n\n" + draft_dict["indictment_text"]
        draft = CaseDraft.model_validate(draft_dict)
        args = (draft, valid_options(), get_crime("blhs_173"), pack_for("blhs_173"), valid_knobs())
        errors = validate_case_draft(*args, court=DEFAULT_COURT_NAME)
        self.assertEqual([error_label(e) for e in errors], ["office_name"])
        self.assertIn("Viện kiểm sát nhân dân khu vực 1, tỉnh X", errors[0])
        self.assertEqual(validate_case_draft(*args), [])
        fixed = CaseDraft.model_validate({**draft_dict, "indictment_text": draft_dict["indictment_text"].replace(
            "VIỆN KIỂM SÁT NHÂN DÂN TỈNH X", "VIỆN KIỂM SÁT NHÂN DÂN KHU VỰC 1, TỈNH X")})
        self.assertEqual(validate_case_draft(fixed, *args[1:], court=DEFAULT_COURT_NAME), [])


if __name__ == "__main__":
    unittest.main()
