"""Route tests for the Bị cáo role (chặng R3): a whole hearing through /turn with the đoạn xen,
"decline", the optional turns, the pending question after a reload, the role card only in this
role, and the 409s. Fake model and in-memory repository - no Gemini, no Supabase."""
from __future__ import annotations

import json
import unittest

from tests import test_trial_routes as routes   # module, not the class: its tests must not run twice here

from app.services.trial_defendant import DECLINE_TEXT, OPT_OUT_TEXTS, ROLE_BRIEF_NOTE

ANSWER = "Dạ, tôi xin trình bày như sau."


class DefendantRouteTests(unittest.TestCase):
    setUp = routes.TrialRouteTests.setUp
    tearDown = routes.TrialRouteTests.tearDown
    create = routes.TrialRouteTests.create
    turn = routes.TrialRouteTests.turn
    act = routes.TrialRouteTests.act

    def code(self, response) -> str:
        self.assertEqual(response.status_code, 409, response.text)
        return response.json()["error"]["code"]

    def play(self, sid, state, *, decline_once=True, debate=True) -> dict:
        declined = False
        while state["status"] == "active":
            actions = state["allowed_actions"]
            question = state["pending_question"]
            if actions == ["continue"]:
                state, _ = self.act(sid, state, "continue")
            elif actions and actions[0].startswith("advance:"):
                self.assertIsNone(question)
                state, _ = self.act(sid, state, "advance", target_step=state["current_step"] + 1)
            elif question is not None:
                if "decline" in actions and decline_once and not declined:
                    state, _ = self.act(sid, state, "decline")
                    declined = True
                else:
                    state, _ = self.act(sid, state, "speak", text=question["prefill"] or ANSWER)
            elif state["current_step"] == 8 and debate and "speak" in actions:
                state, _ = self.act(sid, state, "speak", text="Tôi xin Hội đồng xét xử xem xét hoàn cảnh của tôi.")
            else:
                self.assertEqual(actions, ["speak", "end_slot"])
                state, _ = self.act(sid, state, "end_slot")
        return state

    def test_full_hearing_with_a_refusal_and_the_record(self):
        sid, state = self.create(role="bi_cao")
        state = self.play(sid, state)
        self.assertEqual(state["status"], "completed")
        rows = [r for r in self.repo.utterances if r["session_id"] == sid]
        user = [r for r in rows if r["is_user"]]
        self.assertEqual(sum(r["content"] == DECLINE_TEXT for r in user), 1)
        self.assertIn(OPT_OUT_TEXTS["bi_cao_bo_sung_bao_chua"], [r["content"] for r in user])
        # every AI utterance comes from someone else: the student's id is never an AI speaker
        self.assertEqual([r for r in rows if r["speaker_id"] == "BI_CAO" and not r["is_user"]], [])
        questions = [r for r in rows if "student_question" in r["guard_flags"]]
        self.assertEqual(len(questions), 2 + 4 + 3 + 3 + 1)            # every cap, the fake always asks
        self.assertEqual(self.fake.calls.count("record_summary"), 1)    # IV.2/IV.3 summarised as for KSV
        record = self.client.get(f"/api/trials/{sid}/record").json()
        last_words = record["record"]["sections"][3]["subsections"][3]
        self.assertEqual(last_words["content"], "verbatim")
        self.assertIn(ANSWER, [e["text"] for e in last_words["entries"]])
        self.assertNotIn("user_amount_off_file", record["text"])

    def test_role_card_only_in_a_defendant_session(self):
        sid, _ = self.create(role="bi_cao")
        body = self.client.get(f"/api/trials/{sid}").json()
        self.client.post(f"/api/trials/{sid}/abandon")
        self.assertEqual(body["role_brief"]["note"], ROLE_BRIEF_NOTE)
        self.assertEqual(body["role_brief"]["stance"], "nhận tội, xin giảm nhẹ")
        dumped = json.dumps(body, ensure_ascii=False)
        for hidden in ("yêu cầu bồi thường", "chứng kiến một phần", "defendant_plea", "verdict", "guilty"):
            self.assertNotIn(hidden, dumped)
        for person in ("defendant", "victim"):                            # the panel still hides every card
            self.assertNotIn("stance", body["case_file"][person])
        for role in ("ksv", "luat_su", "nguoi_xem", "thu_ky"):
            other, _ = self.create(role=role)
            response = self.client.get(f"/api/trials/{other}")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('"role_brief"', response.text, role)
            self.assertNotIn('"stance"', response.text, role)
            self.assertIsNone(response.json()["state"]["pending_question"], role)
            self.client.post(f"/api/trials/{other}/abandon")              # stay under 3 active sessions

    def test_pending_question_survives_a_reload(self):
        sid, state = self.create(role="bi_cao")
        state, _ = self.act(sid, state, "advance", target_step=2)
        question = state["pending_question"]
        self.assertEqual((question["speaker_id"], state["allowed_actions"], state["text_limits"]),
                         ("CHU_TOA", ["speak"], {"min": 1, "max": 1500}))
        self.assertIn(self.client.get(f"/api/trials/{sid}").json()["participants"]["BI_CAO"]["name"],
                      question["prefill"])
        self.assertIsNone(question["decline_note"])
        reloaded = self.client.get(f"/api/trials/{sid}").json()
        self.assertEqual(reloaded["state"]["pending_question"], question)
        self.assertEqual(reloaded["utterances"][-1]["seq"], question["seq"])
        state, _ = self.act(sid, state, "speak", text=question["prefill"])
        self.assertIsNone(state["pending_question"]["prefill"])         # second question: no prefill

    def test_conflicts(self):
        sid, state = self.create(role="bi_cao")
        state, _ = self.act(sid, state, "advance", target_step=2)
        self.assertEqual(self.code(self.turn(sid, state, "decline")), "trial_action_not_allowed")
        self.assertEqual(self.code(self.turn(sid, state, "end_slot")), "trial_action_not_allowed")
        self.assertEqual(self.code(self.turn(sid, state, "speak")), "trial_empty_text")
        self.assertEqual(self.code(self.turn(sid, state, "speak", text="x" * 1501)), "trial_text_too_long")
        self.assertEqual(self.turn(sid, state, "speak", text="x" * 6001).status_code, 422)
        self.assertEqual(self.code(self.turn(sid, dict(state, version=state["version"] - 1), "speak", text="Dạ.")),
                         "trial_version_mismatch")
        self.assertEqual(self.code(self.turn(sid, dict(state, current_step=4), "speak", text="Dạ.")),
                         "trial_step_mismatch")
        self.assertEqual(self.code(self.turn(sid, state, "advance", target_step=3)), "trial_slot_not_finished")
        calls = len(self.fake.calls)
        self.assertEqual(self.code(self.turn(sid, state, "continue")), "trial_not_ai_turn")
        self.assertEqual(len(self.fake.calls), calls)
        state, _ = self.act(sid, state, "speak", text=ANSWER)           # still accepted afterwards

    def test_ai_speaking_as_the_defendant_pauses_and_breaker_holds(self):
        sid, state = self.create(role="bi_cao")
        bad = json.dumps({"utterances": [{"speaker_id": "BI_CAO", "text": "Tôi xin nhận tội."}], "new_facts": [],
                          "cau_hoi_cho_nguoi_hoc": None}, ensure_ascii=False)
        self.fake.bad["dialogue"] = [bad] * 6
        state, events = self.act(sid, state, "advance", target_step=2)
        self.assertNotIn("BI_CAO", [d["speaker_id"] for e, d in events if e == "utterance"])
        self.assertEqual(state["allowed_actions"], ["continue"])
        state, _ = self.act(sid, state, "continue")
        state, _ = self.act(sid, state, "continue")
        self.assertEqual(state["allowed_actions"], [])
        self.assertEqual(self.code(self.turn(sid, state, "continue")), "trial_guard_exhausted")

    def test_decline_route_records_the_fixed_sentence_with_no_model_call(self):
        sid, state = self.create(role="bi_cao")
        while state["current_step"] < 4 or state["pending_question"] is None:
            if state["pending_question"] is not None:
                state, _ = self.act(sid, state, "speak", text=state["pending_question"]["prefill"] or ANSWER)
            else:
                state, _ = self.act(sid, state, "advance", target_step=state["current_step"] + 1)
        self.assertEqual(state["allowed_actions"], ["speak", "decline"])
        self.assertIn("điểm h khoản 2 Điều 61 Bộ luật Tố tụng hình sự",
                      state["pending_question"]["decline_note"]["legal_basis"])
        before = state["pending_question"]["seq"]
        calls = len(self.fake.calls)
        state, events = self.act(sid, state, "decline")
        first = next(d for e, d in events if e == "utterance")
        self.assertEqual((first["speaker_id"], first["is_user"], first["kind"], first["text"]),
                         ("BI_CAO", True, "procedural", DECLINE_TEXT))
        self.assertEqual(len(self.fake.calls), calls + 1)               # only the AI's next question
        self.assertGreater(state["pending_question"]["seq"], before)
        self.assertNotIn("guard_pause", json.dumps(events))


if __name__ == "__main__":
    unittest.main()
