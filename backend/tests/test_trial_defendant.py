"""Unit tests for chặng R3: the Bị cáo role (design doc Mục 11.2, decisions 9-14 of 11.8) - the đoạn
xen (Mục 11.0b), "Từ chối trả lời", the optional turns of steps 7-8, the role card, and the
measure-only guards. No Gemini call."""
from __future__ import annotations

import asyncio
import json
import unittest
from dataclasses import replace

from app.models.trial_api import TrialPendingQuestion
from app.prompts.trial_prompts import DEFENDANT_TESTIMONY_RULES, DEFENDANT_VERDICT_NOTE
from app.services import trial_state_machine
from app.services.trial_defendant import (
    DECLINE_NOTE,
    DECLINE_TEXT,
    FALLBACK_QUESTIONS,
    OPT_OUT_TEXTS,
    identity_prefill,
    role_brief,
)
from app.services.trial_session_service import state_out
from app.services.trial_state_machine import (
    STEPS,
    CaseShape,
    TrialConflict,
    UserAction,
    active_slots,
    allowed_actions,
    awaiting,
    complete_ai_turn,
    current_slot,
    is_interleaved,
    is_user_slot,
    new_session,
    text_limits,
)
from app.services.trial_turn_service import (
    STUDENT_QUESTION_FLAG,
    TrialGuardFailure,
    _check_utterance,
    _deliberate,
    _system_prompt,
    apply_student_action,
    run_ai_turn,
)
from tests.test_trial_observer import _ctx
from tests.trial_fixtures import valid_case_file

SHAPE = CaseShape(victim_present=True, witness_count=1, has_related_party=False)
ROLES = ("ksv", "luat_su", "nguoi_xem", "thu_ky", "bi_cao")
INTERLEAVED = ["khai_mac", "hdxx_hoi_bi_cao", "ksv_hoi", "ls_hoi", "loi_sau_cung"]
DEFENDANT_SLOTS = ["moi_bi_cao_bo_sung", "bi_cao_bo_sung_bao_chua", "moi_bi_cao_tranh_luan", "bi_cao_tranh_luan"]
GOOD_VERDICT = json.dumps({"guilty": True, "dieu": "173", "khoan": "1", "diem": [], "penalty_type": "tu",
                           "penalty_months": 12, "fine_vnd": None, "suspended": False, "probation_months": None,
                           "applies_dieu_54": False, "mitigating": [{"khoan": "1", "diem": "s", "fact_ids": ["F2"]}],
                           "aggravating": [], "civil_amount_vnd": None, "reasoning_summary": "Nhận định."})


def seg(lines: list[tuple[str, str]], question: tuple[str, str] | None = None, facts: list | None = None) -> str:
    out = {"utterances": [{"speaker_id": s, "text": t} for s, t in lines], "new_facts": facts or []}
    out["cau_hoi_cho_nguoi_hoc"] = {"speaker_id": question[0], "text": question[1]} if question else None
    return json.dumps(out, ensure_ascii=False)


def at(ctx, key: str, turns: int = 0):
    """Moves the context onto slot `key` with `turns` questions already answered."""
    for step in STEPS:
        keys = [s.key for s in active_slots(step.number, ctx.state.shape, ctx.state.user_role)]
        if key in keys:
            ctx.state = trial_state_machine._enter(replace(ctx.state, current_step=step.number,
                                                           slot_index=keys.index(key), slot_user_turns=turns))
            if turns:
                ctx.state = replace(ctx.state, pending_ai=True)
            return ctx
    raise KeyError(key)


def act(ctx, kind: str, **kw):
    return apply_student_action(ctx, UserAction(kind, ctx.state.current_step, ctx.state.version, **kw))


