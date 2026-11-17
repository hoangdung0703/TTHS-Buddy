"""Offline case table for the AI nghị án guard (nhóm B, design doc Mục 11.16): decisions for the four
crimes in scope (BLHS Điều 134, 171, 173, 174; khoản 1-2), lawful and unlawful, each with its expected
outcome and the corpus text it rests on. The new guard (trial_verdict_guard, shared rules) must get
every case right; the frozen pre-nhóm-B guard is run on the same table to show which outcomes moved.

Outcomes: "pass" (no finding), "warn" (soft findings only: measured, never blocks), "block" (a hard
finding: the decision is regenerated). The old guard knew no soft findings, so it is compared on
blocking only. No Gemini call; legal packs from ingestion/chunks.json.
"""
from __future__ import annotations

import asyncio
import json
import unittest
from dataclasses import dataclass

from app.models.trial import Verdict
from app.services.trial_sentencing_rules import RULES, hard_constraints_text
from app.services.trial_turn_service import TrialGuardFailure, _deliberate
from app.services.trial_verdict_guard import check_verdict
from tests import trial_legacy_verdict_guard as legacy
from tests.trial_fixtures import pack_for, valid_case_file, valid_draft_dict, valid_options

S = {"khoan": "1", "diem": "s", "fact_ids": ["F2"]}
B = {"khoan": "1", "diem": "b", "fact_ids": ["F2"]}
TWO = [S, B]


@dataclass(frozen=True)
class Case:
    name: str
    crime: str             # charged Điều
    charged: str           # charged khoản
    verdict: dict          # overrides of the base verdict
    expected: str          # pass | warn | block
    code: str | None       # the finding expected (block: hard code; warn: soft code)
    basis: str             # corpus text the expectation rests on
    group: str = ""        # "oan": wrongly blocked before nhóm B; "lot": wrongly passed before


def base_verdict(crime: str, charged: str, overrides: dict) -> Verdict:
    data = {"guilty": True, "dieu": crime, "khoan": charged, "diem": [], "penalty_type": "tu", "penalty_months": 12,
            "fine_vnd": None, "suspended": False, "probation_months": None, "applies_dieu_54": False,
            "mitigating": [S], "aggravating": [], "civil_amount_vnd": None, "reasoning_summary": "Nhận định."}
    data.update(overrides)
    return Verdict.model_validate(data)


def case_file(crime: str, charged: str, preventive: str | None = None):
    draft = valid_draft_dict()
    draft["charge"] = {**draft["charge"], "dieu": crime, "khoan": charged}
    if preventive:
        draft["defendant"]["preventive_measure"] = preventive
    return valid_case_file(valid_options().model_copy(update={"crime_key": f"blhs_{crime}"}), draft)


NC = "cai_tao_khong_giam_giu"
D38 = 'Đ38 k1 BLHS: "mức tối thiểu là 03 tháng và mức tối đa là 20 năm"'
D54_1 = 'Đ54 k1 BLHS: "dưới mức thấp nhất ... nhưng phải trong khung hình phạt liền kề nhẹ hơn ... ít nhất hai tình tiết giảm nhẹ quy định tại khoản 1 Điều 51"'
D54_3 = 'Đ54 k3 BLHS: "khung hình phạt nhẹ nhất ... chuyển sang một hình phạt khác thuộc loại nhẹ hơn"'
D36 = 'Đ36 k1 BLHS: "từ 06 tháng đến 03 năm đối với người phạm tội ít nghiêm trọng, phạm tội nghiêm trọng"'
D9 = 'Đ9 k1 điểm b BLHS: nghiêm trọng "từ trên 03 năm tù đến 07 năm tù"'
D35 = 'Đ35 k3 BLHS: "không được thấp hơn 1.000.000 đồng"'
D65 = 'Đ65 k1 BLHS: "xử phạt tù không quá 03 năm ... thời gian thử thách từ 01 năm đến 05 năm"'
D298 = 'Đ298 k2 BLTTHS: "theo khoản khác với khoản mà Viện kiểm sát đã truy tố trong cùng một điều luật"'
D51_3 = 'Đ51 k3 BLHS: "dấu hiệu định tội hoặc định khung thì không được coi là tình tiết giảm nhẹ" (quy tắc)'
D52_2 = 'Đ52 k2 BLHS: "dấu hiệu định tội hoặc định khung hình phạt thì không được coi là tình tiết tăng nặng" (quy tắc)'
D326 = 'Đ326 k2 BLTTHS: "Việc nghị án chỉ được căn cứ vào những chứng cứ, tài liệu đã được thẩm tra tại phiên tòa"'

