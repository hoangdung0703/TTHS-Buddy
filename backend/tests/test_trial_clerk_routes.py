"""Route tests for the Thư ký role (chặng R2): the step-1 report, notes, the biên bản draft and its
finalisation. Fake model and in-memory repository - no Gemini, no Supabase."""
from __future__ import annotations

import json
import unittest

from tests import test_trial_routes as routes   # module, not the class: its tests must not run twice here

from app.services import trial_metrics
from app.services.trial_record import CLERK_AUTHOR_NOTE, DRAFT_NOTE

MARKER = "GHICHU-RIENG-7f3a"
IV2 = ("Chủ tọa hỏi bị cáo về diễn biến vụ án; bị cáo khai nhận hành vi như cáo trạng. Kiểm sát viên hỏi về việc "
       "khắc phục hậu quả; bị cáo trình bày đã xin lỗi bị hại. Luật sư hỏi về hoàn cảnh gia đình của bị cáo.")
IV3 = ("Kiểm sát viên trình bày luận tội, đề nghị Hội đồng xét xử tuyên bị cáo phạm tội như cáo trạng. Luật sư bào "
       "chữa, đề nghị xem xét các tình tiết giảm nhẹ. Hai bên đối đáp về các tình tiết giảm nhẹ trong hồ sơ.")


class _RecordingModel(routes.FakeModel):
    def __init__(self):
        super().__init__()
        self.prompts: list[str] = []

    def __call__(self, system_prompt, user_prompt, *args, **kwargs):
        self.prompts.append(system_prompt + "\n" + user_prompt)
        return super().__call__(system_prompt, user_prompt, *args, **kwargs)