class DefendantSlotTests(unittest.TestCase):
    def test_defendant_slots_exist_for_this_role_only(self):
        for role in ROLES:
            keys = [s.key for step in STEPS for s in active_slots(step.number, SHAPE, role)]
            for key in DEFENDANT_SLOTS:
                self.assertEqual(key in keys, role == "bi_cao", (role, key))

    def test_which_slots_are_the_students(self):
        slots = [s for step in STEPS for s in active_slots(step.number, SHAPE, "bi_cao")]
        self.assertEqual([s.key for s in slots if is_user_slot(s, "bi_cao")],
                         ["bi_cao_bo_sung_bao_chua", "bi_cao_tranh_luan"])
        self.assertEqual([s.key for s in slots if is_interleaved(s, "bi_cao")], INTERLEAVED)
        for role in ("ksv", "luat_su", "nguoi_xem", "thu_ky"):   # no đoạn xen for any other role
            others = [s for step in STEPS for s in active_slots(step.number, SHAPE, role)]
            self.assertEqual([s.key for s in others if is_interleaved(s, role)], [], role)

    def test_question_caps_follow_decision_13(self):
        caps = {s.key: (s.max_questions, s.decline) for step in STEPS for s in step.slots if s.max_questions}
        self.assertEqual(caps, {"khai_mac": (2, False), "hdxx_hoi_bi_cao": (4, True), "ksv_hoi": (3, True),
                                "ls_hoi": (3, True), "loi_sau_cung": (1, False)})
        questioning = sum(caps[k][0] for k in ("hdxx_hoi_bi_cao", "ksv_hoi", "ls_hoi"))
        self.assertEqual(questioning, 10)

    def test_minimum_never_exceeds_the_cap(self):
        for step in STEPS:
            for slot in step.slots:
                self.assertLessEqual(slot.min_questions, slot.max_questions, slot.key)
                self.assertGreaterEqual(slot.max_questions, 0, slot.key)
        unchanged = {s.key: (s.min_user_turns, s.max_user_turns) for step in STEPS for s in step.slots
                     if s.key in ("ksv_hoi", "ls_hoi", "doi_dap")}
        self.assertEqual(unchanged, {"ksv_hoi": (1, 8), "ls_hoi": (1, 8), "doi_dap": (1, 3)})

    def test_questioning_ends_at_the_new_cap_and_the_hearing_moves_on(self):
        for key, cap, after in (("hdxx_hoi_bi_cao", 4, "hdxx_hoi_nguoi_khac"), ("ksv_hoi", 3, "ls_hoi"),
                                ("ls_hoi", 3, "ket_thuc_xet_hoi")):
            ctx = at(_ctx("bi_cao"), key)
            for _ in range(cap):
                ctx.state = complete_ai_turn(ctx.state, asked_student=True)
                self.assertEqual(awaiting(ctx.state), "user", key)
                act(ctx, "speak", text="Dạ.")
            self.assertEqual(ctx.state.slot_user_turns, cap)
            ctx.state = complete_ai_turn(ctx.state, asked_student=True)   # a question past the cap is dropped
            self.assertEqual(current_slot(ctx.state).key, after, key)

    def test_khai_mac_runs_two_questions_then_closes(self):
        state = replace(new_session("bi_cao", SHAPE), current_step=2)
        state = trial_state_machine._enter(state)
        self.assertEqual(awaiting(state), "ai")
        state = complete_ai_turn(state, asked_student=True)          # identity question
        self.assertEqual((awaiting(state), allowed_actions(state), text_limits(state)), ("user", ["speak"], (1, 1500)))
        for code, kind in (("action_not_allowed", "end_slot"), ("action_not_allowed", "decline")):
            with self.assertRaises(TrialConflict) as caught:
                trial_state_machine.apply_user_action(state, UserAction(kind, 2, state.version))
            self.assertEqual(caught.exception.code, code)
        state = trial_state_machine.apply_user_action(state, UserAction("speak", 2, state.version, text="Dạ.")).state
        self.assertEqual((awaiting(state), state.slot_user_turns), ("ai", 1))
        state = complete_ai_turn(state, asked_student=True)          # change of judges question
        state = trial_state_machine.apply_user_action(state, UserAction("speak", 2, state.version, text="Không ạ.")).state
        self.assertEqual(awaiting(state), "ai")                       # the AI closes the slot
        state = complete_ai_turn(state, asked_student=True)          # a question past the cap is not one
        self.assertEqual(current_slot(state).key, "y_kien_ksv_thay_doi")

    def test_ai_closing_the_slot_moves_on(self):
        state = trial_state_machine._enter(replace(new_session("bi_cao", SHAPE), current_step=5))
        self.assertEqual(current_slot(state).key, "ksv_hoi")
        state = complete_ai_turn(state, asked_student=False)
        self.assertEqual(current_slot(state).key, "ls_hoi")

    def test_last_words_close_on_the_answer_without_an_ai_call(self):
        state = trial_state_machine._enter(replace(new_session("bi_cao", SHAPE), current_step=9))
        state = complete_ai_turn(state, asked_student=True)
        self.assertEqual(text_limits(state), (1, 3000))
        state = trial_state_machine.apply_user_action(state, UserAction("speak", 9, state.version, text="Xin khoan hồng.")).state
        self.assertEqual((awaiting(state), allowed_actions(state)), ("user", ["advance:10"]))

    def test_optional_turns_of_steps_7_and_8(self):
        ctx = at(_ctx("bi_cao"), "bi_cao_bo_sung_bao_chua")
        self.assertEqual((allowed_actions(ctx.state), text_limits(ctx.state)), (["speak", "end_slot"], (1, 3000)))
        produced = act(ctx, "end_slot")
        self.assertEqual([(u.text, u.kind, u.is_user) for u in produced],
                         [(OPT_OUT_TEXTS["bi_cao_bo_sung_bao_chua"], "procedural", True)])
        at(ctx, "bi_cao_tranh_luan")
        self.assertEqual((allowed_actions(ctx.state), text_limits(ctx.state)), (["speak", "end_slot"], (1, 3000)))
        act(ctx, "speak", text="Tôi đề nghị Hội đồng xét xử xem xét hoàn cảnh của tôi.")
        self.assertEqual(awaiting(ctx.state), "ai")
        ctx.recorder.answers = [json.dumps({"text": "Về ý kiến của bị cáo:\n\nĐề nghị giữ nguyên quan điểm luận tội "
                                                    "theo khoản 1 Điều 173 Bộ luật Hình sự."}, ensure_ascii=False)]
        produced = asyncio.run(run_ai_turn(ctx))
        self.assertEqual([u.speaker_id for u in produced], ["KSV"])
        self.assertIn("Bị cáo", ctx.recorder.prompts[-1].split("CHỈ DẪN LƯỢT")[1])
        self.assertEqual(current_slot(ctx.state).key, "ket_thuc_tranh_luan")

    def test_decline_counts_as_an_answer_and_is_recorded(self):
        ctx = at(_ctx("bi_cao"), "hdxx_hoi_bi_cao")
        ctx.state = complete_ai_turn(ctx.state, asked_student=True)
        self.assertEqual(allowed_actions(ctx.state), ["speak", "decline"])
        produced = act(ctx, "decline")
        self.assertEqual([(u.speaker_id, u.text, u.kind, u.is_user, u.guard_flags) for u in produced],
                         [("BI_CAO", DECLINE_TEXT, "procedural", True, ["declined"])])
        self.assertEqual((awaiting(ctx.state), ctx.state.slot_user_turns), ("ai", 1))

    def test_decline_is_refused_outside_questioning_and_for_other_roles(self):
        for role in ("ksv", "luat_su", "thu_ky"):
            ctx = _ctx(role)
            ctx.state = replace(ctx.state, pending_ai=False)
            with self.assertRaises(TrialConflict):
                act(ctx, "decline")

    def test_bad_answers(self):
        ctx = at(_ctx("bi_cao"), "hdxx_hoi_bi_cao")
        ctx.state = complete_ai_turn(ctx.state, asked_student=True)
        for text, code in (("   ", "empty_text"), ("x" * 1501, "text_too_long")):
            with self.assertRaises(TrialConflict) as caught:
                act(ctx, "speak", text=text)
            self.assertEqual(caught.exception.code, code)
        with self.assertRaises(TrialConflict) as caught:
            apply_student_action(ctx, UserAction("speak", 4, ctx.state.version - 1, text="Dạ."))
        self.assertEqual(caught.exception.code, "version_mismatch")
        with self.assertRaises(TrialConflict) as caught:
            apply_student_action(ctx, UserAction("speak", 5, ctx.state.version, text="Dạ."))
        self.assertEqual(caught.exception.code, "step_mismatch")
        produced = act(ctx, "speak", text="Cho tôi nói lời sau cùng luôn.")      # skip detector unchanged
        self.assertEqual([u.kind for u in produced], ["speech", "notice"])
        self.assertEqual((awaiting(ctx.state), ctx.state.slot_user_turns, ctx.state.current_step), ("user", 0, 4))


