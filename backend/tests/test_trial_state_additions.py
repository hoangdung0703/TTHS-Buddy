"""Fields added to the trial state without changing any existing one: presiding.items[].blocked_reason,
presiding.catalogue / return_catalogue, final_statement_done (Chủ tọa, Bị cáo) and invitation (Bị cáo).
Pure state tests plus whole hearings through the routes with the fake model - no Gemini, no Supabase."""
from __future__ import annotations

import itertools
import json
import unittest
from dataclasses import replace

from tests import test_trial_routes as routes   # module, not the class: its tests must not run twice here
from tests.test_trial_defendant_routes import ANSWER
from tests.test_trial_presiding import ABSENT, SHAPE, act, at_step
from tests import test_trial_presiding_routes as chair_routes   # module: its tests must not run twice

from app.services import trial_presiding
from app.services.trial_presiding import (
    BLOCKED_TEXTS,
    RETURN_ITEMS,
    STEP_ITEMS,
    blocked_reason,
    catalogue,
    complete_job,
    is_available,
    items_for,
    return_catalogue,
)
from app.services.trial_session_service import final_statement_done
from app.services.trial_state_machine import PresideJob, new_session

HIDDEN_KEYS = ('"verdict_json"', '"verdict"', '"guilty"', '"penalty_months"', '"defendant_plea"', '"stance"')


def reason(state, key):
    return blocked_reason(state, next(i for i in items_for(state) if i.key == key))


class BlockedReasonTests(unittest.TestCase):
    def test_none_exactly_when_available_in_every_reachable_combination(self):
        """The reason mirrors awaiting_user + is_available; it never decides on its own."""
        checked = 0
        for step, shape in itertools.product(range(2, 12), (SHAPE, ABSENT)):
            for in_return in ((False, True) if step == 5 else (False,)):
                base = at_step(step, shape, in_return=in_return, returned=in_return)
                keys = [i.key for i in items_for(base)]
                for size in range(len(keys) + 1):
                    for done in itertools.combinations(keys, size):
                        for questions, rounds, decided, pending, status in itertools.product(
                                (0, 10), (0, 1), (False, True), (False, True), ("active", "completed")):
                            preside = replace(base.preside, done=done, questions=questions, rounds=rounds,
                                              decided=decided)
                            state = replace(base, preside=preside, pending_ai=pending, status=status)
                            for item in items_for(state):
                                available = (status == "active" and not pending and is_available(state, item))
                                why = blocked_reason(state, item)
                                self.assertEqual(why is None, available, (step, done, item.key, why))
                                if why is not None:
                                    self.assertIn(why["code"], BLOCKED_TEXTS)
                                    self.assertTrue(why["text"])
                                checked += 1
        self.assertGreater(checked, 10000)

    def test_codes_prerequisites_and_texts(self):
        fresh = at_step(2)
        self.assertIsNone(reason(fresh, "khai_mac"))
        self.assertEqual(reason(fresh, "kiem_tra_can_cuoc"),
                         {"code": "prerequisite_missing", "prerequisite_item": "khai_mac",
                          "text": "Cần làm trước: Khai mạc, đọc quyết định đưa vụ án ra xét xử."})
        self.assertEqual(reason(at_step(2, done=("khai_mac",)), "khai_mac"),
                         {"code": "already_done", "prerequisite_item": None, "text": "Mục này đã làm."})
        self.assertEqual(reason(at_step(5), "ket_thuc_xet_hoi")["prerequisite_item"], "moi_ksv_hoi")
        step8 = at_step(8)
        self.assertEqual(reason(step8, "vong_2")["prerequisite_item"], "moi_doi_dap")
        self.assertEqual(reason(step8, "tro_lai_xet_hoi")["prerequisite_item"], "moi_doi_dap")
        self.assertEqual(reason(at_step(8, done=("moi_doi_dap",)), "tro_lai_xet_hoi")["prerequisite_item"],
                         "moi_doi_dap")                                 # invited, but no whole round yet
        self.assertIsNone(reason(at_step(8, done=("moi_doi_dap",), rounds=1), "tro_lai_xet_hoi"))
        self.assertEqual(reason(at_step(8, done=("moi_doi_dap", "ket_thuc_tranh_luan"), rounds=1),
                                "tro_lai_xet_hoi")["code"], "debate_closed")
        self.assertEqual(reason(at_step(4, questions=10), "hoi_bi_cao")["code"], "limit_reached")
        self.assertEqual(reason(at_step(10, done=("vao_nghi_an", "chot_quyet_dinh"), decided=True),
                                "y_kien_hoi_tham")["code"], "decision_locked")
        self.assertEqual(reason(at_step(11), "tuyen_an"),     # a step-10 item named from step 11
                         {"code": "prerequisite_missing", "prerequisite_item": "chot_quyet_dinh",
                          "text": "Cần làm trước: Chốt quyết định."})
        self.assertEqual(reason(replace(fresh, pending_ai=True), "khai_mac")["code"], "ai_running")
        self.assertEqual(reason(replace(fresh, status="abandoned"), "khai_mac")["code"], "closed")

    def test_return_step_names_its_own_labels(self):
        state = at_step(5, in_return=True, returned=True)
        self.assertEqual(reason(state, "ket_thuc_xet_hoi"), None)     # nothing required before it
        self.assertEqual([i.key for i in items_for(state)], [i.key for i in RETURN_ITEMS])


