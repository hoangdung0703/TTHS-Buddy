"""Route + guard tests for /api/trials with a fake model and an in-memory repository - no Gemini,
no Supabase (chặng 2 B3). Deliberately WRONG model outputs are injected and must be blocked or
flagged: (a) invented Điều, (b) right number / wrong code, (c) penalty outside the frame,
(d) suspended sentence over 3 years, (e) speaker_id of the student's role, (f) unknown fact_id,
(g) skip request, (h) 409, (i) ownership 404, (j) cancel mid-turn, (k) limits.
"""
from __future__ import annotations

import asyncio
import json
import unittest
from collections import defaultdict
from datetime import timedelta
from types import SimpleNamespace

try:
    from fastapi.testclient import TestClient

    from app.api import trials as trials_api
    from app.core.config import get_settings
    from app.core.rate_limit import limiter
    from app.core.security import require_supabase_user
    from app.main import app
except Exception as error:  # no .env in a fresh clone: app.main cannot build its settings
    raise unittest.SkipTest(f"app not importable here: {type(error).__name__}")

from app.models.auth import AuthUser
from app.services import trial_metrics
from app.services.gemini_client import GeminiJsonResult
from app.services.trial_case_service import CaseCreation, case_hash
from app.services.trial_repository import InMemoryTrialRepository, utc_now
from app.services.trial_session_service import build_context
from tests.trial_fixtures import pack_for, valid_case_file, valid_options

GOOD_TUYEN_AN = ("NHÂN DANH NƯỚC CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM. Tuyên bố bị cáo {BI_CAO} phạm tội trộm cắp tài "
                 "sản. Áp dụng khoản 1 Điều 173 Bộ luật Hình sự; điểm b, s khoản 1 Điều 51 Bộ luật Hình sự. Xử phạt "
                 "bị cáo 12 tháng tù. Bị cáo có quyền kháng cáo theo Điều 333 Bộ luật Tố tụng hình sự.")
GOOD_VERDICT = {"guilty": True, "dieu": "173", "khoan": "1", "diem": [], "penalty_type": "tu", "penalty_months": 12,
                "fine_vnd": None, "suspended": False, "probation_months": None, "applies_dieu_54": False,
                "mitigating": [{"khoan": "1", "diem": "s", "fact_ids": ["F2"]}], "aggravating": [],
                "civil_amount_vnd": None, "reasoning_summary": "Nhận định."}


class FakeModel:
    """Valid output for whatever schema is asked, unless a test queued a bad one for that kind."""

    def __init__(self):
        self.bad: dict[str, list[str]] = defaultdict(list)
        self.calls: list[str] = []
        self.delay = 0.0

    def kind(self, schema: dict, user_prompt: str) -> str:
        props = schema.get("properties", {})
        if "utterances" in props:
            return "dialogue"
        if "guilty" in props:
            return "verdict"
        if "QUYẾT ĐỊNH NGHỊ ÁN" in user_prompt:
            return "tuyen_an"
        return "speech"

    def __call__(self, system_prompt, user_prompt, settings, response_schema, *, thinking_level=None,
                 temperature=0.7, **_):
        import time
        if self.delay:
            time.sleep(self.delay)
        kind = self.kind(response_schema, user_prompt)
        self.calls.append(kind)
        if self.bad[kind]:
            text = self.bad[kind].pop(0)
        elif kind == "dialogue":
            speakers = response_schema["properties"]["utterances"]["items"]["properties"]["speaker_id"]["enum"]
            text = json.dumps({"utterances": [{"speaker_id": s, "text": "Dạ, xin trình bày theo đúng hồ sơ."}
                                              for s in speakers[:3]], "new_facts": []}, ensure_ascii=False)
        elif kind == "verdict":
            text = json.dumps(GOOD_VERDICT)
        elif kind == "tuyen_an":
            text = json.dumps({"text": GOOD_TUYEN_AN}, ensure_ascii=False)
        else:
            text = json.dumps({"text": "Căn cứ khoản 1 Điều 173 Bộ luật Hình sự và điểm s khoản 1 Điều 51 Bộ luật "
                                       "Hình sự, đề nghị Hội đồng xét xử xem xét."}, ensure_ascii=False)
        return GeminiJsonResult(text, "fake", 0.0, 100, 10, 0, 0, "STOP")