TABLE: tuple[Case, ...] = (
    # --- lawful ------------------------------------------------------------------------------------
    Case("173k1 tù 12 tháng", "173", "1", {}, "pass", None, 'Đ173 k1: "phạt tù từ 06 tháng đến 03 năm"'),
    Case("173k1 CTKGG 12 tháng", "173", "1", {"penalty_type": NC}, "pass", None,
         'Đ173 k1: "phạt cải tạo không giam giữ đến 03 năm"'),
    Case("173k1 tù 24 treo 36", "173", "1", {"penalty_months": 24, "suspended": True, "probation_months": 36},
         "pass", None, D65),
    Case("173k2 tù 30 tháng", "173", "2", {"khoan": "2", "penalty_months": 30}, "pass", None,
         'Đ173 k2: "phạt tù từ 02 năm đến 07 năm"'),
    Case("173k2 Đ54 tù 12 (khung k1)", "173", "2", {"khoan": "2", "applies_dieu_54": True, "mitigating": TWO},
         "pass", None, D54_1),
    Case("174k1 tù 6 tháng", "174", "1", {"penalty_months": 6}, "pass", None, 'Đ174 k1: "phạt tù từ 06 tháng"'),
    Case("174k2 tù 84 tháng", "174", "2", {"khoan": "2", "penalty_months": 84}, "pass", None,
         'Đ174 k2: "phạt tù từ 02 năm đến 07 năm"'),
    Case("171k1 tù 12 tháng", "171", "1", {}, "pass", None, 'Đ171 k1: "phạt tù từ 01 năm đến 05 năm"'),
    Case("171k1 Đ54 tù 6 tháng", "171", "1", {"penalty_months": 6, "applies_dieu_54": True, "mitigating": TWO},
         "pass", None, D54_3),
    Case("171k2 tù 36 tháng", "171", "2", {"khoan": "2", "penalty_months": 36}, "pass", None,
         'Đ171 k2: "phạt tù từ 03 năm đến 10 năm"'),
    Case("134k1 CTKGG 24 tháng", "134", "1", {"penalty_type": NC, "penalty_months": 24}, "pass", None,
         'Đ134 k1: "phạt cải tạo không giam giữ đến 03 năm"'),
    Case("134k2 tù 24 tháng", "134", "2", {"khoan": "2", "penalty_months": 24}, "pass", None,
         'Đ134 k2: "phạt tù từ 02 năm đến 06 năm"'),
    Case("173k1 tuyên không phạm tội", "173", "1", {"guilty": False, "penalty_type": "khong", "penalty_months": None,
                                                     "mitigating": []}, "pass", None, "Đ326 k3 điểm c BLTTHS"),
    # --- wrongly blocked before nhóm B ("oan") ------------------------------------------------------
    Case("173 truy tố k1, xử k2", "173", "1", {"khoan": "2", "penalty_months": 30}, "warn", "khoan_heavier", D298,
         "oan"),
    Case("171k1 Đ54 CTKGG 12 (khung nhẹ nhất)", "171", "1",
         {"penalty_type": NC, "applies_dieu_54": True, "mitigating": TWO}, "pass", None, f"{D54_3}; {D36}; {D9}",
         "oan"),
    Case("174k2 Đ54 CTKGG 12 (khung liền kề k1 có CTKGG)", "174", "2",
         {"khoan": "2", "penalty_type": NC, "applies_dieu_54": True, "mitigating": TWO}, "pass", None,
         f"{D54_1}; {D36}; {D9}", "oan"),
    Case("134k2 Đ54 CTKGG 12", "134", "2",
         {"khoan": "2", "penalty_type": NC, "applies_dieu_54": True, "mitigating": TWO}, "pass", None,
         f"{D54_1}; {D36}; {D9}", "oan"),
    Case("171k1 Đ54 phạt tiền 20.000.000 (khung nhẹ nhất)", "171", "1",
         {"penalty_type": "phat_tien", "penalty_months": None, "fine_vnd": 20_000_000, "applies_dieu_54": True,
          "mitigating": TWO}, "pass", None, f"{D54_3}; Đ35 k1 điểm a BLHS", "oan"),
    # --- wrongly passed before nhóm B ("lot") -------------------------------------------------------
    Case("173k2 Đ54 tù 4 (dưới khung liền kề)", "173", "2",
         {"khoan": "2", "penalty_months": 4, "applies_dieu_54": True, "mitigating": TWO}, "block",
         "below_adjacent_frame", D54_1, "lot"),
    Case("174k2 Đ54 tù 5 (dưới khung liền kề)", "174", "2",
         {"khoan": "2", "penalty_months": 5, "applies_dieu_54": True, "mitigating": TWO}, "block",
         "below_adjacent_frame", D54_1, "lot"),
    Case("173k1 Đ54 tù 2 tháng", "173", "1", {"penalty_months": 2, "applies_dieu_54": True, "mitigating": TWO},
         "block", "prison_general_range", D38, "lot"),
    Case("171k1 Đ54 tù 1 tháng", "171", "1", {"penalty_months": 1, "applies_dieu_54": True, "mitigating": TWO},
         "block", "prison_general_range", D38, "lot"),
    Case("Tình tiết giảm nhẹ khoản 3 Điều 51", "173", "1", {"mitigating": [S, {"khoan": "3", "diem": "",
                                                                                "fact_ids": ["F2"]}]},
         "block", "circumstance_unknown", D51_3, "lot"),
    Case("Tình tiết tăng nặng khoản 2 Điều 52", "174", "1", {"aggravating": [{"khoan": "2", "diem": "",
                                                                              "fact_ids": ["F1"]}]},
         "block", "circumstance_unknown", D52_2, "lot"),
    Case("Tình tiết khoản 1 Điều 51 không có điểm", "173", "1", {"mitigating": [{"khoan": "1", "diem": "",
                                                                                 "fact_ids": ["F2"]}]},
         "block", "circumstance_unknown", 'Đ51 k1 BLHS: các tình tiết là các điểm "a) ... x)"', "lot"),
    Case("Tình tiết không gắn sự việc", "134", "1", {"mitigating": [{"khoan": "1", "diem": "s", "fact_ids": []}]},
         "block", "circumstance_no_fact", D326, "lot"),
    Case("Thử thách mà không có án treo", "173", "1", {"probation_months": 24}, "block",
         "probation_without_suspension", D65, "lot"),
    Case("Phạt tiền kèm tù (hình phạt bổ sung chưa mô phỏng)", "173", "1", {"fine_vnd": 5_000_000}, "block",
         "fine_not_main", 'Đ35 k1 BLHS (phạt tiền là hình phạt chính); bổ sung: ngoài phạm vi mô phỏng', "lot"),
    # --- unlawful, blocked before and after ---------------------------------------------------------
    Case("173k1 tù 40 tháng", "173", "1", {"penalty_months": 40}, "block", "above_frame",
         'Đ173 k1: "đến 03 năm"'),
    Case("173k1 tù 4 không Đ54", "173", "1", {"penalty_months": 4}, "block", "below_frame", D54_1),
    Case("171k2 tù 30 không Đ54", "171", "2", {"khoan": "2", "penalty_months": 30}, "block", "below_frame", D54_1),
    Case("Xử Điều khác Điều truy tố", "173", "1", {"dieu": "174"}, "block", "charge_article",
         'Đ298 k1 BLTTHS: "theo tội danh mà Viện kiểm sát truy tố"'),
    Case("Đ54 với một tình tiết khoản 1", "174", "1", {"penalty_months": 4, "applies_dieu_54": True},
         "block", "dieu54_conditions", D54_1),
    Case("Án treo với tù 48 tháng", "173", "2", {"khoan": "2", "penalty_months": 48, "suspended": True,
                                                  "probation_months": 24}, "block", "suspended_prison", D65),
    Case("Thử thách 6 tháng", "134", "1", {"suspended": True, "probation_months": 6}, "block", "probation_range", D65),
    Case("Không phạm tội mà có hình phạt", "173", "1", {"guilty": False}, "block", "acquittal_with_penalty",
         "Đ326 k3 điểm c, d BLTTHS"),
    Case("Có tội mà không có hình phạt", "174", "1", {"penalty_type": "khong", "penalty_months": None}, "block",
         "conviction_without_penalty", "Đ326 k3 điểm d BLTTHS; miễn hình phạt ngoài phạm vi"),
    Case("CTKGG 4 tháng", "173", "1", {"penalty_type": NC, "penalty_months": 4}, "block", "non_custodial_range", D36),
    Case("171k2 Đ54 CTKGG (rất nghiêm trọng)", "171", "2",
         {"khoan": "2", "penalty_type": NC, "applies_dieu_54": True, "mitigating": TWO}, "block",
         "non_custodial_class", f"{D36}; Đ9 k1 điểm c BLHS: rất nghiêm trọng \"từ trên 07 năm tù\""),
    Case("171k1 Đ54 phạt tiền 500.000", "171", "1",
         {"penalty_type": "phat_tien", "penalty_months": None, "fine_vnd": 500_000, "applies_dieu_54": True,
          "mitigating": TWO}, "block", "fine_min", D35),
    Case("Sự việc không có trong hồ sơ", "173", "1", {"mitigating": [{"khoan": "1", "diem": "s", "fact_ids": ["F9"]}]},
         "block", "circumstance_unknown_fact", D326),
    Case("134k1 điểm về người dưới 16 tuổi", "134", "1", {"diem": ["c"]}, "block", "diem_minor",
         "Đ134 k1 điểm c: \"Đối với người dưới 16 tuổi\" - ngoài phạm vi (quyết định 2026-10-19)"),
    Case("173 khoản 5 (chỉ hình phạt bổ sung)", "173", "1", {"khoan": "5"}, "block", "khoan_unknown",
         'Đ173 k5: "Người phạm tội còn có thể bị phạt tiền" - không phải khung hình phạt chính'),
    # --- soft: measured, never blocks (corpus không đủ hoặc chỉ là nhắc kiểm tra) --------------------
    Case("Bồi thường vượt yêu cầu", "173", "1", {"civil_amount_vnd": 9_000_000}, "warn", "civil_over_claim",
         "Corpus không đủ: nguyên tắc dân sự không vượt yêu cầu không có trong corpus"),
    Case("Án treo không nêu tình tiết giảm nhẹ", "174", "1", {"suspended": True, "probation_months": 24,
                                                              "mitigating": []}, "warn",
         "suspended_without_mitigating", f"{D65} (\"căn cứ vào nhân thân ... và các tình tiết giảm nhẹ\")"),
    Case("Tình tiết khoản 2 Điều 51", "171", "1", {"mitigating": [S, {"khoan": "2", "diem": "", "fact_ids": ["F2"]}]},
         "warn", "mitigating_other_reason", 'Đ51 k2 BLHS: "phải ghi rõ lý do giảm nhẹ trong bản án"'),
)
PREVENTIVE = {"Án treo không nêu tình tiết giảm nhẹ": "tạm giam"}