class CatalogueTests(unittest.TestCase):
    def test_every_item_of_steps_2_to_9_with_its_step_and_the_same_label(self):
        cat = catalogue()
        for step in range(2, 10):
            for item in STEP_ITEMS[step]:
                self.assertEqual(cat[item.key], {"step": step, "label": item.label})
        self.assertEqual(len(cat), sum(len(items) for items in STEP_ITEMS.values()))   # keys unique across steps
        self.assertEqual(cat["tuyen_an"]["step"], 11)
        self.assertEqual(return_catalogue()["hoi_lai"], {"step": 5, "label": "Hỏi lại (tối đa 3 câu)"})
        self.assertEqual(return_catalogue()["moi_ksv_hoi"]["label"], "Mời Kiểm sát viên hỏi (tối đa 3 câu)")


class FinalStatementStateTests(unittest.TestCase):
    def test_chair_flag_follows_the_stored_last_words(self):
        state = at_step(9)
        self.assertFalse(final_statement_done(state))
        invited = act(state, "invite", item="moi_loi_sau_cung")
        self.assertEqual(invited.preside.job, PresideJob("invite", "moi_loi_sau_cung"))
        self.assertFalse(final_statement_done(invited))                # the AI defendant has not spoken yet
        spoken = complete_job(invited)
        self.assertTrue(final_statement_done(spoken))
        self.assertTrue(final_statement_done(act(spoken, "advance", target_step=10)))
        self.assertFalse(final_statement_done(at_step(8, done=("moi_doi_dap", "ket_thuc_tranh_luan"))))
        self.assertTrue(trial_presiding.final_statement_done(at_step(11)))

    def test_other_roles_have_no_flag(self):
        for role in ("ksv", "luat_su", "nguoi_xem", "thu_ky"):
            self.assertIsNone(final_statement_done(new_session(role, SHAPE)), role)
        self.assertIs(final_statement_done(new_session("bi_cao", SHAPE)), False)


