"""Tests for chặng R2: the Thư ký role (design doc Mục 11.3, decisions 5-8 of 11.8). Fake model and
in-memory repository - no Gemini, no Supabase."""
from __future__ import annotations

import asyncio
import json
import unittest
from dataclasses import replace

from app.models.trial_api import TrialNotesRequest, TrialRecordDraftRequest
from app.services import trial_clerk
from app.services.trial_clerk import (
    CLERK_PROMPTS,
    clean_section,
    draft_of,
    review_section,
    with_draft,
    with_finalized,
    with_notes,
)
from app.services.trial_record import CLERK_AUTHOR_NOTE, DRAFT_NOTE, build_record, render_record_text
from app.services.trial_session_service import state_out
from app.services.trial_state_machine import (
    ENABLED_USER_ROLES,
    STEPS,
    CaseShape,
    TrialConflict,
    UserAction,
    active_slots,
    allowed_actions,
    apply_user_action,
    awaiting,
    complete_ai_turn,
    current_slot,
    is_user_slot,
    new_session,
    text_limits,
)
from app.services.trial_turn_service import (
    TrialContext,
    TrialGuardFailure,
    Utterance,
    _check_utterance,
    _system_prompt,
    apply_student_action,
    run_ai_turn,
)
from tests.test_trial_observer import _Recorder
from tests.trial_fixtures import pack_for, valid_case_file

SHAPE = CaseShape(victim_present=False, witness_count=1, has_related_party=False)
SID = "00000000-0000-0000-0000-000000000001"
REPORT = ("Thưa Hội đồng xét xử, tại phiên tòa hôm nay có mặt Kiểm sát viên, bị cáo, luật sư bào chữa và người làm "
          "chứng. Bị hại vắng mặt, có đơn đề nghị xét xử vắng mặt. Thư ký đã phổ biến nội quy phiên tòa.")


def _speak(state, text, **kw):
    return apply_user_action(state, UserAction("speak", state.current_step, state.version, text=text, **kw))


class ClerkStateMachineTests(unittest.TestCase):
    def test_step_one_is_the_clerks_report_only(self):
        self.assertIn("thu_ky", ENABLED_USER_ROLES)
        state = new_session("thu_ky", SHAPE)
        self.assertEqual((state.current_step, awaiting(state)), (1, "user"))
        self.assertEqual(current_slot(state).key, "bao_cao_co_mat")
        self.assertEqual(allowed_actions(state), ["speak"])
        self.assertEqual(text_limits(state), (100, 3000))
        after = _speak(state, REPORT).state
        self.assertEqual(allowed_actions(after), ["advance:2"])
        self.assertIsNone(text_limits(after))

    def test_every_later_slot_is_an_ai_slot_and_only_advance_is_allowed(self):
        for step in STEPS[1:]:
            for slot in active_slots(step.number, SHAPE, "thu_ky"):
                self.assertFalse(is_user_slot(slot, "thu_ky"), slot.key)
        state = _speak(new_session("thu_ky", SHAPE), REPORT).state
        waits = 0
        while state.status == "active":
            if awaiting(state) == "ai":
                state = complete_ai_turn(state)
                continue
            waits += 1
            self.assertEqual(allowed_actions(state), [f"advance:{state.current_step + 1}"])
            for kind in ("speak", "end_slot"):
                with self.assertRaises(TrialConflict) as caught:
                    apply_user_action(state, UserAction(kind, state.current_step, state.version, text="Xin phép."))
                self.assertEqual(caught.exception.code, "action_not_allowed")
            state = apply_user_action(state, UserAction("advance", state.current_step, state.version,
                                                        target_step=state.current_step + 1)).state
        self.assertEqual((state.status, waits), ("completed", 10))

    def test_report_errors(self):
        state = new_session("thu_ky", SHAPE)
        cases = {
            "text_too_short": UserAction("speak", 1, state.version, text="Báo cáo."),
            "empty_text": UserAction("speak", 1, state.version, text="   "),
            "version_mismatch": UserAction("speak", 1, state.version + 1, text=REPORT),
            "step_mismatch": UserAction("speak", 2, state.version, text=REPORT),
            "slot_not_finished": UserAction("end_slot", 1, state.version),
        }
        for code, action in cases.items():
            with self.assertRaises(TrialConflict) as caught:
                apply_user_action(state, action)
            self.assertEqual(caught.exception.code, code)
        for target in (2, 3):   # silent clerk: no advance before the report, no jump
            with self.assertRaises(TrialConflict) as caught:
                apply_user_action(state, UserAction("advance", 1, state.version, target_step=target))
            self.assertEqual(caught.exception.code, "slot_not_finished" if target == 2 else "skip_not_allowed")

    def test_other_roles_keep_the_template_report(self):
        for role in ("ksv", "luat_su", "nguoi_xem"):
            state = new_session(role, SHAPE)
            self.assertEqual(awaiting(state), "ai", role)
            self.assertFalse(is_user_slot(current_slot(state), role))
            self.assertEqual(complete_ai_turn(state).current_step, 1)


