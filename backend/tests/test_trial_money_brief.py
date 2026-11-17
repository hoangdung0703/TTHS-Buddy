"""Money amounts in the prompts of the turns that talk about money (nhóm B, design doc Mục 11.16.3):
the list is exactly what the money guard accepts, written in the canonical form, and the guard still
rejects an invented amount. No Gemini call."""
from __future__ import annotations

import asyncio
import json
import unittest

from app.models.trial import Verdict
from app.prompts.trial_prompts import TUYEN_AN_INSTRUCTION
from app.services.trial_turn_service import (
    _check_utterance,
    _known_numbers,
    _user_prompt,
    context_pack,
    money_amounts,
    money_brief,
    run_ai_turn,
)
from tests.test_trial_defendant import at
from tests.test_trial_observer import _ctx

VERDICT = {"guilty": True, "dieu": "173", "khoan": "1", "diem": [], "penalty_type": "tu", "penalty_months": 12,
           "fine_vnd": None, "suspended": False, "probation_months": None, "applies_dieu_54": False,
           "mitigating": [{"khoan": "1", "diem": "s", "fact_ids": ["F2"]}], "aggravating": [],
           "civil_amount_vnd": 1_500_000, "reasoning_summary": "Nhận định."}


class MoneyBriefTests(unittest.TestCase):
    def test_listed_amounts_are_exactly_what_the_guard_accepts(self):
        ctx = _ctx("nguoi_xem")
        self.assertEqual(set(money_amounts(ctx)), _known_numbers(ctx)[0])
        ctx.fact_ledger.append({"about": "BI_HAI", "fact": "Bị hại đã chi 3.000.000 đồng sửa khóa."})
        ctx.verdict = Verdict.model_validate(VERDICT)
        self.assertEqual(set(money_amounts(ctx)), _known_numbers(ctx)[0])
        self.assertIn(3_000_000, money_amounts(ctx))
        self.assertIn(1_500_000, money_amounts(ctx))

    def test_money_turns_carry_the_list_in_canonical_form(self):
        ctx = at(_ctx("nguoi_xem"), "luan_toi")
        brief = money_brief(ctx, "luan_toi")
        self.assertIn("- 12.500.000 đồng: giá trị tài sản theo kết luận định giá", brief)
        self.assertIn("- 2.000.000 đồng:", brief)
        self.assertIn("không tự cộng, trừ", brief)
        self.assertIn("Mức tiền ghi trong điều luật", brief)
        prompt = _user_prompt(ctx, "Luận tội.", ("KSV",), "luan_toi")
        self.assertIn(brief, prompt.split("=== CHỈ DẪN LƯỢT ===")[1])

    def test_lay_and_reference_variants_and_other_turns(self):
        ctx = _ctx("nguoi_xem")
        lay = money_brief(ctx, "bi_hai_trinh_bay")
        self.assertIn("12.500.000 đồng", lay)
        self.assertNotIn("điều luật", lay)
        self.assertIn("để đối chiếu", money_brief(ctx, "nghi_an"))
        for slot in ("khai_mac", "hdxx_hoi_bi_cao", "ksv_hoi", "loi_sau_cung"):
            self.assertEqual(money_brief(ctx, slot), "", slot)

    def test_tuyen_an_lists_the_decided_compensation_and_no_fee_amount(self):
        ctx = _ctx("nguoi_xem")
        ctx.verdict = Verdict.model_validate(VERDICT)
        self.assertIn("1.500.000 đồng: số tiền bồi thường Hội đồng xét xử đã quyết định", money_brief(ctx, "tuyen_an"))
        self.assertIn("không ghi số tiền án phí", TUYEN_AN_INSTRUCTION)

    def test_guard_still_rejects_an_invented_amount(self):
        ctx = at(_ctx("nguoi_xem"), "luan_toi")
        pack = context_pack(ctx, "luan_toi")
        ok, _ = _check_utterance(ctx, "KSV", "Tài sản trị giá 12.500.000 đồng, đã bồi thường 2.000.000 đồng.",
                                 ("KSV",), pack=pack)
        self.assertNotIn("unknown_amount", ok)
        for invented in ("Thiệt hại thực tế là 777.000.000 đồng.", "Phần còn lại là 10.500.000 đồng.",
                         "Bị cáo phải chịu 200.000 đồng án phí hình sự sơ thẩm."):
            violations, _ = _check_utterance(ctx, "KSV", invented, ("KSV",), pack=pack)
            self.assertIn("unknown_amount", violations, invented)

    def test_a_speech_with_an_invented_amount_is_regenerated(self):
        ctx = at(_ctx("nguoi_xem"), "luan_toi")
        bad = json.dumps({"text": "Về trách nhiệm dân sự: buộc bị cáo bồi thường 777.000.000 đồng theo khoản 1 Điều "
                                  "173 Bộ luật Hình sự."}, ensure_ascii=False)
        good = json.dumps({"text": "Về trách nhiệm dân sự: buộc bị cáo bồi thường phần còn lại theo yêu cầu của bị "
                                   "hại, theo khoản 1 Điều 173 Bộ luật Hình sự."}, ensure_ascii=False)
        ctx.recorder.answers = [bad, good]
        produced = asyncio.run(run_ai_turn(ctx))
        self.assertEqual([r.accepted for r in ctx.recorder.records], [False, True])
        self.assertEqual(ctx.recorder.records[0].guard_violations, ["unknown_amount"])
        self.assertNotIn("777", produced[0].text)


if __name__ == "__main__":
    unittest.main()
