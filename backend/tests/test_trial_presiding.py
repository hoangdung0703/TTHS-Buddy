"""Unit tests for the Chủ tọa role (chặng R4): the presiding rules of trial_presiding on the state
machine alone, the templates, the stored form of PresideState, the measure-only usurps_presiding
pattern, the prompts, and that no AI nghị án can run in this role. No Gemini call."""
from __future__ import annotations

import asyncio
import json
import re
import unittest
from dataclasses import replace

from app.models.trial import ChairDecision
from app.prompts.trial_prompts import PRESIDING_ROLE_RULES
from app.services import trial_presiding
from app.services.trial_presiding import (
    STEP_ITEMS,
    code_answers,
    preside_from_dict,
    preside_to_dict,
    template_placeholders,
    usurps_presiding,
)
from app.services.trial_state_machine import (
    PRESIDE_SLOT,
    CaseShape,
    PresideJob,
    TrialConflict,
    UserAction,
    active_slots,
    allowed_actions,
    apply_user_action,
    awaiting,
    complete_ai_turn,
    current_slot,
    new_session,
)
from app.services.trial_turn_service import (
    _check_utterance,
    _deliberate,
    _own_durations,
    _system_prompt,
    apply_student_action,
    run_ai_turn,
)
from tests.test_trial_observer import _ctx
from tests.trial_fixtures import valid_case_file

SHAPE = CaseShape(victim_present=True, witness_count=1, has_related_party=False)
ABSENT = CaseShape(victim_present=False, witness_count=0, has_related_party=False)
BLTTHS_STEP_RANGE = {str(n) for n in range(300, 330)}


def act(state, kind, **kw):
    return apply_user_action(state, UserAction(kind, state.current_step, state.version, **kw)).state


def at_step(step: int, shape: CaseShape = SHAPE, **preside):
    state = new_session("chu_toa", shape)
    state = replace(state, current_step=step, pending_ai=False)
    return replace(state, preside=replace(state.preside, **preside))


def finish(state, **preside):
    """All required items of the step done."""
    keys = [i.key for i in trial_presiding.items_for(state) if i.required]
    return replace(state, preside=replace(state.preside, done=tuple(keys), **preside))


