"""Unit tests for the Chủ tọa's decision form checks (chặng R4, trial_chair_decision): every rule, hard
(blocks "Chốt quyết định") or soft (a warning only), against the real article texts of the corpus.
No Gemini call."""
from __future__ import annotations

import unittest

from app.models.trial import ChairDecision
from app.services.trial_chair_decision import check_decision
from app.services.trial_verdict_guard import check_verdict
from tests.trial_fixtures import pack_for, valid_case_file, valid_draft_dict, valid_options

REASONING = "Nhận định của Hội đồng xét xử về hành vi, chứng cứ và các tình tiết của vụ án. " * 4
STRONG = [{"khoan": "1", "diem": "b", "fact_ids": ["F2"]}, {"khoan": "1", "diem": "s", "fact_ids": ["F2"]}]


def decision(**changes) -> ChairDecision:
    data = {"guilty": True, "dieu": "173", "khoan": "1", "diem": [], "penalty_type": "tu", "penalty_months": 12,
            "fine_vnd": None, "suspended": False, "probation_months": None, "applies_dieu_54": False,
            "mitigating": STRONG, "aggravating": [], "civil_amount_vnd": None, "reasoning_summary": REASONING,
            "exhibits": [{"evidence_id": "E1", "disposition": "tra_lai"}],
            "defendant_pays_criminal_fee": True, "defendant_pays_civil_fee": False}
    data.update(changes)
    return ChairDecision.model_validate(data)


def case(crime: str = "173", khoan: str = "1", **defendant):
    draft = valid_draft_dict()
    draft["charge"] = {**draft["charge"], "dieu": crime, "khoan": khoan}
    draft["defendant"].update(defendant)
    options = valid_options().model_copy(update={"crime_key": f"blhs_{crime}"})
    return valid_case_file(options, draft)


def codes(d: ChairDecision, crime: str = "173", khoan: str = "1", **defendant) -> tuple[set[str], set[str]]:
    check = check_decision(d, case(crime, khoan, **defendant), pack_for(f"blhs_{crime}"))
    return {f.code for f in check.errors}, {f.code for f in check.warnings}


