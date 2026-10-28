"""Unit tests for the biên bản summaries (chặng 3E): code guards, one regeneration, verbatim
fallback, errors and timeouts. Scripted fake model - no Gemini call."""
from __future__ import annotations

import asyncio
import json
import unittest
from unittest import mock

from app.services import trial_record_summary
from app.services.trial_record import build_record
from app.services.trial_record_summary import check_summary, section_sources, summarise_record
from app.services.trial_turn_service import Utterance
from tests.test_trial_turns import ScriptedRecorder, make_ctx

QUESTION = "Bị cáo trình bày lại diễn biến tối hôm đó, ai có mặt và bị cáo đã làm gì với chiếc xe? "
ANSWER = "Dạ, tôi dắt chiếc xe máy trị giá 12.500.000 đồng đi, hôm sau tôi mang trả lại và xin lỗi bị hại. "
CHARGE = ("Căn cứ khoản 1 Điều 173 Bộ luật Hình sự, Viện kiểm sát đề nghị xử phạt bị cáo từ 9 đến 12 tháng tù; "
          "bị cáo có tình tiết giảm nhẹ là đã bồi thường và thành khẩn khai báo. ")
GOOD_IV2 = "Chủ tọa hỏi {BI_CAO} về diễn biến; {BI_CAO} khai đã dắt chiếc xe trị giá 12.500.000 đồng rồi trả lại."
GOOD_IV3 = ("Kiểm sát viên {KSV} luận tội theo khoản 1 Điều 173 Bộ luật Hình sự, đề nghị xử phạt bị cáo từ 9 đến 12 "
            "tháng tù.")


def ctx_with_hearing(answers: list[str] | None = None, recorder=None):
    ctx = make_ctx(answers or [])
    if recorder is not None:
        ctx.recorder = recorder
    rows = [(4, "CHU_TOA", False, QUESTION * 3), (4, "BI_CAO", False, ANSWER * 3),
            (5, "KSV", True, QUESTION * 2), (5, "CHU_TOA", False, "Đề nghị trật tự."),
            (6, "KSV", False, CHARGE * 6), (7, "LUAT_SU", True, "Đề nghị Hội đồng xét xử xem xét giảm nhẹ. " * 8),
            (9, "BI_CAO", False, "Xin Hội đồng xét xử khoan hồng.")]
    for i, (step, speaker, user, text) in enumerate(rows, 1):
        ctx.transcript.append(Utterance(i, step, speaker, user, "speech", text, [], None))
    ctx.transcript.append(Utterance(len(rows) + 1, 5, "CHU_TOA", False, "notice", "Nhắc trật tự 999.", [], None))
    return ctx


def summary(iv2: str = GOOD_IV2, iv3: str = GOOD_IV3) -> str:
    return json.dumps({"iv2": iv2, "iv3": iv3}, ensure_ascii=False)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.ctx = ctx_with_hearing()
        self.sources = section_sources(self.ctx)
        self.all = "\n".join(self.sources.values())

    def check(self, text: str, key: str = "iv3") -> list[str]:
        return check_summary(self.ctx, text, self.sources[key], self.all)

    def test_good_summaries_pass(self):
        self.assertEqual(self.check(GOOD_IV2, "iv2"), [])
        self.assertEqual(self.check(GOOD_IV3), [])

    def test_notice_is_not_a_source(self):
        self.assertNotIn("999", self.all)
        self.assertIn("unknown_number", self.check("{KSV} nêu con số 999."))

    def test_unknown_amount_or_date(self):
        self.assertEqual(set(self.check("{BI_CAO} khai chiếc xe trị giá 13.000.000 đồng.", "iv2")),
                         {"unknown_number", "unknown_amount"})
        self.assertIn("unknown_number", self.check("Ngày 17/04/2031 {KSV} luận tội."))

    def test_unknown_article(self):
        self.assertIn("citation_not_in_source", self.check("{KSV} viện dẫn Điều 52 Bộ luật Hình sự."))
        labels = self.check("{KSV} viện dẫn Điều 999 Bộ luật Hình sự.")
        self.assertIn("citation_not_in_source", labels)
        self.assertTrue(any(v.startswith("citation:") for v in labels))

    def test_unknown_person(self):
        self.assertIn("invented_name", self.check("Nguyễn Văn Bình phát biểu ý kiến."))
        self.assertIn("unknown_placeholder", self.check("{NLC_9} phát biểu ý kiến."))

    def test_markdown_and_length(self):
        self.assertIn("markdown", self.check("**Kiểm sát viên** {KSV} luận tội."))
        self.assertIn("too_long", self.check(GOOD_IV3 + " " + "Kiểm sát viên phân tích thêm. " * 200))
        self.assertIn("empty", self.check("  "))


class GenerationTests(unittest.TestCase):
    def test_failed_section_regenerated_once_then_accepted(self):
        bad_iv2 = "{BI_CAO} khai chiếc xe trị giá 13.000.000 đồng."
        ctx = ctx_with_hearing([summary(iv2=bad_iv2), summary()])
        result = asyncio.run(summarise_record(ctx))
        self.assertEqual((result["iv2"], result["iv3"], result["flags"]), (GOOD_IV2, GOOD_IV3, []))
        self.assertEqual([r.accepted for r in ctx.recorder.records], [False, True])
        self.assertIn("iv3", ctx.recorder.prompts[0])
        self.assertNotIn("- iv3:", ctx.recorder.prompts[1])        # only the failed section asked again

    def test_twice_failed_section_falls_back_to_verbatim_with_flag(self):
        bad_iv2 = "**{BI_CAO}** khai."
        ctx = ctx_with_hearing([summary(iv2=bad_iv2), summary(iv2=bad_iv2)])
        result = asyncio.run(summarise_record(ctx))
        self.assertIsNone(result["iv2"])
        self.assertEqual(result["iv3"], GOOD_IV3)
        self.assertEqual(result["flags"], ["iv2:verbatim_fallback:markdown"])
        record = build_record(ctx.case, ctx.transcript, None, None, summary=result)
        items = record.sections[3].subsections
        self.assertEqual([i.content for i in items], ["verbatim", "verbatim", "summary", "verbatim"])
        self.assertTrue(items[1].summary_fallback and items[1].entries)

    def test_schema_error_twice_is_verbatim(self):
        ctx = ctx_with_hearing(["not json", "{}"])
        result = asyncio.run(summarise_record(ctx))
        self.assertEqual((result["iv2"], result["iv3"]), (None, None))
        self.assertEqual(len(ctx.recorder.records), 2)

    def test_model_error_and_timeout_are_verbatim(self):
        class Failing(ScriptedRecorder):
            async def call(self, *args, **kwargs):
                raise RuntimeError("boom")

        class Slow(ScriptedRecorder):
            async def call(self, *args, **kwargs):
                await asyncio.sleep(1)

        self.assertEqual(asyncio.run(summarise_record(ctx_with_hearing(recorder=Failing())))["flags"],
                         ["error:RuntimeError"])
        with mock.patch.object(trial_record_summary, "SUMMARY_TIMEOUT_SECONDS", 0.05):
            self.assertEqual(asyncio.run(summarise_record(ctx_with_hearing(recorder=Slow())))["flags"], ["timeout"])

    def test_no_source_no_call(self):
        ctx = make_ctx([])
        result = asyncio.run(summarise_record(ctx))
        self.assertEqual(ctx.recorder.records, [])
        self.assertEqual((result["iv2"], result["iv3"], result["flags"]), (None, None, []))


if __name__ == "__main__":
    unittest.main()