def outcome_new(case: Case) -> tuple[str, set[str], set[str]]:
    file = case_file(case.crime, case.charged, PREVENTIVE.get(case.name))
    result = check_verdict(base_verdict(case.crime, case.charged, case.verdict), file, pack_for(f"blhs_{case.crime}"))
    hard, soft = {f.code for f in result.hard}, {f.code for f in result.soft}
    return ("block" if hard else "warn" if soft else "pass"), hard, soft


def blocks_old(case: Case) -> bool:
    file = case_file(case.crime, case.charged, PREVENTIVE.get(case.name))
    return bool(legacy.check_verdict(base_verdict(case.crime, case.charged, case.verdict), file,
                                     pack_for(f"blhs_{case.crime}")).errors)


def table_report() -> dict:
    """Numbers for the nhóm B report: totals, wrong outcomes per guard, outcomes that moved."""
    old_wrong, new_wrong, changed = [], [], []
    for case in TABLE:
        new, _, _ = outcome_new(case)
        old_block, should_block = blocks_old(case), case.expected == "block"
        if old_block != should_block:
            old_wrong.append(case.name)
        if new != case.expected:
            new_wrong.append(case.name)
        if old_block != (new == "block"):
            changed.append((case.name, case.code, "block->" + new if old_block else "pass->" + new, case.basis))
    return {"total": len(TABLE), "old_wrong": old_wrong, "new_wrong": new_wrong, "changed": changed}


