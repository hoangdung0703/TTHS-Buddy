"""Unit tests: deterministic legal pack + Rule 9 pair guard (design doc Mục 4, 5.1, 8.1).

Run from backend/:  ../.venv/bin/python -m unittest discover -s tests -v
"""
from __future__ import annotations

import unittest

from app.services.trial_config import BLHS_DOCUMENT, BLTTHS_DOCUMENT, CRIMES, get_crime
from app.services.trial_legal_pack import missing_keys, pack_request_for_crime
from app.services.trial_rule9 import check_citations, extract_citations, lay_speaker_citations, mask_unverified_citations
from tests.trial_fixtures import pack_for


def kinds(text: str, mode: str = "lenient") -> list[str]:
    return [v.kind for v in check_citations(text, pack_for("blhs_173"), mode)]


class LegalPackTests(unittest.TestCase):
    def test_every_crime_pack_is_complete(self):
        for key, crime in CRIMES.items():
            with self.subTest(crime=key):
                self.assertEqual(missing_keys(pack_for(key), pack_request_for_crime(crime)), [])

    def test_khoan_and_diem_are_parsed_from_real_text(self):
        article = pack_for("blhs_173").get(BLHS_DOCUMENT, "173")
        self.assertEqual(sorted(article.khoans, key=int), ["1", "2", "3", "4", "5"])
        self.assertEqual(article.khoans["1"].diem, frozenset("abcdđ"))
        self.assertTrue(article.has_diem("2", "c"))
        self.assertFalse(article.has_diem("1", "e"))
        self.assertIn("168", article.cross_refs)

    def test_khoan_split_article_is_reassembled_in_order(self):
        article = pack_for("blhs_134").get(BLHS_DOCUMENT, "134")
        self.assertEqual(sorted(article.khoans, key=int), ["1", "2", "3", "4", "5", "6"])
        self.assertTrue(article.has_diem("1", "k"))

    def test_dieu_51_has_point_s(self):
        self.assertTrue(pack_for("blhs_173").get(BLHS_DOCUMENT, "51").has_diem("1", "s"))

    def test_step_slices(self):
        pack = pack_for("blhs_173")
        step2 = {(a.source_document, a.dieu_number) for a in pack.slice_for_step(2, "173")}
        step4 = {(a.source_document, a.dieu_number) for a in pack.slice_for_step(4, "173")}
        step11 = {(a.source_document, a.dieu_number) for a in pack.slice_for_step(11, "173")}
        self.assertIn((BLTTHS_DOCUMENT, "301"), step2)
        self.assertNotIn((BLHS_DOCUMENT, "173"), step2)
        self.assertIn((BLTTHS_DOCUMENT, "309"), step4)
        self.assertIn((BLHS_DOCUMENT, "173"), step4)
        self.assertNotIn((BLHS_DOCUMENT, "51"), step4)
        self.assertIn((BLTTHS_DOCUMENT, "327"), step11)
        self.assertIn((BLHS_DOCUMENT, "51"), step11)

    def test_slot_slices_are_trimmed_and_carry_what_each_speech_needs(self):
        pack = pack_for("blhs_173")
        closing = {a.key for a in pack.slice_for_step(8, "173")}
        expected = {"luan_toi": {("321", BLTTHS_DOCUMENT), ("52", BLHS_DOCUMENT)},
                    "bao_chua": {("322", BLTTHS_DOCUMENT), ("65", BLHS_DOCUMENT)},
                    "tuyen_an": {("327", BLTTHS_DOCUMENT), ("331", BLTTHS_DOCUMENT), ("51", BLHS_DOCUMENT)}}
        for slot, needed in expected.items():
            keys = {a.key for a in pack.slice_for_slot(slot, 8, "173")}
            with self.subTest(slot=slot):
                self.assertLess(len(keys), len(closing))
                self.assertIn((BLHS_DOCUMENT, "173"), keys)
                for dieu, doc in needed:
                    self.assertIn((doc, dieu), keys)
        self.assertEqual({a.key for a in pack.slice_for_slot("khai_mac", 2, "173")},
                         {a.key for a in pack.slice_for_step(2, "173")})

    def test_pack_round_trips_through_stored_payloads(self):
        from app.services.trial_legal_pack import build_pack
        pack = pack_for("blhs_134")
        rebuilt = build_pack(pack.to_payloads())
        self.assertEqual(set(rebuilt.articles), set(pack.articles))
        for key, article in pack.articles.items():
            self.assertEqual({k: v.diem for k, v in rebuilt.articles[key].khoans.items()},
                             {k: v.diem for k, v in article.khoans.items()}, key)
            self.assertEqual(rebuilt.articles[key].cross_refs, article.cross_refs, key)

    def test_no_crime_khoan_in_whitelist_carries_death_penalty(self):
        for key, crime in CRIMES.items():
            article = pack_for(key).get(BLHS_DOCUMENT, crime.dieu)
            for khoan in crime.allowed_khoan:
                with self.subTest(crime=key, khoan=khoan):
                    self.assertNotIn("tử hình", article.khoans[khoan].text)