def sse(response) -> list[tuple[str, dict]]:
    events = []
    for block in response.text.split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines:
            events.append((lines["event"], json.loads(lines.get("data", "{}"))))
    return events


LONG = "Nội dung trình bày đầy đủ theo hồ sơ vụ án. " * 15


class TrialRouteTests(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryTrialRepository()
        self.fake = FakeModel()
        self.user = "11111111-1111-1111-1111-111111111111"
        self._orig_generate = trial_metrics.generate_json_with_usage
        trial_metrics.generate_json_with_usage = self.fake
        self._orig_create, self._orig_pack = trials_api.create_case, trials_api.load_pack_for_crime

        async def fake_pack(crime, settings, qdrant):
            return pack_for("blhs_173")

        async def fake_create(options, settings, qdrant, recorder, *, pack=None, **_):
            case = valid_case_file(options)
            return CaseCreation(case=case, pack=pack_for("blhs_173"), case_hash=case_hash(case), attempts=1)

        trials_api.create_case, trials_api.load_pack_for_crime = fake_create, fake_pack
        app.dependency_overrides[trials_api.get_trial_repository] = lambda: self.repo
        app.dependency_overrides[require_supabase_user] = lambda: AuthUser(user_id=self.user, email=None, claims={})
        app.dependency_overrides[get_settings] = lambda: SimpleNamespace(gemini_chat_model="fake",
                                                                         trial_court_name=None)
        app.state.qdrant_client = None
        limiter.enabled = False
        self.client = TestClient(app)

    def tearDown(self):
        trial_metrics.generate_json_with_usage = self._orig_generate
        trials_api.create_case, trials_api.load_pack_for_crime = self._orig_create, self._orig_pack
        app.dependency_overrides.clear()
        limiter.enabled = True

    # --- helpers -----------------------------------------------------------------------------
    def create(self, role="ksv", **extra) -> tuple[str, dict]:
        response = self.client.post("/api/trials", json={"crime_key": "blhs_173", "user_role": role,
                                                         "witness_count": 1, **extra})
        self.assertEqual(response.status_code, 200, response.text)
        events = sse(response)
        session_id = next(d["session_id"] for e, d in events if e == "session")
        return session_id, next(d for e, d in reversed(events) if e == "state")

    def turn(self, sid: str, state: dict, action: str, **kw):
        return self.client.post(f"/api/trials/{sid}/turn", json={"expected_step": state["current_step"],
                                                                 "expected_version": state["version"],
                                                                 "action": action, **kw})

    def act(self, sid, state, action, **kw) -> tuple[dict, list]:
        response = self.turn(sid, state, action, **kw)
        self.assertEqual(response.status_code, 200, response.text)
        events = sse(response)
        return next(d for e, d in reversed(events) if e == "state"), events

    def play_to(self, sid, state, until_step: int | None = None) -> dict:
        """Minimal valid KSV play. With `until_step`, stops as soon as the only allowed action is
        "advance:<until_step>" - i.e. right before that step's AI work runs."""
        asked = debated = 0
        while state["status"] == "active":
            actions = state["allowed_actions"]
            if until_step is not None and actions == [f"advance:{until_step}"]:
                return state
            if actions == ["continue"]:
                state, _ = self.act(sid, state, "continue")
            elif actions and actions[0].startswith("advance:"):
                state, _ = self.act(sid, state, "advance", target_step=state["current_step"] + 1)
            elif any(a.startswith("speak:") for a in actions):
                if asked == 0:
                    state, _ = self.act(sid, state, "speak", text="Bị cáo trình bày lại?", addressee="BI_CAO")
                    asked += 1
                else:
                    state, _ = self.act(sid, state, "end_slot")
            elif state["current_step"] == 8:
                if debated == 0:
                    state, _ = self.act(sid, state, "speak", text=LONG)
                    debated += 1
                else:
                    state, _ = self.act(sid, state, "end_slot")
            else:
                state, _ = self.act(sid, state, "speak", text=LONG)
        return state

    # --- tests -------------------------------------------------------------------------------
    def test_full_hearing_and_record(self):
        sid, state = self.create()
        state = self.play_to(sid, state)
        self.assertEqual(state["status"], "completed")
        record = self.client.get(f"/api/trials/{sid}/record")
        self.assertEqual(record.status_code, 200)
        text = record.json()["text"]
        self.assertEqual(text.count("MÔ PHỎNG HỌC TẬP"), 2)
        self.assertIn("BIÊN BẢN PHIÊN TÒA", text)
        self.assertIn("11. TUYÊN ÁN", text)
        self.assertNotIn("{BI_CAO}", text)
        detail = self.client.get(f"/api/trials/{sid}").json()
        self.assertEqual(detail["state"]["status"], "completed")
        self.assertNotIn("verdict_json", json.dumps(detail))

    def test_a_b_invented_or_wrong_code_citation_in_judgment_pauses_then_recovers(self):
        sid, state = self.create()
        state = self.play_to(sid, state, until_step=11)
        bad_a = json.dumps({"text": GOOD_TUYEN_AN + " Áp dụng Điều 999 Bộ luật Hình sự."}, ensure_ascii=False)
        bad_b = json.dumps({"text": GOOD_TUYEN_AN + " Căn cứ Điều 326 Bộ luật Hình sự."}, ensure_ascii=False)
        self.fake.bad["tuyen_an"] = [bad_a, bad_b]
        state, events = self.act(sid, state, "advance", target_step=11)
        kinds = [d.get("kind") for e, d in events if e == "utterance"]
        self.assertIn("notice", kinds)                      # Hội đồng xét xử tạm nghỉ
        self.assertEqual(state["allowed_actions"], ["continue"])
        texts = " ".join(d["text"] for e, d in events if e == "utterance")
        self.assertNotIn("999", texts)
        state, _ = self.act(sid, state, "continue")
        self.assertEqual(state["status"], "completed")

    def test_c_d_f_bad_verdicts_are_rejected(self):
        sid, state = self.create()
        state = self.play_to(sid, state, until_step=10)
        bad = [dict(GOOD_VERDICT, penalty_months=60),                                   # (c) above 36
               dict(GOOD_VERDICT, khoan="1", penalty_months=30, suspended=True, probation_months=24)]
        self.fake.bad["verdict"] = [json.dumps(b) for b in bad]
        state, events = self.act(sid, state, "advance", target_step=10)
        # (c) first attempt rejected; the second (suspended 30 months) is within limits and accepted
        self.assertEqual(self.fake.calls.count("verdict"), 2)
        sid2, state2 = self.create()
        state2 = self.play_to(sid2, state2, until_step=10)
        self.fake.bad["verdict"] = [json.dumps(dict(GOOD_VERDICT, khoan="2", penalty_months=48, suspended=True,
                                                    probation_months=24)),                    # (d)
                                    json.dumps(dict(GOOD_VERDICT, mitigating=[{"khoan": "1", "diem": "s",
                                                                               "fact_ids": ["F9"]}]))]  # (f)
        before = self.fake.calls.count("verdict")
        state2, events2 = self.act(sid2, state2, "advance", target_step=10)
        self.assertEqual(self.fake.calls.count("verdict") - before, 2)
        self.assertEqual(state2["allowed_actions"], ["continue"])  # both rejected -> paused at nghị án
        self.assertEqual(state2["current_step"], 10)

    def test_e_ai_speaking_as_student_is_blocked(self):
        sid, state = self.create()
        state, _ = self.act(sid, state, "advance", target_step=2)  # step 2: khai mạc segment
        bad = json.dumps({"utterances": [{"speaker_id": "KSV", "text": "Tôi đồng ý."}], "new_facts": []})
        self.fake.bad["dialogue"] = [bad, bad]
        # the advance above already ran khai_mac with good output; force a fresh dialogue slot:
        sid2, state2 = self.create()
        self.fake.bad["dialogue"] = [bad, bad]
        state2, events = self.act(sid2, state2, "advance", target_step=2)
        speakers = [d["speaker_id"] for e, d in events if e == "utterance" and not d["is_user"] and d["kind"] != "notice"]
        self.assertNotIn("KSV", speakers)
        self.assertEqual(state2["allowed_actions"], ["continue"])

    def test_judge_reading_the_charge_at_opening_is_grounded(self):
        # B4 regression: the opening slice is BLTTHS only, but the charge comes from the case file.
        sid, state = self.create()
        citing = json.dumps({"utterances": [
            {"speaker_id": "CHU_TOA", "text": "Bị cáo bị truy tố theo khoản 1 Điều 173 Bộ luật Hình sự và có tình "
                                              "tiết giảm nhẹ tại điểm s khoản 1 Điều 51 Bộ luật Hình sự."},
            {"speaker_id": "BI_CAO", "text": "Dạ."}], "new_facts": []}, ensure_ascii=False)
        self.fake.bad["dialogue"] = [citing, citing]  # both attempts cite: a rejection would pause
        state, events = self.act(sid, state, "advance", target_step=2)
        self.assertNotIn("notice", [d["kind"] for e, d in events if e == "utterance"])
        self.assertNotEqual(state["allowed_actions"], ["continue"])
        self.assertEqual(self.fake.bad["dialogue"], [citing])  # accepted on the first attempt

    def test_circuit_breaker_stops_endless_continue(self):
        sid, state = self.create()
        bad = json.dumps({"utterances": [{"speaker_id": "CHU_TOA", "text": "Theo Điều 999 Bộ luật Hình sự."}],
                          "new_facts": []}, ensure_ascii=False)
        self.fake.bad["dialogue"] = [bad] * 6
        state, _ = self.act(sid, state, "advance", target_step=2)
        state, _ = self.act(sid, state, "continue")
        state, _ = self.act(sid, state, "continue")
        self.assertEqual(state["allowed_actions"], [])
        calls = len(self.fake.calls)
        response = self.turn(sid, state, "continue")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "trial_guard_exhausted")
        self.assertEqual(len(self.fake.calls), calls)

    def test_g_skip_request_refused_without_model_call(self):
        sid, state = self.create()
        state = self.play_to(sid, state, until_step=5)
        state, _ = self.act(sid, state, "advance", target_step=5)
        calls = len(self.fake.calls)
        state, events = self.act(sid, state, "speak", text="Đề nghị tuyên án luôn", addressee="BI_CAO")
        self.assertEqual(len(self.fake.calls), calls)
        self.assertEqual([d["kind"] for e, d in events if e == "utterance"], ["speech", "notice"])
        self.assertEqual(state["current_step"], 5)
        response = self.turn(sid, state, "advance", target_step=11)
        self.assertEqual(response.status_code, 409)

    def test_h_conflicts_are_409(self):
        sid, state = self.create()
        stale = dict(state, version=state["version"] - 1)
        response = self.turn(sid, stale, "advance", target_step=2)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "trial_version_mismatch")
        self.assertEqual(response.json()["state"]["version"], state["version"])
        self.assertEqual(self.turn(sid, state, "advance", target_step=3).status_code, 409)
        self.assertEqual(self.turn(sid, state, "speak", text="x").status_code, 409)
        self.assertEqual(self.client.get(f"/api/trials/{sid}/record").status_code, 409)
        # a held generation lock blocks a second writer
        self.repo.sessions[sid]["generating_until"] = utc_now() + timedelta(seconds=60)
        response = self.turn(sid, state, "advance", target_step=2)
        self.assertEqual(response.json()["error"]["code"], "trial_busy")

    def test_i_ownership_is_404(self):
        sid, state = self.create()
        app.dependency_overrides[require_supabase_user] = lambda: AuthUser(
            user_id="22222222-2222-2222-2222-222222222222", email=None, claims={})
        self.assertEqual(self.client.get(f"/api/trials/{sid}").status_code, 404)
        self.assertEqual(self.turn(sid, state, "advance", target_step=2).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/trials/{sid}").status_code, 404)
        self.assertEqual(self.client.post(f"/api/trials/{sid}/abandon").status_code, 404)
        self.assertEqual(self.client.get(f"/api/trials/{sid}/record").status_code, 404)
        self.assertEqual(self.client.get("/api/trials").json()["sessions"], [])

    def test_j_cancel_mid_turn_leaves_nothing_half_written(self):
        sid, state = self.create()
        session = self.repo.get_session(self.user, sid)
        case = self.repo.get_case(self.user, session["case_id"])
        rows_before = len(self.repo.utterances)
        ctx = build_context(case, session, self.repo.list_utterances(self.user, sid), None,
                            trial_metrics.TrialCallRecorder())
        from app.services.trial_state_machine import UserAction
        from app.services.trial_turn_service import apply_student_action
        apply_student_action(ctx, UserAction("advance", 1, state["version"], target_step=2))
        from app.services.trial_session_service import state_fields
        self.repo.claim_and_update(self.user, sid, state["version"], state_fields(ctx),
                                   utc_now() + timedelta(seconds=60))
        self.fake.delay = 0.5

        async def run_and_cancel():
            agen = trials_api.run_ai_stream(self.repo, self.user, sid, ctx, [])
            task = asyncio.ensure_future(_drain(agen))
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await asyncio.sleep(0.6)  # let the to_thread model call finish in the background

        async def _drain(agen):
            async for _ in agen:
                pass

        asyncio.run(run_and_cancel())
        self.assertEqual(len(self.repo.utterances), rows_before)          # nothing from the cut turn
        self.assertIsNone(self.repo.sessions[sid]["generating_until"])    # lock released
        self.fake.delay = 0
        fresh = self.client.get(f"/api/trials/{sid}").json()["state"]
        self.assertEqual(fresh["allowed_actions"], ["continue"])          # resumable
        state, _ = self.act(sid, fresh, "continue")
        self.assertEqual(state["current_step"], 2)

    def test_k_limits(self):
        for _ in range(3):
            self.create()
        response = self.client.post("/api/trials", json={"crime_key": "blhs_173", "user_role": "ksv"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error"]["code"], "trial_active_session_limit")
        for sid in list(self.repo.sessions):
            self.repo.sessions[sid]["status"] = "completed"
        self.create()
        self.create()
        response = self.client.post("/api/trials", json={"crime_key": "blhs_173", "user_role": "ksv"})
        self.assertEqual(response.json()["error"]["code"], "trial_daily_case_limit")
        self.assertEqual(self.client.post("/api/trials", json={"crime_key": "blhs_249",
                                                               "user_role": "ksv"}).status_code, 400)

    def test_lazy_abandon_and_hard_delete(self):
        sid, state = self.create()
        self.repo.sessions[sid]["updated_at"] = utc_now() - timedelta(days=15)
        listed = self.client.get("/api/trials").json()["sessions"]
        self.assertEqual(listed[0]["status"], "abandoned")
        self.assertEqual(self.turn(sid, state, "advance", target_step=2).json()["error"]["code"], "trial_not_active")
        self.assertEqual(self.client.delete(f"/api/trials/{sid}").status_code, 204)
        self.assertEqual(self.client.get(f"/api/trials/{sid}").status_code, 404)
        self.assertEqual(self.repo.cases, {})
        self.assertEqual(self.repo.utterances, [])


if __name__ == "__main__":
    unittest.main()