class GuardTableTests(unittest.TestCase):
    def test_table_size_and_scope(self):
        self.assertGreaterEqual(len(TABLE), 30)
        self.assertEqual({c.crime for c in TABLE}, {"134", "171", "173", "174"})
        self.assertEqual({c.charged for c in TABLE}, {"1", "2"})
        self.assertTrue(all(c.basis for c in TABLE))

    def test_new_guard_gets_every_case_right(self):
        for case in TABLE:
            with self.subTest(case.name):
                outcome, hard, soft = outcome_new(case)
                self.assertEqual(outcome, case.expected, (hard, soft))
                if case.code:
                    self.assertIn(case.code, hard if case.expected == "block" else soft)

    def test_previously_wrong_cases_are_the_ones_that_moved(self):
        report = table_report()
        self.assertEqual(report["new_wrong"], [])
        flagged = {c.name for c in TABLE if c.group}
        self.assertEqual(set(report["old_wrong"]), flagged)
        self.assertEqual({name for name, *_ in report["changed"]}, flagged)

    def test_soft_findings_never_block_the_ai_decision(self):
        for case in (c for c in TABLE if c.expected == "warn"):
            with self.subTest(case.name):
                self.assertEqual(outcome_new(case)[1], set())


def verdict_json(**overrides) -> str:
    return base_verdict("173", "1", overrides).model_dump_json()