class Rule9PairTests(unittest.TestCase):
    def test_grounded_citation_passes(self):
        self.assertEqual(kinds("theo khoản 1 Điều 173 Bộ luật Hình sự"), [])
        self.assertEqual(kinds("căn cứ Điều 326 Bộ luật Tố tụng hình sự"), [])

    def test_number_valid_in_other_code_is_rejected(self):
        # The hole in the number-only guard: 326 exists, but as a BLTTHS article.
        self.assertEqual(kinds("khoản 1 Điều 326 Bộ luật Hình sự"), ["unknown_pair"])
        self.assertEqual(kinds("Điều 173 Bộ luật Tố tụng hình sự"), ["unknown_pair"])

    def test_abbreviations(self):
        self.assertEqual(kinds("khoản 1 Điều 173 BLHS và Điều 327 BLTTHS"), [])

    def test_missing_khoan_and_diem(self):
        self.assertEqual(kinds("khoản 9 Điều 173 Bộ luật Hình sự"), ["khoan_missing"])
        self.assertEqual(kinds("điểm z khoản 1 Điều 51 Bộ luật Hình sự"), ["diem_missing"])
        self.assertEqual(kinds("điểm e khoản 1 Điều 173 Bộ luật Hình sự"), ["diem_missing"])
        self.assertEqual(kinds("điểm b, s khoản 1 Điều 51 Bộ luật Hình sự"), [])

    def test_law_name_inherited_across_connectors(self):
        text = "áp dụng khoản 1 Điều 173 và điểm s khoản 1 Điều 51 Bộ luật Hình sự"
        self.assertEqual(kinds(text, "strict"), [])
        self.assertEqual({c.law for c in extract_citations(text)}, {BLHS_DOCUMENT})

    def test_list_of_numbers(self):
        self.assertEqual(kinds("các Điều 50, 51 Bộ luật Hình sự", "strict"), [])
        self.assertEqual(kinds("các Điều 51, 999 Bộ luật Hình sự"), ["unknown_pair"])

    def test_missing_law_strict_vs_lenient(self):
        self.assertEqual(kinds("khoản 1 Điều 173", "strict"), ["missing_law"])
        self.assertEqual(kinds("khoản 1 Điều 173", "lenient"), [])  # only BLHS has 173 in the pack
        self.assertEqual(kinds("Điều 47", "lenient"), ["ambiguous_law"])  # BLHS 47 and BLTTHS 47
        self.assertEqual(kinds("Điều 999", "lenient"), ["unknown_pair"])

    def test_other_law_is_rejected(self):
        self.assertEqual(kinds("Điều 46 Luật Tổ chức Tòa án nhân dân"), ["other_law"])

    def test_cross_reference_inside_pack_article_is_allowed(self):
        self.assertEqual(kinds("Điều 168 Bộ luật Hình sự"), [])

    def test_no_false_positive_on_ordinary_words(self):
        self.assertEqual(extract_citations("điều kiện hoàn cảnh, điều này cho thấy"), [])

    def test_lay_speaker_may_not_cite(self):
        self.assertTrue(lay_speaker_citations("Tôi biết Điều 173 rồi"))
        self.assertFalse(lay_speaker_citations("Tôi xin lỗi bị hại"))

    def test_masking_student_text(self):
        masked, count = mask_unverified_citations(
            "Đề nghị áp dụng Điều 999 Bộ luật Hình sự và khoản 1 Điều 173 Bộ luật Hình sự", pack_for("blhs_173"),
            "Kiểm sát viên")
        self.assertEqual(count, 1)
        self.assertNotIn("999", masked)
        self.assertIn("khoản 1 Điều 173", masked)
        self.assertIn("Kiểm sát viên", masked)


if __name__ == "__main__":
    unittest.main()
