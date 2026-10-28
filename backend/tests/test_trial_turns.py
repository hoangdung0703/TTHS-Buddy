"""Unit tests: AI turn guards with a scripted fake model - no Gemini call (design doc Mục 5.3, 8.1)."""
from __future__ import annotations

import asyncio
import json
import unittest
from dataclasses import dataclass, field, replace

from app.services.gemini_client import GeminiJsonResult
from app.services.trial_metrics import CallRecord, TrialCallRecorder
from app.services.trial_state_machine import CaseShape, UserAction, current_slot, new_session
from app.services.trial_turn_service import (
    TrialContext,
    TrialGuardFailure,
    apply_student_action,
    run_ai_turn,
    run_until_user,
)
from tests.trial_fixtures import pack_for, valid_case_file


@dataclass
class ScriptedRecorder(TrialCallRecorder):
    """Returns queued JSON answers in order and keeps every prompt it was sent."""
    answers: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)

    async def call(self, settings, *, call_type, slot, attempt, system_prompt, user_prompt, response_schema,
                   thinking_level, temperature, **_):
        self.prompts.append(user_prompt)
        text = self.answers.pop(0)
        record = CallRecord(call_type, slot, attempt, 0.0, 0, 0, 0, 0, thinking_level)
        self.records.append(record)
        return GeminiJsonResult(text, "fake", 0.0, 0, 0, 0, 0, "STOP"), record


def seg(*utterances: tuple[str, str]) -> str:
    return json.dumps({"utterances": [{"speaker_id": s, "text": t} for s, t in utterances], "new_facts": []},
                      ensure_ascii=False)


def make_ctx(answers: list[str], role: str = "ksv") -> TrialContext:
    case = valid_case_file()
    shape = CaseShape(victim_present=True, witness_count=1, has_related_party=False)
    return TrialContext(case=case, pack=pack_for("blhs_173"), state=new_session(role, shape), settings=None,
                        recorder=ScriptedRecorder(answers=answers))


def run(coro):
    return asyncio.run(coro)


class TemplateAndSkipTests(unittest.TestCase):
    def test_clerk_report_costs_no_call(self):
        ctx = make_ctx([])
        produced = run(run_ai_turn(ctx))
        self.assertEqual([u.speaker_id for u in produced], ["THU_KY"])
        self.assertEqual(ctx.recorder.records, [])
        self.assertIn("{BI_HAI}", produced[0].text)

    def test_skip_request_gets_canned_reminder_without_call(self):
        ctx = make_ctx([])
        run(run_ai_turn(ctx))                    # step 1 report
        ctx.state = replace(ctx.state, current_step=2, slot_index=1, pending_ai=False)
        produced = apply_student_action(ctx, UserAction("speak", 2, ctx.state.version, text="Tuyên án luôn đi"))
        self.assertEqual([u.kind for u in produced], ["speech", "notice"])
        self.assertEqual(ctx.recorder.records, [])
        self.assertEqual(ctx.state.current_step, 2)