class DefendantRouteAdditionTests(unittest.TestCase):
    setUp = routes.TrialRouteTests.setUp
    tearDown = routes.TrialRouteTests.tearDown
    create = routes.TrialRouteTests.create
    turn = routes.TrialRouteTests.turn
    act = routes.TrialRouteTests.act

    def test_invitation_and_final_statement_through_a_whole_hearing(self):
        sid, state = self.create(role="bi_cao")
        seen_steps = []
        while state["status"] == "active":
            dumped = json.dumps(state, ensure_ascii=False)
            for hidden in HIDDEN_KEYS:
                self.assertNotIn(hidden, dumped)
            actions, step = state["allowed_actions"], state["current_step"]
            invitation = state["invitation"]
            self.assertIs(state["final_statement_done"], step > 9 or (step == 9 and actions[:1] == ["advance:10"]))
            if invitation is not None:
                seen_steps.append(step)
                stored = self.client.get(f"/api/trials/{sid}").json()
                line = next(u for u in stored["utterances"] if u["seq"] == invitation["seq"])
                self.assertEqual({k: line[k] for k in invitation}, invitation)   # the very line in the transcript
                self.assertEqual((line["speaker_id"], line["step"], line["is_user"]), ("CHU_TOA", step, False))
                self.assertEqual(stored["state"]["invitation"], invitation)       # same after a reload
                self.assertNotIn("{", invitation["text"])                         # names rendered
            if actions == ["continue"]:
                state, _ = self.act(sid, state, "continue")
            elif actions[0].startswith("advance:"):
                self.assertIsNone(invitation)
                state, _ = self.act(sid, state, "advance", target_step=step + 1)
            elif state["pending_question"] is not None:
                if step == 9:
                    question = state["pending_question"]
                    self.assertEqual(invitation, {k: question[k] for k in invitation})
                else:
                    self.assertIsNone(invitation, step)
                state, _ = self.act(sid, state, "speak", text=state["pending_question"]["prefill"] or ANSWER)
            else:
                self.assertIn(step, (7, 8))
                self.assertIsNotNone(invitation)
                state, _ = self.act(sid, state, "end_slot")
        self.assertEqual(seen_steps, [7, 8, 9])
        self.assertEqual((state["status"], state["final_statement_done"], state["invitation"]),
                         ("completed", True, None))

    def test_after_speaking_at_step_8_the_invitation_is_gone(self):
        sid, state = self.create(role="bi_cao")
        while not (state["current_step"] == 8 and state["invitation"] is not None):
            actions = state["allowed_actions"]
            if actions[0].startswith("advance:"):
                state, _ = self.act(sid, state, "advance", target_step=state["current_step"] + 1)
            elif state["pending_question"] is not None:
                state, _ = self.act(sid, state, "speak", text=state["pending_question"]["prefill"] or ANSWER)
            else:
                state, _ = self.act(sid, state, "end_slot")
        self.assertIs(state["final_statement_done"], False)
        state, _ = self.act(sid, state, "speak", text="Tôi xin Hội đồng xét xử xem xét hoàn cảnh của tôi.")
        self.assertIsNone(state["invitation"])

    def test_other_roles_keep_null_fields(self):
        for role in ("ksv", "luat_su", "nguoi_xem", "thu_ky"):
            self.repo._usage_rows().clear()
            sid, state = self.create(role=role)
            state, _ = self.act(sid, state, "advance", target_step=2) if role != "thu_ky" else (state, None)
            body = self.client.get(f"/api/trials/{sid}").json()
            self.client.post(f"/api/trials/{sid}/abandon")
            for shown in (state, body["state"]):
                self.assertIsNone(shown["final_statement_done"], role)
                self.assertIsNone(shown["invitation"], role)
                self.assertIsNone(shown["presiding"], role)


class ChairRouteAdditionTests(unittest.TestCase):
    setUp = chair_routes.PresidingRouteTests.setUp
    tearDown = chair_routes.PresidingRouteTests.tearDown
    create = chair_routes.PresidingRouteTests.create
    act = chair_routes.PresidingRouteTests.act
    turn = chair_routes.PresidingRouteTests.turn
    put_decision = chair_routes.PresidingRouteTests.put_decision
    item = chair_routes.PresidingRouteTests.item
    do = chair_routes.PresidingRouteTests.do
    play = chair_routes.PresidingRouteTests.play
    _to_step = chair_routes.PresidingRouteTests._to_step

    def test_blocked_reason_catalogue_and_final_statement_in_the_state(self):
        sid, state = self.create(role="chu_toa")
        self.assertIsNone(state["presiding"])                            # step 1: no checklist, as before
        self.assertIs(state["final_statement_done"], False)
        self.assertIsNone(state["invitation"])
        state, _ = self.act(sid, state, "advance", target_step=2)
        presiding = state["presiding"]
        self.assertEqual(presiding["catalogue"], catalogue())
        self.assertEqual(presiding["return_catalogue"], return_catalogue())
        for shown in presiding["items"]:
            self.assertEqual(shown["blocked_reason"] is None, shown["available"], shown["key"])
        self.assertEqual(self.item(state, "hoi_thay_doi")["blocked_reason"]["prerequisite_item"], "khai_mac")
        state = self.do(sid, state, "khai_mac")
        self.assertEqual(self.item(state, "khai_mac")["blocked_reason"]["code"], "already_done")
        self.assertIsNone(self.item(state, "hoi_thay_doi")["blocked_reason"])

        state = self._to_step(sid, state, 9)
        self.assertIs(state["final_statement_done"], False)
        state = self.do(sid, state, "moi_loi_sau_cung")
        self.assertIs(state["final_statement_done"], True)
        body = self.client.get(f"/api/trials/{sid}").json()
        self.assertIs(body["state"]["final_statement_done"], True)
        self.assertEqual(self.item(body["state"], "moi_loi_sau_cung")["blocked_reason"]["code"], "already_done")
        state = self.play(sid, state)
        self.assertEqual((state["status"], state["final_statement_done"]), ("completed", True))
        dumped = json.dumps(self.client.get(f"/api/trials/{sid}").json(), ensure_ascii=False)
        for hidden in ('"verdict_json"', '"defendant_plea"', '"stance"', '"source"'):
            self.assertNotIn(hidden, dumped)


if __name__ == "__main__":
    unittest.main()