def _ctx(answers=None) -> TrialContext:
    return TrialContext(case=valid_case_file(), pack=pack_for("blhs_173"), state=new_session("thu_ky", SHAPE),
                        settings=None, recorder=_Recorder(answers=answers or []))


class ClerkTurnTests(unittest.TestCase):
    def test_report_is_stored_verbatim_as_the_clerks_words(self):
        ctx = _ctx()
        with self.assertRaises(TrialConflict) as caught:
            apply_student_action(ctx, UserAction("speak", 1, ctx.state.version, text=REPORT + "x" * 3000))
        self.assertEqual(caught.exception.code, "text_too_long")
        produced = apply_student_action(ctx, UserAction("speak", 1, ctx.state.version, text=REPORT))
        self.assertEqual([(u.speaker_id, u.is_user, u.text) for u in produced], [("THU_KY", True, REPORT)])

    def test_system_prompt_names_the_clerk(self):
        prompt = _system_prompt(_ctx())
        self.assertIn("Người học đang đóng vai Thư ký ({THU_KY})", prompt)
        self.assertIn("không tự nhận thay Thư ký — vai đó do người học đóng.", prompt)

    def test_ai_writing_as_the_clerk_is_blocked_structurally(self):
        bad = json.dumps({"utterances": [{"speaker_id": "THU_KY", "text": "Báo cáo Hội đồng xét xử."}],
                          "new_facts": []}, ensure_ascii=False)
        ctx = _ctx(answers=[bad, bad])
        apply_student_action(ctx, UserAction("speak", 1, ctx.state.version, text=REPORT))
        apply_student_action(ctx, UserAction("advance", 1, ctx.state.version, target_step=2))
        with self.assertRaises(TrialGuardFailure) as caught:
            asyncio.run(run_ai_turn(ctx))
        self.assertIn("speaker_is_student", caught.exception.violations)
        self.assertEqual(current_slot(ctx.state).key, "khai_mac")   # paused on the same slot

    def test_speaking_for_the_clerk_is_measured_only(self):
        ctx = _ctx()
        violations, flags = _check_utterance(ctx, "CHU_TOA", "Thư ký phiên tòa báo cáo: mọi người đều có mặt.",
                                             ("CHU_TOA",))
        self.assertEqual((violations, flags), ([], ["speaks_for_student"]))
        _, flags = _check_utterance(ctx, "CHU_TOA", "Thư ký đã báo cáo sự có mặt.", ("CHU_TOA",))
        self.assertEqual(flags, [])


class ClerkStateOutTests(unittest.TestCase):
    def test_prompt_every_step_and_report_only_while_due(self):
        case = valid_case_file()
        state = new_session("thu_ky", SHAPE)
        out = state_out(SID, state, case=case)
        self.assertEqual(out.clerk_prompt.model_dump(), {"step": 1, "text": CLERK_PROMPTS[1], "reviewed": False})
        self.assertIsNone(out.procedure_note)
        self.assertIn(case.participants["BI_CAO"].name, out.clerk_report.prefill)
        self.assertNotIn("{", out.clerk_report.prefill)
        attendance = {a.speaker_id: a.present for a in out.clerk_report.attendance}
        self.assertEqual(attendance, {"KSV": True, "BI_CAO": True, "LUAT_SU": True, "BI_HAI": False, "NLC_1": True})
        after = _speak(state, REPORT).state
        self.assertIsNone(state_out(SID, after, case=case).clerk_report)
        self.assertEqual(state_out(SID, replace(after, current_step=7), case=case).clerk_prompt.step, 7)
        for role in ("ksv", "luat_su", "nguoi_xem"):
            other = state_out(SID, new_session(role, SHAPE), case=case)
            self.assertIsNone(other.clerk_prompt)
            self.assertIsNone(other.clerk_report)


def _transcript() -> list[Utterance]:
    return [
        Utterance(1, 1, "THU_KY", True, "speech", REPORT),
        Utterance(2, 4, "CHU_TOA", False, "speech", "{BI_CAO} khai đã lấy chiếc xe trị giá 12.500.000 đồng."),
        Utterance(3, 5, "KSV", False, "speech", "Bị cáo đã bồi thường 2.000.000 đồng phải không?"),
        Utterance(4, 6, "KSV", False, "speech", "Đề nghị áp dụng khoản 1 Điều 173 Bộ luật Hình sự, giảm 10%."),
        Utterance(5, 7, "CHU_TOA", False, "notice", "Theo Điều 51 Bộ luật Hình sự 9.000.000 đồng."),
    ]


