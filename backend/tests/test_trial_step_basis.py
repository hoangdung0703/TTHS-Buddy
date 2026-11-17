"""Step legal_basis (nhóm B, design doc Mục 11.16.2): StepSpec.legal_basis is shown in the step list
and must hold every Điều of the verified procedure note of that step; the legal text the AI calls of
that step load (and Rule 9 checks against) must hold every Điều of both. A step whose basis is not in
its slice makes Rule 9 reject a correct citation. No Gemini call."""
from __future__ import annotations

import unittest

from app.services.trial_config import BLTTHS_DOCUMENT
from app.services.trial_procedure_notes import PROCEDURE_NOTES
from app.services.trial_rule9 import check_citations
from app.services.trial_state_machine import STEPS, CaseShape, active_slots
from app.services.trial_turn_service import context_pack
from tests.test_trial_defendant import at
from tests.test_trial_observer import _ctx
from tests.trial_fixtures import pack_for

SHAPE = CaseShape(victim_present=True, witness_count=1, has_related_party=True)
ROLES = ("ksv", "luat_su", "nguoi_xem", "thu_ky", "bi_cao")


def step_slice(step: int) -> set[str]:
    """BLTTHS Điều numbers loaded by any slot of `step`, for any role."""
    pack = pack_for("blhs_173")
    keys = {slot.key for role in ROLES for slot in active_slots(step, SHAPE, role)}
    return {a.dieu_number for key in keys for a in pack.slice_for_slot(key, step, "173")
            if a.source_document == BLTTHS_DOCUMENT}


class StepBasisTests(unittest.TestCase):
    def test_step_basis_holds_the_verified_note_basis(self):
        for step in STEPS:
            with self.subTest(step=step.number):
                self.assertLessEqual(set(PROCEDURE_NOTES[step.number].legal_basis), set(step.legal_basis))

    def test_step_basis_is_in_the_slice_the_step_loads(self):
        for step in STEPS:
            with self.subTest(step=step.number):
                self.assertLessEqual(set(step.legal_basis), step_slice(step.number))

    def test_every_basis_article_is_in_the_pack(self):
        pack = pack_for("blhs_173")
        for step in STEPS:
            for dieu in step.legal_basis:
                self.assertIsNotNone(pack.get(BLTTHS_DOCUMENT, dieu), (step.number, dieu))

    def test_luan_toi_may_cite_dieu_325(self):
        # Rút quyết định truy tố / kết luận về tội nhẹ hơn: rejected by Rule 9 before nhóm B.
        ctx = at(_ctx("nguoi_xem"), "luan_toi")
        text = "Căn cứ Điều 325 Bộ luật Tố tụng hình sự, Viện kiểm sát kết luận về tội nhẹ hơn."
        self.assertEqual(check_citations(text, context_pack(ctx, "luan_toi"), "lenient"), [])


if __name__ == "__main__":
    unittest.main()
