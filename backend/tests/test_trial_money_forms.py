"""Money amounts written with a unit word (nhóm B+, design doc Mục 11.16.3): read into the same value
as the full digit form and compared with the case; amounts in words only are measured. No Gemini call."""
from __future__ import annotations

import unittest

from app.services.trial_money import money_mentions, money_values, word_amounts
from app.services.trial_turn_service import _check_utterance, context_pack
from tests.test_trial_defendant import at
from tests.test_trial_observer import _ctx


class ParseTests(unittest.TestCase):
    def test_forms(self):
        cases = {
            "trị giá 12.500.000 đồng": 12_500_000,
            "trị giá 12,5 triệu đồng": 12_500_000,
            "trị giá 12,5 triệu": 12_500_000,
            "khoảng 1 tỷ 200 triệu đồng": 1_200_000_000,
            "1,2 tỷ": 1_200_000_000,
            "200 nghìn đồng": 200_000,
            "200 ngàn": 200_000,
            "7 tr": 7_000_000,
            "7tr đồng": 7_000_000,
            "1.500 triệu": 1_500_000_000,
            "12500000 đồng": 12_500_000,
        }
        for text, value in cases.items():
            with self.subTest(text):
                self.assertEqual(money_values(text), {value})

    def test_not_money(self):
        for text in ("phạt tù 12 tháng", "ngày 15 tháng 3 năm 2026", "tổn thương 15%", "Điều 173 khoản 2",
                     "trong 15 trường hợp", "15 trang", "khoảng 21 giờ"):
            with self.subTest(text):
                self.assertEqual(money_mentions(text), [])

    def test_one_mention_per_amount(self):
        mentions = money_mentions("Đã bồi thường 2 triệu đồng, còn yêu cầu 2.000.000 đồng.")
        self.assertEqual([(m.value, m.form) for m in mentions], [(2_000_000, "unit"), (2_000_000, "digits")])

    def test_words_only_are_found_for_measuring(self):
        self.assertTrue(word_amounts("bồi thường mười hai triệu rưỡi"))
        self.assertTrue(word_amounts("đã trả mười lăm triệu đồng"))
        self.assertTrue(word_amounts("hai trăm nghìn"))
        self.assertEqual(word_amounts("mười năm tù"), [])
        self.assertEqual(money_mentions("đã trả mười lăm triệu đồng"), [])


class GuardTests(unittest.TestCase):
    """Case fixture amounts: 12.500.000 (định giá), 2.000.000 (yêu cầu, đã bồi thường), 7.000.000 (khoản phụ)."""

    def check(self, speaker: str, text: str):
        ctx = at(_ctx("nguoi_xem"), "luan_toi")
        return _check_utterance(ctx, speaker, text, (speaker,), pack=context_pack(ctx, "luan_toi"))

    def test_valid_amounts_pass_in_every_form(self):
        for text in ("Tài sản trị giá 12,5 triệu đồng.", "Tài sản trị giá 12.500.000 đồng.",
                     "Đã bồi thường 2 triệu.", "Bị cáo định bán với giá 7 tr.", "Bị cáo đã trả 2.000 nghìn đồng."):
            with self.subTest(text):
                violations, _ = self.check("KSV", text)
                self.assertNotIn("unknown_amount", violations)

    def test_invented_amounts_fail_in_every_digit_form(self):
        for text in ("Thiệt hại 13 triệu đồng.", "Thiệt hại 12,6 triệu.", "Tài sản 1 tỷ 200 triệu.", "Tiền 300 nghìn.",
                     "Tiền 8 tr.", "Thiệt hại 13.000.000 đồng."):
            for speaker in ("KSV", "BI_HAI"):
                with self.subTest(text=text, speaker=speaker):
                    violations, _ = self.check(speaker, text)
                    self.assertIn("unknown_amount", violations)

    def test_law_threshold_with_a_unit_is_accepted_for_legal_speakers_only(self):
        # Điều 173 khoản 1: "trị giá từ 2.000.000 đồng đến dưới 50.000.000 đồng".
        self.assertNotIn("unknown_amount", self.check("KSV", "Giá trị dưới 50 triệu đồng.")[0])
        self.assertIn("unknown_amount", self.check("BI_HAI", "Giá trị dưới 50 triệu đồng.")[0])

    def test_words_only_are_measured_not_rejected(self):
        violations, flags = self.check("BI_HAI", "Tôi mất mười lăm triệu đồng.")
        self.assertNotIn("unknown_amount", violations)
        self.assertIn("amount_in_words", flags)


if __name__ == "__main__":
    unittest.main()