IV2_OK = ("Chủ tọa hỏi bị cáo Trần Minh Tâm về diễn biến vụ án; bị cáo khai đã lấy chiếc xe trị giá 12.500.000 đồng. "
          "Kiểm sát viên hỏi về việc bồi thường; bị cáo xác nhận đã bồi thường 2.000.000 đồng cho bị hại. "
          "Luật sư hỏi về hoàn cảnh gia đình của bị cáo.")


class ClerkReviewTests(unittest.TestCase):
    def setUp(self):
        self.case = valid_case_file()

    def codes(self, key, text):
        return [n.code for n in review_section(self.case, _transcript(), key, text)]

    def test_clean_section_gives_no_notice(self):
        self.assertEqual(self.codes("iv2", IV2_OK), [])

    def test_each_check(self):
        self.assertEqual(self.codes("iv2", ""), ["empty"])
        self.assertEqual(self.codes("iv2", "Bị cáo khai nhận."), ["too_short"])
        self.assertEqual(self.codes("iv2", IV2_OK * 30), ["too_long"])
        # Amount said only in another section (step 6/notice), percent never said in IV.2.
        self.assertEqual(self.codes("iv2", IV2_OK + " Mức giảm 10%, thiệt hại 9.000.000 đồng."),
                         ["unknown_amount", "unknown_percent"])
        self.assertEqual(self.codes("iv3", IV2_OK.replace("12.500.000 đồng", "khoản 1 Điều 173 Bộ luật Hình sự")
                                    + " Giảm 10%."), ["unknown_amount"])
        self.assertEqual(self.codes("iv3", "Kiểm sát viên đề nghị áp dụng khoản 1 Điều 173. " * 6),
                         ["citation_missing_law"])
        self.assertEqual(self.codes("iv3", "Kiểm sát viên đề nghị áp dụng Điều 51 Bộ luật Hình sự. " * 5),
                         ["citation_not_in_section"])
        self.assertEqual(self.codes("iv2", IV2_OK + " Ông Phạm Quang Huy có mặt."), ["unknown_name"])

    def test_messages_name_the_section_and_value(self):
        notice = review_section(self.case, _transcript(), "iv2", IV2_OK + " Thiệt hại 5.000.000 đồng.")[0]
        self.assertEqual(notice.message, "Mục 2 nêu 5.000.000 đồng; con số này không xuất hiện trong phần hỏi và trả lời.")

    def test_markdown_is_cleaned_words_kept(self):
        text = "## Tóm tắt\r\n**Bị cáo** khai `nhận`.\n\n\n\n* ý một\n+ ý hai   \n\x07"
        self.assertEqual(clean_section(text), "Tóm tắt\nBị cáo khai nhận.\n\n- ý một\n- ý hai")

    def test_user_work_round_trip(self):
        from datetime import datetime, timezone
        now = datetime(2026, 10, 29, tzinfo=timezone.utc)
        work = with_notes(None, "ghi chú", now)
        work = with_draft(work, {"iv2": "**IV2**", "iv3": None}, now)
        self.assertEqual((work["notes"], draft_of(work).iv2, draft_of(work).iv3), ("ghi chú", "IV2", ""))
        work = with_draft(work, {"iv2": None, "iv3": "IV3"}, now)
        self.assertEqual(draft_of(work).sections(), {"iv2": "IV2", "iv3": "IV3"})
        self.assertFalse(draft_of(work).finalized)
        work = with_finalized(work, now)
        self.assertTrue(draft_of(work).finalized)
        self.assertEqual(work["notes"], "ghi chú")

    def test_request_bounds_match_the_service(self):
        self.assertEqual(TrialNotesRequest.model_fields["text"].metadata[0].max_length, trial_clerk.NOTES_MAX_CHARS)
        for key in ("iv2", "iv3"):
            self.assertEqual(TrialRecordDraftRequest.model_fields[key].metadata[0].max_length,
                             trial_clerk.SECTION_HARD_MAX_CHARS)

    def test_record_shows_the_clerks_sections(self):
        record = build_record(self.case, _transcript(), None, None, clerk={"iv2": IV2_OK, "iv3": ""}, draft=True)
        items = record.sections[3].subsections
        self.assertEqual([i.content for i in items], ["verbatim", "user", "user", "verbatim"])
        self.assertEqual((items[1].summary, items[2].summary), (IV2_OK, None))
        self.assertEqual(items[1].author_note, CLERK_AUTHOR_NOTE)
        self.assertEqual((record.draft, record.preamble), (True, [DRAFT_NOTE]))
        text = render_record_text(record)
        self.assertIn(DRAFT_NOTE, text)
        self.assertIn(f"({CLERK_AUTHOR_NOTE})", text)
        final = build_record(self.case, _transcript(), None, None, clerk={"iv2": IV2_OK, "iv3": IV2_OK})
        self.assertEqual((final.draft, final.preamble), (False, []))


if __name__ == "__main__":
    unittest.main()