class VerdictWiringTests(unittest.TestCase):
    """The turn service: hard findings regenerate (codes logged, basis in the feedback), soft ones are
    logged on an accepted call, and the code-computed constraints reach the nghị án prompt."""

    def _ctx(self, answers: list[str]):
        from tests.test_trial_defendant import at
        from tests.test_trial_observer import _ctx
        return at(_ctx("nguoi_xem", answers=answers), "nghi_an")

    def test_hard_finding_regenerates_with_codes_and_basis(self):
        ctx = self._ctx([verdict_json(penalty_months=2, applies_dieu_54=True, mitigating=TWO), verdict_json()])
        asyncio.run(_deliberate(ctx))
        first, second = ctx.recorder.records
        self.assertEqual((first.accepted, first.guard_violations), (False, ["verdict:prison_general_range"]))
        self.assertTrue(second.accepted)
        self.assertIn("khoản 1 Điều 38 Bộ luật Hình sự", ctx.recorder.prompts[1])
        self.assertEqual(ctx.verdict.penalty_months, 12)

    def test_soft_finding_is_logged_not_rejected(self):
        ctx = self._ctx([verdict_json(civil_amount_vnd=9_000_000)])
        asyncio.run(_deliberate(ctx))
        (record,) = ctx.recorder.records
        self.assertTrue(record.accepted)
        self.assertEqual(record.guard_violations, ["soft:civil_over_claim"])
        self.assertEqual(ctx.verdict_flags, [])

    def test_two_hard_failures_pause_with_codes(self):
        bad = verdict_json(penalty_months=40)
        ctx = self._ctx([bad, bad])
        with self.assertRaises(TrialGuardFailure) as raised:
            asyncio.run(_deliberate(ctx))
        self.assertEqual(raised.exception.violations, ["verdict:above_frame"])

    def test_constraints_reach_the_prompt(self):
        ctx = self._ctx([verdict_json()])
        asyncio.run(_deliberate(ctx))
        self.assertIn("RÀNG BUỘC CỨNG CỦA VỤ ÁN NÀY", ctx.recorder.prompts[0])

    def test_constraints_text_per_frame(self):
        text = hard_constraints_text(case_file("174", "2"), pack_for("blhs_174"))
        self.assertIn("phạt tù từ 24 tháng đến 84 tháng", text)
        self.assertIn("phạt tù không dưới 6 tháng, hoặc cải tạo không giam giữ", text)   # Điều 54 khoản 1
        self.assertNotIn("khung nhẹ nhất", text)
        lightest = hard_constraints_text(case_file("171", "1"), pack_for("blhs_171"))
        self.assertIn("phạt tù từ 12 tháng đến 60 tháng.", lightest)
        self.assertIn("khoản 3 Điều 54", lightest)
        heavy = hard_constraints_text(case_file("171", "2"), pack_for("blhs_171"))
        self.assertIn("không được phạt cải tạo không giam giữ", heavy)
        self.assertNotIn("hoặc cải tạo không giam giữ (khoản 1 Điều 54", heavy)

    def test_every_rule_code_has_a_severity(self):
        self.assertTrue(set(RULES.values()) <= {"hard", "soft"})
        self.assertEqual(RULES["khoan_heavier"], "soft")
        self.assertEqual(RULES["civil_over_claim"], "soft")
        self.assertEqual(RULES["circumstance_unknown"], "hard")


if __name__ == "__main__":
    unittest.main()