class PresidingStateTests(unittest.TestCase):
    def test_step_1_is_the_clerk_template_then_one_preside_slot_per_step(self):
        state = new_session("chu_toa", SHAPE)
        self.assertEqual((state.current_step, awaiting(state)), (1, "ai"))
        self.assertEqual(current_slot(state).key, "bao_cao_co_mat")
        state = complete_ai_turn(state)
        self.assertEqual(allowed_actions(state), ["advance:2"])
        state = act(state, "advance", target_step=2)
        self.assertEqual((current_slot(state), awaiting(state)), (PRESIDE_SLOT, "user"))
        for step in range(2, 12):
            self.assertEqual(active_slots(step, SHAPE, "chu_toa"), (PRESIDE_SLOT,))
        for role in ("ksv", "luat_su", "nguoi_xem", "thu_ky", "bi_cao"):   # unchanged for every other role
            self.assertNotIn(PRESIDE_SLOT, [s for n in range(1, 12) for s in active_slots(n, SHAPE, role)])
            self.assertIsNone(new_session(role, SHAPE).preside)

    def test_catalogue_follows_the_case_shape(self):
        keys = lambda state: [i.key for i in trial_presiding.items_for(state)]   # noqa: E731
        self.assertIn("cam_doan_nlc", keys(at_step(2)))
        self.assertNotIn("cam_doan_nlc", keys(at_step(2, ABSENT)))
        self.assertIn("cong_bo_loi_khai_bi_hai", keys(at_step(4, ABSENT)))
        self.assertNotIn("cong_bo_loi_khai_bi_hai", keys(at_step(4)))
        self.assertIn("moi_bi_hai_trinh_bay", keys(at_step(7)))
        self.assertNotIn("moi_bi_hai_trinh_bay", keys(at_step(7, ABSENT)))
        self.assertNotIn("hoi_nguoi_khac", keys(at_step(4, ABSENT)))     # nobody else present to question
        self.assertFalse(next(i for i in STEP_ITEMS[2] if i.key == "hoi_yeu_cau").required)   # decision Q6

    def test_every_basis_is_a_bltths_article_of_the_hearing(self):
        for items in (*STEP_ITEMS.values(), trial_presiding.RETURN_ITEMS):
            for item in items:
                self.assertTrue(set(item.basis) <= BLTTHS_STEP_RANGE, item.key)

    def test_procedure_incomplete_lists_missing_items(self):
        state = at_step(5)
        with self.assertRaises(TrialConflict) as caught:
            act(state, "advance", target_step=6)
        self.assertEqual(caught.exception.code, "procedure_incomplete")
        self.assertEqual(caught.exception.detail, {"missing_items": ["moi_ksv_hoi", "moi_ls_hoi", "ket_thuc_xet_hoi"]})
        self.assertNotIn("item:ket_thuc_xet_hoi", allowed_actions(state))   # last: only once the others are done
        state = act(state, "invite", item="moi_ksv_hoi")
        self.assertEqual((awaiting(state), state.preside.job), ("ai", PresideJob("invite", "moi_ksv_hoi")))
        state = complete_ai_turn(state)
        state = complete_ai_turn(act(state, "invite", item="moi_ls_hoi"))
        self.assertIn("item:ket_thuc_xet_hoi", allowed_actions(state))
        state = act(state, "item", item="ket_thuc_xet_hoi")
        self.assertEqual(allowed_actions(state)[-1], "advance:6")
        moved = act(state, "advance", target_step=6)
        self.assertEqual((moved.current_step, moved.preside.done), (6, ()))

    def test_a_debate_round_is_two_speeches(self):
        state = act(at_step(8), "invite", item="moi_doi_dap")
        state = complete_ai_turn(state)
        self.assertEqual((awaiting(state), state.preside.job.progress, state.preside.rounds), ("ai", 1, 0))
        state = complete_ai_turn(state)
        self.assertEqual((awaiting(state), state.preside.job, state.preside.rounds), ("user", None, 1))
        self.assertIn("return_to_questioning", allowed_actions(state))
        self.assertIn("invite:vong_2", allowed_actions(state))

    def test_return_to_questioning_only_from_step_8_and_once(self):
        for step in (5, 6, 7):
            with self.assertRaises(TrialConflict) as caught:
                act(at_step(step, rounds=1, done=("moi_doi_dap",)), "return_to_questioning")
            self.assertEqual(caught.exception.code, "return_not_allowed")
        state = at_step(8, rounds=1, done=("moi_doi_dap",))
        state = act(state, "return_to_questioning")
        self.assertEqual((state.current_step, state.preside.returned, state.preside.in_return), (5, True, True))
        state = finish(state)
        self.assertEqual(allowed_actions(state)[-1], "advance:8")
        state = act(state, "advance", target_step=8)
        self.assertFalse(state.preside.in_return)
        state = replace(state, preside=replace(state.preside, rounds=1, done=("moi_doi_dap",)))
        with self.assertRaises(TrialConflict) as caught:
            act(state, "return_to_questioning")
        self.assertEqual(caught.exception.code, "return_used")

    def test_decide_and_pronounce_sequence(self):
        state = at_step(10)
        self.assertEqual(allowed_actions(state), ["item:vao_nghi_an"])
        state = act(state, "item", item="vao_nghi_an")
        self.assertEqual(allowed_actions(state), ["invite:y_kien_hoi_tham", "decide"])
        state = act(state, "decide")
        self.assertTrue(state.preside.decided)
        self.assertEqual(allowed_actions(state), ["advance:11"])
        state = act(state, "advance", target_step=11)
        self.assertEqual(allowed_actions(state), ["prepare_pronouncement"])
        with self.assertRaises(TrialConflict) as caught:
            act(state, "pronounce")
        self.assertEqual(caught.exception.code, "pronouncement_missing")
        state = complete_ai_turn(act(state, "prepare_pronouncement"))
        self.assertEqual(allowed_actions(state), ["pronounce"])
        state = act(state, "pronounce")
        self.assertEqual((state.status, awaiting(state)), ("completed", "none"))

    def test_other_actions_are_refused(self):
        state = at_step(4)
        for kind in ("speak", "end_slot", "decline", "decide", "pronounce"):
            with self.assertRaises(TrialConflict):
                act(state, kind, text="x")
        with self.assertRaises(TrialConflict) as caught:
            act(state, "ask", addressee="KSV", text="Hỏi?")
        self.assertEqual(caught.exception.code, "missing_addressee")

    def test_stored_form_round_trips(self):
        preside = replace(at_step(8).preside, done=("moi_doi_dap",), rounds=1, returned=True,
                          job=PresideJob("invite", "vong_2", None, 1))
        data = json.loads(json.dumps(preside_to_dict(preside)))
        self.assertEqual(preside_from_dict(data), preside)
        self.assertEqual(preside_from_dict(None), at_step(2).preside)