class DecisionCheckTests(unittest.TestCase):
    def test_a_lawful_decision_passes_clean(self):
        self.assertEqual(codes(decision()), (set(), set()))
        check = check_decision(decision(), case(), pack_for("blhs_173"))
        self.assertTrue(check.ok)

    def test_every_finding_has_field_message_and_basis(self):
        d = decision(penalty_months=48, exhibits=[], reasoning_summary="ngắn", civil_amount_vnd=9_000_000)
        check = check_decision(d, case(), pack_for("blhs_173"))
        for finding in [*check.errors, *check.warnings]:
            self.assertTrue(finding.field and finding.message and finding.basis, finding)
            self.assertTrue(all("Bộ luật" in b for b in finding.basis), finding)

    # --- hard errors ---------------------------------------------------------------------------
    def test_frame_of_the_khoan(self):
        self.assertIn("above_frame", codes(decision(penalty_months=48))[0])          # khoản 1: tối đa 03 năm
        self.assertIn("below_frame", codes(decision(penalty_months=4))[0])           # khoản 1: từ 06 tháng
        self.assertEqual(codes(decision(penalty_months=36))[0], set())

    def test_dieu_54_needs_two_strong_mitigating(self):
        weak = [STRONG[0]]
        errors = codes(decision(penalty_months=4, applies_dieu_54=True, mitigating=weak))[0]
        self.assertIn("dieu54_conditions", errors)

    def test_dieu_54_khoan_1_floor_is_the_adjacent_lighter_frame(self):
        # Khoản 2 (02-07 năm); the adjacent lighter frame (khoản 1) starts at 06 tháng tù.
        self.assertIn("below_adjacent_frame", codes(decision(khoan="2", penalty_months=4, applies_dieu_54=True),
                                                    khoan="2")[0])
        self.assertEqual(codes(decision(khoan="2", penalty_months=6, applies_dieu_54=True), khoan="2")[0], set())
        self.assertIn("below_frame", codes(decision(khoan="2", penalty_months=18), khoan="2")[0])

    def test_dieu_54_khoan_3_lightest_frame_allows_a_lighter_kind(self):
        # Điều 171 khoản 1: only "phạt tù từ 01 năm đến 05 năm" - no cải tạo không giam giữ in the frame.
        nc = dict(penalty_type="cai_tao_khong_giam_giu", penalty_months=12, dieu="171")
        self.assertIn("non_custodial_not_in_frame", codes(decision(**nc), crime="171")[0])
        self.assertEqual(codes(decision(**nc, applies_dieu_54=True), crime="171")[0], set())
        self.assertEqual(codes(decision(dieu="171", penalty_months=6, applies_dieu_54=True), crime="171")[0], set())
        self.assertIn("below_frame", codes(decision(dieu="171", penalty_months=6), crime="171")[0])
        # Điều 171 khoản 2 (03-10 năm) is "rất nghiêm trọng": no cải tạo không giam giữ (Điều 36, Điều 9).
        self.assertIn("non_custodial_class", codes(decision(**{**nc, "khoan": "2"}, applies_dieu_54=True),
                                                   crime="171", khoan="2")[0])

    def test_prison_general_minimum(self):
        errors = codes(decision(penalty_months=2, applies_dieu_54=True))[0]   # khung nhẹ nhất, Điều 54 khoản 3
        self.assertEqual(errors, {"prison_general_range"})
        self.assertIn("penalty_months", codes(decision(penalty_months=None))[0])

    def test_non_custodial_range(self):
        nc = dict(penalty_type="cai_tao_khong_giam_giu")
        self.assertEqual(codes(decision(**nc, penalty_months=12))[0], set())
        self.assertIn("non_custodial_range", codes(decision(**nc, penalty_months=4))[0])
        self.assertIn("non_custodial_range", codes(decision(**nc, penalty_months=40))[0])

    def test_fine(self):
        fine = dict(penalty_type="phat_tien", penalty_months=None)
        self.assertIn("fine_not_in_frame", codes(decision(**fine, fine_vnd=5_000_000))[0])
        self.assertIn("fine_min", codes(decision(**fine, fine_vnd=500_000, applies_dieu_54=True))[0])
        self.assertEqual(codes(decision(**fine, fine_vnd=5_000_000, applies_dieu_54=True))[0], set())
        self.assertIn("fine_not_main", codes(decision(fine_vnd=5_000_000))[0])

    def test_suspended_sentence(self):
        self.assertEqual(codes(decision(suspended=True, probation_months=24))[0], set())
        self.assertIn("probation_range", codes(decision(suspended=True, probation_months=6))[0])
        self.assertIn("suspended_prison", codes(decision(khoan="2", penalty_months=48, suspended=True,
                                                         probation_months=24), khoan="2")[0])
        self.assertIn("probation_without_suspension", codes(decision(probation_months=24))[0])

    def test_circumstances(self):
        self.assertIn("circumstance_unknown", codes(decision(mitigating=[{"khoan": "1", "diem": "zz",
                                                                          "fact_ids": ["F2"]}]))[0])
        self.assertIn("circumstance_no_fact", codes(decision(mitigating=[{"khoan": "1", "diem": "s",
                                                                          "fact_ids": []}]))[0])
        self.assertIn("circumstance_unknown_fact", codes(decision(mitigating=[{"khoan": "1", "diem": "s",
                                                                               "fact_ids": ["F9"]}]))[0])

    def test_charge_and_points(self):
        self.assertIn("charge_article", codes(decision(dieu="174"))[0])
        self.assertIn("khoan_unknown", codes(decision(khoan="9"))[0])
        # Khoản 5 of Điều 173 only lists additional penalties ("còn có thể bị phạt tiền"): not a frame.
        self.assertIn("khoan_unknown", codes(decision(khoan="5", penalty_months=12))[0])
        # Điều 51 khoản 3 and Điều 52 khoản 2 are rules about circumstances, not circumstances.
        self.assertIn("circumstance_unknown", codes(decision(mitigating=[*STRONG, {"khoan": "3", "diem": "",
                                                                                  "fact_ids": ["F2"]}]))[0])
        self.assertIn("circumstance_unknown", codes(decision(aggravating=[{"khoan": "2", "diem": "",
                                                                           "fact_ids": ["F1"]}]))[0])
        self.assertIn("diem_unknown", codes(decision(diem=["zz"]))[0])
        self.assertIn("conviction_without_penalty", codes(decision(penalty_type="khong", penalty_months=None))[0])

    def test_reasoning_length(self):
        self.assertIn("reasoning_length", codes(decision(reasoning_summary="Ngắn."))[0])
        self.assertIn("reasoning_length", codes(decision(reasoning_summary="x" * 2001))[0])

    def test_exhibits(self):
        self.assertIn("exhibit_missing", codes(decision(exhibits=[]))[0])
        self.assertIn("exhibit_unknown", codes(decision(exhibits=[{"evidence_id": "E1", "disposition": "tra_lai"},
                                                                  {"evidence_id": "E2", "disposition": "luu_ho_so"}]))[0])
        self.assertIn("exhibit_duplicate", codes(decision(exhibits=[{"evidence_id": "E1", "disposition": "tra_lai"}] * 2))[0])

    def test_acquittal(self):
        free = dict(guilty=False, penalty_type="khong", penalty_months=None, mitigating=[],
                    defendant_pays_criminal_fee=False)
        self.assertEqual(codes(decision(**free))[0], set())
        self.assertIn("acquittal_with_penalty", codes(decision(**{**free, "penalty_type": "tu"}))[0])
        self.assertIn("acquittal_criminal_fee", codes(decision(**{**free, "defendant_pays_criminal_fee": True}))[0])
        self.assertIn("acquittal_victim_fee", codes(decision(**free, dieu="134"), crime="134")[1])
        self.assertIn("civil_negative", codes(decision(civil_amount_vnd=-1))[0])

    # --- soft warnings: never block ------------------------------------------------------------
    def test_warnings_do_not_block(self):
        cases = {
            "khoan_heavier": (decision(khoan="2", penalty_months=30), {}),                    # Q9
            "civil_over_claim": (decision(civil_amount_vnd=9_000_000), {}),                   # Q11
            "civil_fee_without_claim": (decision(defendant_pays_civil_fee=True), {}),
            "exhibit_confiscated_property": (decision(exhibits=[{"evidence_id": "E1",
                                                                  "disposition": "tich_thu_sung_ngan_sach"}]), {}),
            "mitigating_other_reason": (decision(mitigating=[*STRONG, {"khoan": "2", "diem": "", "fact_ids": ["F2"]}]),
                                        {}),
            "aggravating_frame_overlap": (decision(khoan="2", diem=["c"], penalty_months=30,
                                                   aggravating=[{"khoan": "1", "diem": "g", "fact_ids": ["F1"]}]),
                                          {"khoan": "2"}),
            "suspended_without_mitigating": (decision(suspended=True, probation_months=24, mitigating=[]), {}),
            "release_needed": (decision(suspended=True, probation_months=24),
                               {"preventive_measure": "tạm giam"}),
        }
        for code, (d, extra) in cases.items():
            khoan = extra.pop("khoan", "1")
            errors, warnings = codes(d, khoan=khoan, **extra)
            self.assertIn(code, warnings, code)
            self.assertNotIn(code, errors, code)

    def test_mitigating_khoan_2_without_point_is_not_an_unknown_point(self):
        # Điều 51 khoản 2 has no điểm ("Tòa án có thể coi đầu thú hoặc tình tiết khác là tình tiết giảm nhẹ").
        errors = codes(decision(mitigating=[*STRONG, {"khoan": "2", "diem": "", "fact_ids": ["F2"]}]))[0]
        self.assertEqual(errors, set())
        self.assertIn("circumstance_unknown", codes(decision(mitigating=[{"khoan": "1", "diem": "",
                                                                          "fact_ids": ["F2"]}]))[0])

    def test_the_ai_guard_of_other_roles_is_unchanged(self):
        # Decision Q10: the gaps of check_verdict (heavier khoản blocked, no adjacent-frame floor) stay.
        pack, file = pack_for("blhs_173"), case()
        heavier = decision(khoan="2", penalty_months=30).to_verdict()
        self.assertTrue(check_verdict(heavier, file, pack).errors)
        below = decision(khoan="1", penalty_months=1, applies_dieu_54=True).to_verdict()
        self.assertEqual(check_verdict(below, file, pack).errors, [])
        self.assertIn("prison_general_range", codes(decision(penalty_months=1, applies_dieu_54=True))[0])


if __name__ == "__main__":
    unittest.main()