class ClerkRouteTests(unittest.TestCase):
    tearDown = routes.TrialRouteTests.tearDown
    create = routes.TrialRouteTests.create
    turn = routes.TrialRouteTests.turn
    act = routes.TrialRouteTests.act

    def setUp(self):
        routes.TrialRouteTests.setUp(self)
        self.fake = _RecordingModel()
        trial_metrics.generate_json_with_usage = self.fake

    def report(self, sid, state) -> dict:
        self.assertEqual(state["allowed_actions"], ["speak"])
        state, _ = self.act(sid, state, "speak", text=state["clerk_report"]["prefill"])
        return state

    def play(self, sid, state, until_step: int | None = None) -> dict:
        while state["status"] == "active":
            actions = state["allowed_actions"]
            if actions == ["speak"]:
                state = self.report(sid, state)
            elif actions == ["continue"]:
                state, _ = self.act(sid, state, "continue")
            else:
                self.assertEqual(actions, [f"advance:{state['current_step'] + 1}"])
                if until_step is not None and state["current_step"] + 1 == until_step:
                    return state
                state, _ = self.act(sid, state, "advance", target_step=state["current_step"] + 1)
        return state

    def code(self, response) -> str:
        return response.json()["error"]["code"]

    def test_creation_waits_for_the_clerks_report(self):
        sid, state = self.create(role="thu_ky")
        self.assertEqual(self.fake.calls, [])   # step 1 is the student's: no model call at creation
        self.assertEqual((state["current_step"], state["awaiting"], state["allowed_actions"]), (1, "user", ["speak"]))
        self.assertEqual(state["text_limits"], {"min": 100, "max": 3000})
        detail = self.client.get(f"/api/trials/{sid}").json()
        self.assertEqual(detail["utterances"], [])
        self.assertIn(detail["participants"]["BI_CAO"]["name"], state["clerk_report"]["prefill"])
        self.assertEqual(state["clerk_prompt"]["step"], 1)
        self.assertFalse(state["clerk_prompt"]["reviewed"])
        dumped = json.dumps(detail, ensure_ascii=False)
        for hidden in ("role_brief", "stance", "knowledge", "demeanor", "verdict", "user_work", "notes"):
            self.assertNotIn(f'"{hidden}"', dumped)
        too_short = self.turn(sid, state, "speak", text="Đủ cả.")
        self.assertEqual((too_short.status_code, self.code(too_short)), (409, "trial_text_too_short"))
        stale = self.client.post(f"/api/trials/{sid}/turn", json={"expected_step": 1, "expected_version": 99,
                                                                 "action": "speak", "text": "x" * 200})
        self.assertEqual(self.code(stale), "trial_version_mismatch")
        silent = self.turn(sid, state, "continue")
        self.assertEqual(self.code(silent), "trial_not_ai_turn")
        jump = self.turn(sid, state, "advance", target_step=2)
        self.assertEqual(self.code(jump), "trial_slot_not_finished")
        state = self.report(sid, state)
        self.assertEqual(state["allowed_actions"], ["advance:2"])
        self.assertIsNone(state["clerk_report"])
        first = self.client.get(f"/api/trials/{sid}").json()["utterances"][0]
        self.assertEqual((first["speaker_id"], first["is_user"]), ("THU_KY", True))

    def test_full_hearing_makes_no_summary_call_and_notes_stay_out_of_everything(self):
        sid, state = self.create(role="thu_ky")
        state = self.report(sid, state)
        version = state["version"]
        saved = self.client.put(f"/api/trials/{sid}/notes", json={"text": f"{MARKER} bị cáo khai\r\nnhận tội"})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["notes"], f"{MARKER} bị cáo khai\nnhận tội")
        self.assertEqual(self.repo.sessions[sid]["version"], version)   # notes never touch the state
        state = self.play(sid, state)
        self.assertEqual(state["status"], "completed")
        self.assertNotIn("record_summary", self.fake.calls)
        self.assertNotIn(routes.trials_api.RECORD_STATUS_TEXT,
                         [d["message"] for e, d in self.last_events if e == "status"])
        self.assertEqual(self.fake.calls.count("verdict"), 1)
        self.assertTrue(self.fake.prompts)
        self.assertFalse(any(MARKER in p for p in self.fake.prompts))
        self.assertTrue(any("Người học đang đóng vai Thư ký ({THU_KY})" in p for p in self.fake.prompts))
        for path in ("", f"/{sid}", f"/{sid}/record"):
            self.assertNotIn(MARKER, self.client.get(f"/api/trials{path}").text, path)
        self.assertEqual(self.client.get(f"/api/trials/{sid}/notes").json()["notes"],
                         f"{MARKER} bị cáo khai\nnhận tội")
        self.assertIsNone(self.repo.sessions[sid]["verdict_json"].get("record_summary"))

    def test_notes_rules(self):
        ksv_sid, _ = self.create(role="ksv")
        refused = self.client.put(f"/api/trials/{ksv_sid}/notes", json={"text": "x"})
        self.assertEqual((refused.status_code, self.code(refused)), (409, "trial_not_clerk"))
        self.assertEqual(self.code(self.client.get(f"/api/trials/{ksv_sid}/notes")), "trial_not_clerk")
        sid, state = self.create(role="thu_ky")
        self.assertEqual(self.client.get(f"/api/trials/{sid}/notes").json(),
                         {"notes": "", "updated_at": None, "max_chars": 20000})
        too_long = self.client.put(f"/api/trials/{sid}/notes", json={"text": "x" * 20001})
        self.assertEqual(too_long.status_code, 422)
        self.assertEqual(self.client.put(f"/api/trials/{sid}/notes", json={"text": "x" * 20000}).status_code, 200)
        self.assertEqual(self.client.put(f"/api/trials/{sid}/notes", json={"text": ""}).json()["notes"], "")
        self.repo.sessions[sid]["user_id"] = "22222222-2222-2222-2222-222222222222"    # someone else's
        self.assertEqual(self.client.put(f"/api/trials/{sid}/notes", json={"text": "x"}).status_code, 404)
        self.assertEqual(self.client.get(f"/api/trials/{sid}/notes").status_code, 404)
        self.repo.sessions[sid]["user_id"] = self.user
        self.client.post(f"/api/trials/{sid}/abandon")
        abandoned = self.client.put(f"/api/trials/{sid}/notes", json={"text": "x"})
        self.assertEqual(self.code(abandoned), "trial_not_active")

    def test_draft_review_and_finalise(self):
        sid, state = self.create(role="thu_ky")
        for path, method in ((f"/{sid}/record/draft", "put"), (f"/{sid}/record/finalize", "post")):
            early = getattr(self.client, method)(f"/api/trials{path}", json={"iv2": IV2})
            self.assertEqual((early.status_code, self.code(early)), (409, "trial_not_completed"))
        state = self.play(sid, state)
        calls = len(self.fake.calls)

        record = self.client.get(f"/api/trials/{sid}/record").json()
        self.assertTrue(record["record"]["draft"])
        self.assertEqual(record["record"]["preamble"], [DRAFT_NOTE])
        items = record["record"]["sections"][3]["subsections"]
        self.assertEqual([i["content"] for i in items], ["verbatim", "user", "user", "verbatim"])
        self.assertEqual([i["summary"] for i in items[1:3]], [None, None])
        self.assertEqual({n["code"] for n in record["clerk"]["notices"]}, {"empty"})
        self.assertEqual(record["clerk"]["limits"], {"min": 200, "max": 4000, "hard_max": 6000})

        saved = self.client.put(f"/api/trials/{sid}/record/draft",
                                json={"iv2": "**" + IV2 + "** Thiệt hại 5.000.000 đồng."})
        self.assertEqual(saved.status_code, 200, saved.text)
        body = saved.json()
        self.assertTrue(body["iv2"].startswith("Chủ tọa hỏi") and "**" not in body["iv2"])
        self.assertEqual(body["iv3"], "")
        self.assertIn(("iv2", "unknown_amount"), {(n["section"], n["code"]) for n in body["notices"]})
        self.assertIn(("iv3", "empty"), {(n["section"], n["code"]) for n in body["notices"]})
        self.assertEqual(self.client.put(f"/api/trials/{sid}/record/draft", json={"iv3": "x" * 6001}).status_code, 422)

        empty = self.client.post(f"/api/trials/{sid}/record/finalize")
        self.assertEqual((empty.status_code, self.code(empty)), (409, "trial_record_section_empty"))
        self.client.put(f"/api/trials/{sid}/record/draft", json={"iv3": IV3})
        final = self.client.post(f"/api/trials/{sid}/record/finalize")
        self.assertEqual(final.status_code, 200, final.text)
        body = final.json()
        self.assertFalse(body["record"]["draft"])
        self.assertEqual(body["record"]["preamble"], [])
        self.assertTrue(body["clerk"]["finalized"])
        self.assertIn("unknown_amount", {n["code"] for n in body["clerk"]["notices"]})   # notices never block
        items = body["record"]["sections"][3]["subsections"]
        self.assertEqual(items[2]["summary"], IV3)
        self.assertEqual(items[1]["author_note"], CLERK_AUTHOR_NOTE)
        self.assertIn(IV3, body["text"])
        self.assertNotIn(DRAFT_NOTE, body["text"])

        again = self.client.post(f"/api/trials/{sid}/record/finalize").json()
        self.assertEqual(again["clerk"]["finalized_at"], body["clerk"]["finalized_at"])
        locked = self.client.put(f"/api/trials/{sid}/record/draft", json={"iv2": IV2})
        self.assertEqual((locked.status_code, self.code(locked)), (409, "trial_record_finalized"))
        self.assertEqual(self.client.get(f"/api/trials/{sid}/record").json()["record"], body["record"])
        self.assertEqual(len(self.fake.calls), calls)   # the record side never calls the model

    def test_draft_routes_refuse_other_roles(self):
        sid, state = self.create(role="ksv")
        self.assertEqual(self.code(self.client.put(f"/api/trials/{sid}/record/draft", json={"iv2": IV2})),
                         "trial_not_clerk")
        self.assertEqual(self.code(self.client.post(f"/api/trials/{sid}/record/finalize")), "trial_not_clerk")
        state = routes.TrialRouteTests.play_to(self, sid, state)
        record = self.client.get(f"/api/trials/{sid}/record").json()
        self.assertIsNone(record["clerk"])
        self.assertFalse(record["record"]["draft"])
        self.assertIsNone(state["clerk_prompt"])

    def test_guard_pause_and_breaker_unchanged_for_the_clerk(self):
        sid, state = self.create(role="thu_ky")
        state = self.report(sid, state)
        bad = json.dumps({"utterances": [{"speaker_id": "THU_KY", "text": "Báo cáo Hội đồng xét xử."}],
                          "new_facts": []}, ensure_ascii=False)
        self.fake.bad["dialogue"] = [bad] * 6
        state, events = self.act(sid, state, "advance", target_step=2)
        spoken = [d for e, d in events if e == "utterance" and d["kind"] != "notice"]
        self.assertEqual(spoken, [])                       # nothing in the clerk's name got through
        self.assertEqual(state["allowed_actions"], ["continue"])
        state, _ = self.act(sid, state, "continue")
        state, _ = self.act(sid, state, "continue")
        self.assertEqual(state["allowed_actions"], [])
        exhausted = self.turn(sid, state, "continue")
        self.assertEqual(self.code(exhausted), "trial_guard_exhausted")


if __name__ == "__main__":
    unittest.main()