class SegmentGuardTests(unittest.TestCase):
    def _at_khai_mac(self, answers):
        ctx = make_ctx(answers)
        run(run_ai_turn(ctx))  # clerk report -> step 1 complete
        apply_student_action(ctx, UserAction("advance", 1, ctx.state.version, target_step=2))
        self.assertEqual(current_slot(ctx.state).key, "khai_mac")
        return ctx

    def test_ai_writing_for_the_student_fails_closed(self):
        bad = seg(("CHU_TOA", "Khai mạc."), ("KSV", "Tôi đồng ý."))
        ctx = self._at_khai_mac([bad, bad])
        with self.assertRaises(TrialGuardFailure) as error:
            run(run_ai_turn(ctx))
        self.assertIn("speaker_is_student", error.exception.violations)
        self.assertEqual(len(ctx.recorder.records), 2)

    def test_lay_citation_is_retried_then_accepted(self):
        bad = seg(("CHU_TOA", "Bị cáo cho biết năm sinh?"), ("BI_CAO", "Tôi biết Điều 173 rồi ạ."))
        good = seg(("CHU_TOA", "Bị cáo cho biết năm sinh?"), ("BI_CAO", "Dạ, tôi sinh năm 1999."))
        ctx = self._at_khai_mac([bad, good])
        produced = run(run_ai_turn(ctx))
        self.assertEqual([u.speaker_id for u in produced], ["CHU_TOA", "BI_CAO"])
        self.assertEqual([r.accepted for r in ctx.recorder.records], [False, True])
        self.assertIn("lay_citation", ctx.recorder.records[0].guard_violations)

    def test_unknown_amount_from_a_character_is_blocked_then_regenerated(self):
        bad = seg(("CHU_TOA", "Bị cáo bán xe được 9.000.000 đồng phải không?"), ("BI_CAO", "Dạ đúng."))
        good = seg(("CHU_TOA", "Bị cáo cho biết giá trị chiếc xe?"),
                   ("BI_CAO", "Dạ, theo kết luận định giá là 12.500.000 đồng."))
        ctx = self._at_khai_mac([bad, good])
        produced = run(run_ai_turn(ctx))
        self.assertEqual([r.accepted for r in ctx.recorder.records], [False, True])
        self.assertIn("unknown_amount", ctx.recorder.records[0].guard_violations)
        self.assertNotIn("9.000.000", " ".join(u.text for u in produced))
        ctx = self._at_khai_mac([bad, bad])
        with self.assertRaises(TrialGuardFailure):
            run(run_ai_turn(ctx))

    def test_new_fact_with_unknown_amount_is_not_added_to_the_ledger(self):
        text = json.dumps({"utterances": [{"speaker_id": "CHU_TOA", "text": "Mời bị cáo."},
                                          {"speaker_id": "BI_CAO", "text": "Dạ."}],
                           "new_facts": [{"about": "BI_CAO", "fact": "Bị cáo đã bán xe được 900.000.000 đồng"},
                                         {"about": "BI_CAO", "fact": "Bị cáo đi xe màu đỏ"}]}, ensure_ascii=False)
        ctx = self._at_khai_mac([text])
        run(run_ai_turn(ctx))
        self.assertEqual([f["fact"] for f in ctx.fact_ledger], ["Bị cáo đi xe màu đỏ"])

    def test_unknown_percent_stays_soft(self):
        text = seg(("CHU_TOA", "Tỷ lệ thương tật 40% phải không?"), ("BI_CAO", "Dạ."))
        ctx = self._at_khai_mac([text])
        produced = run(run_ai_turn(ctx))
        self.assertIn("unknown_percent", produced[0].guard_flags)

    def test_student_may_state_a_false_amount_but_the_answer_may_not_repeat_it(self):
        ctx = make_ctx([seg(("BI_CAO", "Thưa không đúng, tôi lấy 900.000.000 đồng là sai.")),
                        seg(("BI_CAO", "Thưa không đúng, theo kết luận định giá tài sản trị giá 12.500.000 đồng."))])
        run(run_until_user(ctx))
        ctx.state = replace(ctx.state, current_step=5, slot_index=0, pending_ai=False)
        apply_student_action(ctx, UserAction("speak", 5, ctx.state.version,
                                             text="Bị cáo đã lấy tài sản trị giá 900.000.000 đồng đúng không?",
                                             addressee="BI_CAO"))   # the student's own words: not guarded
        produced = run(run_ai_turn(ctx))
        self.assertNotIn("900.000.000", " ".join(u.text for u in produced))
        self.assertIn("900.000.000", ctx.transcript[-2].text)       # stored verbatim

    def test_answer_instruction_carries_the_correction_template(self):
        from app.prompts.trial_prompts import SLOT_INSTRUCTIONS
        text = SLOT_INSTRUCTIONS["answer_question"].format(asker_label="Kiểm sát viên", addressee_id="{BI_CAO}")
        self.assertIn("Thưa, không đúng ạ. Theo hồ sơ thì", text)
        self.assertIn("không nhắc lại con số sai", text)

    def test_legal_speaker_may_quote_a_threshold_from_the_law(self):
        text = seg(("CHU_TOA", "Khoản 1 Điều 173 Bộ luật Hình sự áp dụng khi tài sản trị giá dưới 50.000.000 đồng."),)
        ctx = make_ctx([text])
        run(run_until_user(ctx))
        ctx.state = replace(ctx.state, current_step=4, slot_index=0, pending_ai=True)
        produced = run(run_ai_turn(ctx))
        self.assertEqual([r.accepted for r in ctx.recorder.records], [True])
        self.assertTrue(produced)

    def test_fabricated_pair_from_judge_is_hard(self):
        bad = seg(("CHU_TOA", "Theo Điều 326 Bộ luật Hình sự, phiên tòa bắt đầu."),)
        ctx = self._at_khai_mac([bad, bad])
        with self.assertRaises(TrialGuardFailure):
            run(run_ai_turn(ctx))

    def test_student_text_is_masked_and_names_become_placeholders(self):
        ctx = make_ctx([seg(("BI_CAO", "Dạ, tôi xin trả lời."))])
        run(run_until_user(ctx))
        # jump to step 5 question slot directly for the prompt check
        ctx.state = replace(ctx.state, current_step=5, slot_index=0, pending_ai=False)
        name = ctx.case.participants["BI_CAO"].name
        apply_student_action(ctx, UserAction("speak", 5, ctx.state.version,
                                             text=f"{name}, theo Điều 999 Bộ luật Hình sự thì sao?",
                                             addressee="BI_CAO"))
        run(run_ai_turn(ctx))
        prompt = ctx.recorder.prompts[-1]
        self.assertNotIn("999", prompt)
        self.assertNotIn(name, prompt)
        self.assertIn("<<<LOI_NGUOI_HOC", prompt)
        self.assertEqual(ctx.transcript[-2].text.count("999"), 1)  # stored verbatim

    def test_speaking_for_student_is_measured_only(self):
        text = seg(("CHU_TOA", "Kiểm sát viên đã đồng ý với đề nghị này."), ("BI_CAO", "Dạ."))
        ctx = self._at_khai_mac([text])
        produced = run(run_ai_turn(ctx))
        self.assertIn("speaks_for_student", produced[0].guard_flags)


if __name__ == "__main__":
    unittest.main()