class TemplateTests(unittest.TestCase):
    def test_every_item_template_renders_with_known_people_only(self):
        case = valid_case_file()
        for items in STEP_ITEMS.values():
            for item in items:
                text = template_placeholders(item.key, case, SHAPE)
                if text is None:
                    continue
                self.assertFalse(set(re.findall(r"\{([A-Z_0-9]+)\}", text)) - set(case.participants), item.key)
                self.assertNotIn("{", trial_presiding.template_text(item.key, case, SHAPE), item.key)

    def test_templates_cite_only_the_articles_they_follow(self):
        case = valid_case_file()
        self.assertIn("khoản 1 Điều 173 Bộ luật Hình sự", template_placeholders("khai_mac", case, SHAPE))
        self.assertIn("Điều 302", template_placeholders("hoi_thay_doi", case, SHAPE))
        self.assertIn("điểm d khoản 2 Điều 308", template_placeholders("cong_bo_loi_khai_bi_hai", case, ABSENT))
        self.assertIn("hoãn phiên tòa", template_placeholders("hoi_yeu_cau", case, ABSENT))
        self.assertNotIn("hoãn phiên tòa", template_placeholders("hoi_yeu_cau", case, SHAPE))
        rights = template_placeholders("giai_thich_quyen", case, SHAPE)
        for article in ("Điều 61", "Điều 62", "Điều 66"):
            self.assertIn(article, rights)
        self.assertNotIn("Điều 62", template_placeholders("giai_thich_quyen", case, ABSENT))

    def test_code_answers(self):
        self.assertEqual([s for s, _ in code_answers("hoi_thay_doi", SHAPE, own_identity_question=False)],
                         ["KSV", "LUAT_SU", "BI_CAO"])
        self.assertEqual(code_answers("kiem_tra_can_cuoc", SHAPE, own_identity_question=True), [])
        self.assertEqual(code_answers("moi_luan_toi", SHAPE, own_identity_question=False), [])
        self.assertFalse(trial_presiding.TEMPLATES_REVIEWED)                  # decision Q13: drafts