class InterleavedTurnTests(unittest.TestCase):
    def test_the_call_stops_at_the_question_and_cannot_hold_the_answer(self):
        ctx = at(_ctx("bi_cao", answers=[seg([("CHU_TOA", "Hôm nay Tòa án mở phiên tòa xét xử vụ án.")],
                                              ("CHU_TOA", "Đề nghị bị cáo cho biết lý lịch."))]), "khai_mac")
        schemas = []
        call = ctx.recorder.call

        async def spy(settings, **kw):
            schemas.append(kw["response_schema"])
            return await call(settings, **kw)
        ctx.recorder.call = spy
        produced = asyncio.run(run_ai_turn(ctx))
        schema = schemas[0]["properties"]
        self.assertEqual(schema["utterances"]["items"]["properties"]["speaker_id"]["enum"], ["CHU_TOA"])
        self.assertEqual(schema["cau_hoi_cho_nguoi_hoc"]["properties"]["speaker_id"]["enum"], ["CHU_TOA"])
        self.assertEqual(produced[-1].guard_flags, [STUDENT_QUESTION_FLAG])
        self.assertEqual((awaiting(ctx.state), allowed_actions(ctx.state)), ("user", ["speak"]))
        prompt = ctx.recorder.prompts[0]
        self.assertIn("ĐÚNG MỘT câu hỏi cho {BI_CAO}", prompt)
        self.assertIn(DEFENDANT_TESTIMONY_RULES.format()[:60], prompt)
        self.assertIn("Người học đang đóng vai Bị cáo ({BI_CAO})", ctx.recorder.systems[0])
        out = state_out("00000000-0000-0000-0000-000000000000", ctx.state, case=ctx.case, transcript=ctx.transcript)
        self.assertEqual(out.pending_question, TrialPendingQuestion(
            seq=produced[-1].seq, speaker_id="CHU_TOA", speaker_role="Chủ tọa",
            speaker_name=ctx.case.participants["CHU_TOA"].name, text="Đề nghị bị cáo cho biết lý lịch.",
            prefill=identity_prefill(ctx.case), decline_note=None))

    def test_answer_typed_into_the_question_is_cut(self):
        ctx = at(_ctx("bi_cao", answers=[seg([], ("HOI_THAM_1", "Bị cáo có ăn năn không?\n{BI_CAO}: Dạ có ạ."))]),
                 "hdxx_hoi_bi_cao")
        produced = asyncio.run(run_ai_turn(ctx))
        self.assertEqual(produced[-1].text, "Bị cáo có ăn năn không?")
        self.assertIn("question_trimmed", produced[-1].guard_flags)

    def test_ai_speaking_as_the_defendant_is_rejected(self):
        bad = seg([("BI_CAO", "Dạ, tôi xin nhận tội.")], ("CHU_TOA", "Bị cáo còn gì trình bày không?"))
        ctx = at(_ctx("bi_cao", answers=[bad, bad]), "hdxx_hoi_bi_cao")
        with self.assertRaises(TrialGuardFailure) as caught:
            asyncio.run(run_ai_turn(ctx))
        self.assertIn("speaker_is_student", caught.exception.violations)
        self.assertEqual([u for u in ctx.transcript if u.speaker_id == "BI_CAO"], [])
        self.assertEqual(awaiting(ctx.state), "ai")                    # paused on the same slot
        bad_question = seg([], ("BI_CAO", "Tôi xin trả lời."))
        ctx = at(_ctx("bi_cao", answers=[bad_question, bad_question]), "hdxx_hoi_bi_cao")
        with self.assertRaises(TrialGuardFailure):
            asyncio.run(run_ai_turn(ctx))

    def test_cap_reached_no_question_is_kept(self):
        ctx = at(_ctx("bi_cao", answers=[seg([("CHU_TOA", "Hội đồng xét xử đã hỏi xong bị cáo.")],
                                              ("CHU_TOA", "Bị cáo còn gì nữa không?"))]), "hdxx_hoi_bi_cao", turns=4)
        produced = asyncio.run(run_ai_turn(ctx))
        self.assertEqual([u.guard_flags for u in produced], [[]])
        self.assertNotIn("cau_hoi_cho_nguoi_hoc", ctx.recorder.prompts[0])
        self.assertIn("Đã hết câu hỏi dành cho {BI_CAO}", ctx.recorder.prompts[0])
        self.assertEqual(current_slot(ctx.state).key, "hdxx_hoi_nguoi_khac")

    def test_code_asks_when_the_model_skips_a_required_question(self):
        ctx = at(_ctx("bi_cao", answers=[seg([("CHU_TOA", "Hội đồng xét xử bắt đầu phần xét hỏi.")])]),
                 "hdxx_hoi_bi_cao")
        produced = asyncio.run(run_ai_turn(ctx))
        self.assertEqual((produced[-1].speaker_id, produced[-1].text),
                         ("CHU_TOA", FALLBACK_QUESTIONS["hdxx_hoi_bi_cao"][0]))
        self.assertEqual(produced[-1].guard_flags, ["question_fallback", STUDENT_QUESTION_FLAG])
        self.assertEqual(awaiting(ctx.state), "user")
        ctx = at(_ctx("bi_cao", answers=[seg([("KSV", "Viện kiểm sát không có câu hỏi.")])]), "ksv_hoi")
        asyncio.run(run_ai_turn(ctx))                                  # min 0: the KSV may ask nothing
        self.assertEqual(current_slot(ctx.state).key, "ls_hoi")

    def test_qa_loop_asks_others_in_the_same_call(self):
        ctx = at(_ctx("bi_cao", answers=[seg([("KSV", "Người làm chứng thấy gì?"), ("NLC_1", "Tôi thấy dắt xe.")],
                                              ("KSV", "Bị cáo dắt xe đi đâu?"))]), "ksv_hoi")
        produced = asyncio.run(run_ai_turn(ctx))
        self.assertEqual([u.speaker_id for u in produced], ["KSV", "NLC_1", "KSV"])
        out = state_out("00000000-0000-0000-0000-000000000000", ctx.state, case=ctx.case, transcript=ctx.transcript)
        self.assertEqual(out.allowed_actions, ["speak", "decline"])
        self.assertEqual(out.pending_question.decline_note.model_dump(), DECLINE_NOTE)
        self.assertIsNone(out.pending_question.prefill)

    def test_speaks_for_the_defendant_is_measured_not_blocked(self):
        ctx = _ctx("bi_cao")
        act_ctx = at(ctx, "hdxx_hoi_bi_cao")
        act_ctx.state = complete_ai_turn(act_ctx.state, asked_student=True)
        act(act_ctx, "speak", text="Tôi không nhớ rõ.")
        violations, flags = _check_utterance(ctx, "CHU_TOA", "Như bị cáo vừa khai, bị cáo đã thừa nhận hành vi.",
                                             ("CHU_TOA",))
        self.assertEqual((violations, flags), ([], ["speaks_for_student"]))
        _, flags = _check_utterance(ctx, "CHU_TOA", "Bị cáo có thừa nhận hành vi không?", ("CHU_TOA",))
        self.assertEqual(flags, [])                                    # a question is not a claim
        ctx.add("BI_CAO", "Dạ, tôi thừa nhận đã lấy chiếc xe.", is_user=True)
        _, flags = _check_utterance(ctx, "CHU_TOA", "Bị cáo đã thừa nhận hành vi.", ("CHU_TOA",))
        self.assertEqual(flags, [])                                    # the defendant did just admit
        ctx.add("BI_CAO", DECLINE_TEXT, is_user=True, kind="procedural")
        _, flags = _check_utterance(ctx, "CHU_TOA", "Bị cáo đã thừa nhận hành vi.", ("CHU_TOA",))
        self.assertEqual(flags, ["speaks_for_student"])                # a refusal admits nothing
        ctx.add("BI_CAO", "Tôi không thừa nhận, điều đó không đúng.", is_user=True)
        _, flags = _check_utterance(ctx, "CHU_TOA", "Bị cáo đã thừa nhận hành vi.", ("CHU_TOA",))
        self.assertEqual(flags, ["speaks_for_student"])                # a denial admits nothing

    def test_off_file_amount_is_flagged_and_never_enters_the_ledger(self):
        ctx = at(_ctx("bi_cao"), "hdxx_hoi_bi_cao")
        ctx.state = complete_ai_turn(ctx.state, asked_student=True)
        produced = act(ctx, "speak", text="Chiếc xe chỉ đáng 900.000.000 đồng thôi.")
        self.assertEqual(produced[0].guard_flags, ["user_amount_off_file"])
        ctx.recorder.answers = [seg([("CHU_TOA", "Theo hồ sơ, chiếc xe trị giá 12.500.000 đồng.")],
                                    ("CHU_TOA", "Bị cáo còn ý kiến gì không?"),
                                    facts=[{"about": "BI_CAO", "fact": "Bị cáo khai xe trị giá 900.000.000 đồng."}])]
        asyncio.run(run_ai_turn(ctx))
        self.assertEqual(ctx.fact_ledger, [])
        ksv = at(_ctx("ksv"), "luan_toi")
        self.assertEqual(act(ksv, "speak", text="Tài sản trị giá 900.000.000 đồng. " * 10)[0].guard_flags, [])

    def test_verdict_prompt_note_for_the_defendant_only(self):
        for role, expected in (("bi_cao", True), ("ksv", False), ("nguoi_xem", False)):
            ctx = at(_ctx(role, answers=[GOOD_VERDICT]), "nghi_an")
            asyncio.run(_deliberate(ctx))
            note = DEFENDANT_VERDICT_NOTE.replace("{{", "{").replace("}}", "}").strip()
            self.assertEqual(note in ctx.recorder.systems[0], expected, role)
        self.assertIn("điểm s khoản 1 Điều 51 Bộ luật Hình sự", DEFENDANT_VERDICT_NOTE)

    def test_role_card_is_the_defendants_own_only(self):
        case = valid_case_file()
        brief = role_brief(case)
        self.assertEqual(set(brief), {"stance", "knowledge", "demeanor", "note"})
        self.assertEqual(brief["stance"], case.draft.defendant.stance)
        dumped = json.dumps(brief, ensure_ascii=False)
        for other in ("yêu cầu bồi thường", "chứng kiến một phần", "nhan_", "guilty"):
            self.assertNotIn(other, dumped)
        self.assertNotIn("{", "".join([brief["stance"], brief["demeanor"], *brief["knowledge"]]))
        self.assertIn(case.participants["BI_CAO"].name, identity_prefill(case))
        self.assertIn("27 tuổi", identity_prefill(case))
        self.assertLessEqual(len(identity_prefill(case)), 1500)

    def test_decline_note_cites_the_checked_articles(self):
        self.assertEqual(DECLINE_NOTE["legal_basis"], ["điểm h khoản 2 Điều 61 Bộ luật Tố tụng hình sự",
                                                       "điểm b khoản 2 Điều 308 Bộ luật Tố tụng hình sự"])
        self.assertIn("không buộc phải đưa ra lời khai chống lại chính mình hoặc buộc phải nhận mình có tội",
                      DECLINE_NOTE["text"])
        self.assertFalse(DECLINE_NOTE["reviewed"])

    def test_other_roles_get_no_pending_question(self):
        for role in ("ksv", "nguoi_xem", "thu_ky"):
            ctx = _ctx(role)
            out = state_out("00000000-0000-0000-0000-000000000000", ctx.state, case=ctx.case,
                            transcript=ctx.transcript)
            self.assertIsNone(out.pending_question, role)


if __name__ == "__main__":
    unittest.main()