class GuardTests(unittest.TestCase):
    def test_usurps_presiding_pattern(self):
        for text in ("Hội đồng xét xử tuyên bố kết thúc phần xét hỏi.", "Bây giờ chuyển sang phần tranh luận.",
                     "Hội đồng xét xử đã chấp nhận đề nghị của tôi.", "Chủ tọa đã đồng ý cho bị cáo nói.",
                     "Mời Kiểm sát viên trình bày luận tội.", "Hội đồng xét xử quyết định cách ly người làm chứng."):
            self.assertTrue(usurps_presiding(text), text)
        for text in ("Đề nghị Hội đồng xét xử chấp nhận yêu cầu bồi thường.", "Xin chuyển sang phần tranh luận.",
                     "Kính đề nghị Hội đồng xét xử cho phép bị cáo được hưởng án treo.",
                     "Bị cáo có ý kiến gì về bản cáo trạng không?", "Tôi xin hết."):
            self.assertFalse(usurps_presiding(text), text)

    def test_usurps_flag_is_measured_only_and_for_this_role_only(self):
        line = "Hội đồng xét xử tuyên bố kết thúc phần xét hỏi."
        violations, flags = _check_utterance(_ctx("chu_toa"), "HOI_THAM_1", line, ("HOI_THAM_1",))
        self.assertIn("usurps_presiding", flags)
        self.assertNotIn("usurps_presiding", violations)
        self.assertNotIn("usurps_presiding", _check_utterance(_ctx("ksv"), "CHU_TOA", line, ("CHU_TOA",))[1])

    def test_chu_toa_never_an_ai_speaker(self):
        violations, _ = _check_utterance(_ctx("chu_toa"), "CHU_TOA", "Tôi tuyên bố.", ("CHU_TOA",))
        self.assertIn("speaker_is_student", violations)

    def test_assessor_durations(self):
        draft = ChairDecision.model_validate({
            "guilty": True, "dieu": "173", "khoan": "1", "diem": [], "penalty_type": "tu", "penalty_months": 12,
            "suspended": True, "probation_months": 24, "applies_dieu_54": False, "mitigating": [], "aggravating": [],
            "reasoning_summary": "x"})
        self.assertFalse(_own_durations("Đồng ý mức 12 tháng tù, thử thách 2 năm.", draft))
        self.assertFalse(_own_durations("Phiên tòa ngày 19 tháng 10 năm 2026.", draft))
        self.assertTrue(_own_durations("Nên xử 18 tháng tù.", draft))
        self.assertTrue(_own_durations("Nên xử 3 năm tù.", draft))

    def test_system_prompt_has_the_presiding_rules_for_this_role_only(self):
        self.assertIn(PRESIDING_ROLE_RULES, _system_prompt(_ctx("chu_toa")))
        for role in ("ksv", "bi_cao", "nguoi_xem"):
            self.assertNotIn(PRESIDING_ROLE_RULES, _system_prompt(_ctx(role)))

    def test_no_ai_deliberation_in_this_role(self):
        ctx = _ctx("chu_toa")
        with self.assertRaises(RuntimeError):
            asyncio.run(_deliberate(ctx))
        self.assertEqual(ctx.recorder.records, [])


class TurnTests(unittest.TestCase):
    def test_answer_job_uses_only_the_addressee(self):
        ctx = _ctx("chu_toa", answers=[json.dumps({"utterances": [{"speaker_id": "BI_HAI", "text": "Dạ, đúng ạ."}],
                                                   "new_facts": []})])
        ctx.state = at_step(4)
        apply_student_action(ctx, UserAction("ask", 4, ctx.state.version, text="Bị hại xác nhận?", addressee="BI_HAI"))
        produced = asyncio.run(run_ai_turn(ctx))
        self.assertEqual([u.speaker_id for u in produced], ["BI_HAI"])
        self.assertEqual(awaiting(ctx.state), "user")
        self.assertIn("Một người nói duy nhất: {BI_HAI}", ctx.recorder.prompts[0])

    def test_indictment_invitation_is_read_by_code(self):
        ctx = _ctx("chu_toa")
        ctx.state = at_step(3)
        produced = apply_student_action(ctx, UserAction("invite", 3, ctx.state.version, item="moi_cong_bo_cao_trang"))
        self.assertEqual([(u.speaker_id, u.is_user) for u in produced], [("CHU_TOA", True), ("KSV", False)])
        self.assertEqual(produced[1].text, ctx.case.draft.indictment_text)
        self.assertEqual(ctx.recorder.records, [])
        self.assertEqual(awaiting(ctx.state), "user")


if __name__ == "__main__":
    unittest.main()
