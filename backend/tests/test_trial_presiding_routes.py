"""Route tests for the Chủ tọa role (chặng R4): whole hearings through /turn and PUT /decision with a
fake model and the in-memory repository - the checklist and 409 trial_procedure_incomplete, the
templates at 0 LLM calls, the decision form, the Hội thẩm comments kept out of the transcript, no AI
nghị án, the Điều 323 return, the record appendices, and what the API never returns. No Gemini, no
Supabase."""
from __future__ import annotations

import json
import unittest

from tests import test_trial_routes as routes   # module, not the class: its tests must not run twice here

from app.services import trial_presiding
from app.services.gemini_client import GeminiJsonResult

LONG_REASONING = ("Hội đồng xét xử nhận định hành vi của bị cáo đã đủ yếu tố cấu thành tội trộm cắp tài sản theo "
                  "khoản 1 Điều 173 Bộ luật Hình sự; bị cáo thành khẩn khai báo, đã tự nguyện trả lại tài sản và "
                  "bồi thường thiệt hại nên được hưởng các tình tiết giảm nhẹ.")


def good_decision(**changes) -> dict:
    decision = {"guilty": True, "dieu": "173", "khoan": "1", "diem": [], "penalty_type": "tu", "penalty_months": 12,
                "fine_vnd": None, "suspended": False, "probation_months": None, "applies_dieu_54": False,
                "mitigating": [{"khoan": "1", "diem": "b", "fact_ids": ["F2"]},
                               {"khoan": "1", "diem": "s", "fact_ids": ["F2"]}],
                "aggravating": [], "civil_amount_vnd": None, "reasoning_summary": LONG_REASONING,
                "exhibits": [{"evidence_id": "E1", "disposition": "tra_lai"}],
                "defendant_pays_criminal_fee": True, "defendant_pays_civil_fee": False}
    decision.update(changes)
    return decision


ASSESSOR_OK = {"hoi_tham_1": {"dong_y": True, "y_kien": "Tôi đồng ý với bản nháp về căn cứ kết tội."},
               "hoi_tham_2": {"dong_y": False, "y_kien": "Tôi cho rằng mức hình phạt nên nhẹ hơn vì bị cáo đã "
                                                         "khắc phục hậu quả."}}


class ChairFake(routes.FakeModel):
    """The route fake plus the Hội thẩm comment schema."""

    def __init__(self):
        super().__init__()
        self.assessor = [json.dumps(ASSESSOR_OK, ensure_ascii=False)]

    def __call__(self, system_prompt, user_prompt, settings, response_schema, **kw):
        if "hoi_tham_1" in response_schema.get("properties", {}):
            self.calls.append("assessor")
            text = self.assessor.pop(0) if len(self.assessor) > 1 else self.assessor[0]
            return GeminiJsonResult(text, "fake", 0.0, 100, 10, 0, 0, "STOP")
        return super().__call__(system_prompt, user_prompt, settings, response_schema, **kw)


class PresidingRouteTests(unittest.TestCase):
    tearDown = routes.TrialRouteTests.tearDown
    create = routes.TrialRouteTests.create
    turn = routes.TrialRouteTests.turn
    act = routes.TrialRouteTests.act

    def setUp(self):
        routes.TrialRouteTests.setUp(self)
        self.fake = ChairFake()
        routes.trial_metrics.generate_json_with_usage = self.fake

    # --- helpers -----------------------------------------------------------------------------------
    def code(self, response) -> str:
        self.assertEqual(response.status_code, 409, response.text)
        return response.json()["error"]["code"]

    def put_decision(self, sid, state, decision=None):
        return self.client.put(f"/api/trials/{sid}/decision",
                               json={"expected_version": state["version"], "decision": decision or good_decision()})

    def item(self, state, key):
        return next(i for i in state["presiding"]["items"] if i["key"] == key)

    def do(self, sid, state, key, **kw):
        """Performs one checklist item by its kind (the template unless `text` is given)."""
        kind = self.item(state, key)["kind"]
        if kind == "item":
            return self.act(sid, state, "item", item=key, **kw)[0]
        if kind == "invite":
            return self.act(sid, state, "invite", item=key, **kw)[0]
        if kind == "ask":
            addressee = "BI_CAO" if key == "hoi_bi_cao" else state["presiding"]["ask_addressees"][-1]
            return self.act(sid, state, "ask", addressee=addressee, text="Bị cáo trình bày lại diễn biến?")[0]
        if kind == "return":
            return self.act(sid, state, "return_to_questioning")[0]
        if kind == "decide":
            response = self.put_decision(sid, state)
            self.assertEqual(response.status_code, 200, response.text)
            state = response.json()["state"]
            return self.act(sid, state, "decide")[0]
        if kind == "pronounce":
            action = "pronounce" if "pronounce" in state["allowed_actions"] else "prepare_pronouncement"
            return self.act(sid, state, action)[0]
        raise AssertionError(kind)

    def play(self, sid, state, extra=None) -> dict:
        """Required items only, in checklist order; `extra(step, state)` may act first and return the
        new state (or None to go on)."""
        while state["status"] == "active":
            actions = state["allowed_actions"]
            if actions == ["continue"]:
                state, _ = self.act(sid, state, "continue")
                continue
            if state["current_step"] == 1:
                state, _ = self.act(sid, state, "advance", target_step=2)
                continue
            if extra is not None:
                moved = extra(state["current_step"], state)
                if moved is not None:
                    state = moved
                    continue
            missing = state["presiding"]["missing_required"]
            if missing:
                key = next(k for k in missing if self.item(state, k)["available"])
                state = self.do(sid, state, key)
            else:
                state, _ = self.act(sid, state, "advance", target_step=int(actions[-1].split(":")[1]))
        return state

    def rows(self, sid):
        return [r for r in self.repo.utterances if r["session_id"] == sid]

    # --- tests -------------------------------------------------------------------------------------
    def test_minimal_hearing_completes_without_ai_deliberation(self):
        sid, state = self.create(role="chu_toa")
        self.assertEqual(state["allowed_actions"], ["advance:2"])
        state = self.play(sid, state)
        self.assertEqual(state["status"], "completed")
        # The decision is the student's: no nghị án call, ever (decision Q8).
        self.assertNotIn("verdict", self.fake.calls)
        # Step 2 answers by code (Q5) - the only dialogue calls are the one question at step 4, the two
        # step-5 invitations, the step-7 victim and the step-9 last words.
        self.assertEqual(self.fake.calls.count("dialogue"), 5, self.fake.calls)
        self.assertEqual(self.fake.calls.count("tuyen_an"), 1)
        self.assertEqual(self.fake.calls.count("record_summary"), 1)
        rows = self.rows(sid)
        self.assertEqual([r for r in rows if r["speaker_id"] == "CHU_TOA" and not r["is_user"]], [])
        pronounced = [r for r in rows if r["procedure_item"] == "tuyen_an"]
        self.assertEqual(len(pronounced), 1)
        self.assertTrue(pronounced[0]["is_user"])
        self.assertIn("system_drafted", pronounced[0]["guard_flags"])
        self.assertNotIn("{BI_CAO}", pronounced[0]["content"])        # rendered with names, as the student said it
        session = self.repo.sessions[sid]
        self.assertEqual(session["verdict_json"]["source"], "user")
        self.assertEqual(session["user_work"]["preside"]["done"], ["tuyen_an"])

    def test_template_items_cost_no_call(self):
        sid, state = self.create(role="chu_toa")
        state, _ = self.act(sid, state, "advance", target_step=2)
        before = len(self.fake.calls)
        for key in ("khai_mac", "kiem_tra_can_cuoc", "kiem_tra_co_mat", "giai_thich_quyen", "hoi_thay_doi",
                    "cam_doan_nlc", "hoi_yeu_cau"):
            state = self.do(sid, state, key)
        self.assertEqual(len(self.fake.calls), before)
        rows = self.rows(sid)
        by_item = {}
        for r in rows:
            by_item.setdefault(r["procedure_item"], []).append(r["speaker_id"])
        self.assertEqual(by_item["hoi_thay_doi"], ["CHU_TOA", "KSV", "LUAT_SU", "BI_CAO"])
        self.assertEqual(by_item["cam_doan_nlc"], ["CHU_TOA", "NLC_1"])
        identity = [r for r in rows if r["step"] == 2 and r["speaker_id"] == "BI_CAO" and r["procedure_item"] is None]
        self.assertEqual(len(identity), 1)                              # identity_prefill, by code
        self.assertEqual(state["allowed_actions"][-1], "advance:3")
        self.assertEqual(state["presiding"]["missing_required"], [])

    def test_own_identity_question_gets_an_ai_answer(self):
        sid, state = self.create(role="chu_toa")
        state, _ = self.act(sid, state, "advance", target_step=2)
        state = self.do(sid, state, "khai_mac")
        state = self.do(sid, state, "kiem_tra_can_cuoc", text="Bị cáo cho Hội đồng xét xử biết họ tên, nơi ở?")
        self.assertEqual(self.fake.calls, ["dialogue"])
        self.assertEqual(state["awaiting"], "user")

    def test_khai_mac_first_and_advance_needs_every_required_item(self):
        sid, state = self.create(role="chu_toa")
        state, _ = self.act(sid, state, "advance", target_step=2)
        self.assertEqual(state["allowed_actions"], ["item:khai_mac"])
        self.assertEqual(self.code(self.turn(sid, state, "item", item="hoi_thay_doi")), "trial_item_not_available")
        response = self.turn(sid, state, "advance", target_step=3)
        self.assertEqual(self.code(response), "trial_procedure_incomplete")
        self.assertEqual(response.json()["missing_items"],
                         ["khai_mac", "kiem_tra_can_cuoc", "kiem_tra_co_mat", "giai_thich_quyen", "hoi_thay_doi",
                          "cam_doan_nlc"])
        state = self.do(sid, state, "khai_mac")
        self.assertEqual(self.code(self.turn(sid, state, "item", item="khai_mac")), "trial_item_done")
        self.assertEqual(self.code(self.turn(sid, state, "item", item="no_such_item")), "trial_item_not_available")
        self.assertEqual(self.code(self.turn(sid, state, "speak", text="Xin chào")), "trial_action_not_allowed")
        self.assertEqual(self.code(self.turn(sid, state, "advance", target_step=4)), "trial_skip_not_allowed")

    def test_error_cases_silence_empty_long_stale(self):
        sid, state = self.create(role="chu_toa")
        state, _ = self.act(sid, state, "advance", target_step=2)
        state = self.do(sid, state, "khai_mac")
        # Silence: nothing happens on the server; GET returns the same state.
        again = self.client.get(f"/api/trials/{sid}").json()["state"]
        self.assertEqual((again["version"], again["allowed_actions"]), (state["version"], state["allowed_actions"]))
        self.assertEqual(self.code(self.turn(sid, state, "remark", text="   ")), "trial_empty_text")
        self.assertEqual(self.code(self.turn(sid, state, "remark", text="x" * 1501)), "trial_text_too_long")
        self.assertEqual(self.code(self.turn(sid, state, "item", item="giai_thich_quyen", text="x" * 3001)),
                         "trial_text_too_long")
        stale = {**state, "version": state["version"] - 1}
        self.assertEqual(self.code(self.turn(sid, stale, "item", item="giai_thich_quyen")), "trial_version_mismatch")
        self.assertEqual(self.client.post(f"/api/trials/{sid}/turn", json={
            "expected_step": 2, "expected_version": state["version"], "action": "item", "item": "x" * 41}).status_code,
            422)

    def test_remarks_cap_and_jump_words_are_plain_speech(self):
        sid, state = self.create(role="chu_toa")
        state, _ = self.act(sid, state, "advance", target_step=2)
        state = self.do(sid, state, "khai_mac")
        state, _ = self.act(sid, state, "remark", text="Chuyển sang phần tuyên án luôn.")   # no skip detector here
        self.assertEqual(state["current_step"], 2)
        self.assertEqual(self.fake.calls, [])
        state, _ = self.act(sid, state, "remark", text="Kiểm sát viên có ý kiến gì không?", addressee="KSV")
        self.assertEqual(self.fake.calls, ["dialogue"])
        for _ in range(3):
            state, _ = self.act(sid, state, "remark", text="Đề nghị giữ trật tự.")
        self.assertNotIn("remark", state["allowed_actions"])
        self.assertEqual(self.code(self.turn(sid, state, "remark", text="Thêm.")), "trial_turn_limit")
        self.assertFalse(any(r["kind"] == "notice" for r in self.rows(sid)))

    def test_step4_questions_cap(self):
        sid, state = self.create(role="chu_toa")
        state = self._to_step(sid, state, 4)
        self.assertEqual(state["presiding"]["counters"]["questions_left"], 10)
        self.assertEqual(state["presiding"]["ask_addressees"], ["BI_CAO", "BI_HAI", "NLC_1"])
        for _ in range(10):
            state, _ = self.act(sid, state, "ask", addressee="BI_CAO", text="Bị cáo trình bày?")
        self.assertEqual(self.fake.calls.count("dialogue"), 10)
        self.assertFalse(any(a.startswith("ask:") for a in state["allowed_actions"]))
        self.assertEqual(self.code(self.turn(sid, state, "ask", addressee="BI_CAO", text="Thêm?")), "trial_turn_limit")
        self.assertIn("advance:5", state["allowed_actions"])

    def _to_step(self, sid, state, step):
        """Plays the required items until `step` is entered."""
        def extra(current, s):
            if current >= step:
                raise _Reached(s)
            return None
        try:
            self.play(sid, state, extra=extra)
        except _Reached as reached:
            return reached.state
        raise AssertionError("step not reached")

    def test_decision_form_errors_block_and_warnings_do_not(self):
        sid, state = self.create(role="chu_toa")
        state = self._to_step(sid, state, 10)
        self.assertEqual(self.code(self.put_decision(sid, state)), "trial_action_not_allowed")  # before vào nghị án
        state = self.do(sid, state, "vao_nghi_an")
        self.assertNotIn("decide", state["allowed_actions"])
        self.assertEqual(self.code(self.turn(sid, state, "decide")), "trial_decision_missing")
        bad = good_decision(penalty_months=48, exhibits=[])
        response = self.put_decision(sid, state, bad)
        self.assertEqual(response.status_code, 200, response.text)
        state = response.json()["state"]
        codes = {e["code"] for e in state["decision"]["check"]["errors"]}
        self.assertEqual(codes, {"above_frame", "exhibit_missing"})
        self.assertNotIn("decide", state["allowed_actions"])
        self.assertNotIn("y_kien_hoi_tham", "".join(state["allowed_actions"]))
        response = self.turn(sid, state, "decide")
        self.assertEqual(self.code(response), "trial_decision_invalid")
        self.assertEqual(sorted(response.json()["errors"]), ["above_frame", "exhibit_missing"])
        warned = good_decision(khoan="2", penalty_months=30, civil_amount_vnd=9_000_000)   # heavier khoản (Q9), civil (Q11)
        state = self.put_decision(sid, state, warned).json()["state"]
        check = state["decision"]["check"]
        self.assertEqual(check["errors"], [])
        self.assertEqual({w["code"] for w in check["warnings"]}, {"khoan_heavier", "civil_over_claim"})
        self.assertIn("decide", state["allowed_actions"])
        state, _ = self.act(sid, state, "decide")
        self.assertTrue(state["decision"]["locked"])
        self.assertEqual(self.code(self.put_decision(sid, state)), "trial_decision_locked")

    def test_assessors_comment_on_the_draft_outside_the_transcript(self):
        sid, state = self.create(role="chu_toa")
        state = self._to_step(sid, state, 10)
        state = self.do(sid, state, "vao_nghi_an")
        state = self.put_decision(sid, state).json()["state"]
        rows_before = len(self.rows(sid))
        state, events = self.act(sid, state, "invite", item="y_kien_hoi_tham")
        self.assertEqual(self.fake.calls.count("assessor"), 1)
        self.assertEqual(len(self.rows(sid)), rows_before)                 # Q16: not in the transcript
        self.assertFalse([e for e, _ in events if e == "utterance"])
        opinions = state["decision"]["assessor_opinions"]
        self.assertEqual([o["agrees"] for o in opinions], [True, False])
        self.assertIn("Điều 326", state["decision"]["assessor_order_note"])  # Q7 label
        self.assertEqual(self.code(self.turn(sid, state, "invite", item="y_kien_hoi_tham")), "trial_item_done")
        state, _ = self.act(sid, state, "decide")
        state, _ = self.act(sid, state, "advance", target_step=11)
        state, _ = self.act(sid, state, "prepare_pronouncement")
        self.assertIn("NHÂN DANH", state["decision"]["pronouncement_preview"])
        self.assertEqual(state["allowed_actions"], ["pronounce"])
        state, _ = self.act(sid, state, "pronounce")
        record = self.client.get(f"/api/trials/{sid}/record").json()
        appendix = record["record"]["appendix"]
        self.assertEqual(len(appendix), 2)
        self.assertIn("Lời tuyên do hệ thống soạn", " ".join(appendix[0]["notes"]))
        self.assertIn("Biên bản nghị án", appendix[1]["heading"])
        self.assertTrue(any("Ý kiến thiểu số" in n for n in appendix[1]["notes"]))
        self.assertIn("BIÊN BẢN NGHỊ ÁN", record["text"])

    def test_assessor_naming_its_own_penalty_is_regenerated(self):
        own = {"hoi_tham_1": {"dong_y": False, "y_kien": "Nên xử 18 tháng tù."},
               "hoi_tham_2": {"dong_y": True, "y_kien": "Đồng ý."}}
        self.fake.assessor = [json.dumps(own, ensure_ascii=False), json.dumps(own, ensure_ascii=False),
                              json.dumps(ASSESSOR_OK, ensure_ascii=False)]
        sid, state = self.create(role="chu_toa")
        state = self._to_step(sid, state, 10)
        state = self.do(sid, state, "vao_nghi_an")
        state = self.put_decision(sid, state).json()["state"]
        state, events = self.act(sid, state, "invite", item="y_kien_hoi_tham")
        self.assertEqual(self.fake.calls.count("assessor"), 2)             # rejected twice: pause
        self.assertEqual(state["allowed_actions"], ["continue"])
        notice = [d for e, d in events if e == "utterance"][-1]
        self.assertEqual((notice["speaker_id"], notice["kind"]), ("HE_THONG", "notice"))
        self.assertEqual(notice["speaker_role"], "Hệ thống")
        state, _ = self.act(sid, state, "continue")
        self.assertEqual(len(state["decision"]["assessor_opinions"]), 2)
        self.assertIsNone(self.repo.sessions[sid]["verdict_json"])

    def test_return_to_questioning_once_from_step_8(self):
        sid, state = self.create(role="chu_toa")
        state = self._to_step(sid, state, 8)
        self.assertNotIn("return_to_questioning", state["allowed_actions"])     # before a round
        state = self.do(sid, state, "moi_doi_dap")
        self.assertIn("return_to_questioning", state["allowed_actions"])
        self.assertEqual(self.item(state, "vong_2")["note"], trial_presiding.DEBATE_ROUNDS_NOTE)   # Q12
        state, _ = self.act(sid, state, "return_to_questioning")
        self.assertEqual((state["current_step"], state["presiding"]["in_return"]), (5, True))
        self.assertEqual(state["presiding"]["counters"]["questions_left"], 3)
        self.assertEqual(state["presiding"]["missing_required"], ["ket_thuc_xet_hoi"])
        self.assertEqual(self.code(self.turn(sid, state, "advance", target_step=6)), "trial_skip_not_allowed")
        for _ in range(3):
            state, _ = self.act(sid, state, "ask", addressee="BI_CAO", text="Bị cáo làm rõ thêm?")
        self.assertEqual(self.code(self.turn(sid, state, "ask", addressee="BI_CAO", text="Nữa?")), "trial_turn_limit")
        state = self.do(sid, state, "moi_ksv_hoi")
        state = self.do(sid, state, "ket_thuc_xet_hoi")
        self.assertEqual(state["allowed_actions"][-1], "advance:8")
        state, _ = self.act(sid, state, "advance", target_step=8)
        self.assertFalse(state["presiding"]["in_return"])
        self.assertNotIn("tro_lai_xet_hoi", [i["key"] for i in state["presiding"]["items"]])
        self.assertEqual(self.code(self.turn(sid, state, "return_to_questioning")), "trial_return_used")
        self.assertEqual(state["presiding"]["missing_required"], ["moi_doi_dap", "ket_thuc_tranh_luan"])
        state = self.play(sid, state)
        record = self.client.get(f"/api/trials/{sid}/record").json()["record"]
        iv2 = record["sections"][3]["subsections"][1]
        self.assertIn("trở lại việc xét hỏi", " ".join(iv2["notes"]))

    def test_last_words_then_no_question_to_the_defendant(self):
        sid, state = self.create(role="chu_toa")
        state = self._to_step(sid, state, 9)
        self.assertIn("BI_CAO", state["presiding"]["remark_addressees"])
        state = self.do(sid, state, "moi_loi_sau_cung")
        self.assertNotIn("BI_CAO", state["presiding"]["remark_addressees"])
        self.assertEqual(self.code(self.turn(sid, state, "remark", text="Bị cáo còn gì nữa?", addressee="BI_CAO")),
                         "trial_missing_addressee")

    def test_nothing_hidden_leaks_and_other_roles_have_no_presiding_keys(self):
        sid, state = self.create(role="chu_toa")
        state = self._to_step(sid, state, 10)
        state = self.do(sid, state, "vao_nghi_an")
        state = self.put_decision(sid, state).json()["state"]
        state, _ = self.act(sid, state, "decide")
        body = self.client.get(f"/api/trials/{sid}").json()
        dumped = json.dumps(body, ensure_ascii=False)
        for hidden in ("verdict_json", "knobs", "defendant_plea", "stance", "source"):
            self.assertNotIn(f'"{hidden}"', dumped)
        self.assertNotIn("role_brief", body)
        for role in ("ksv", "luat_su", "nguoi_xem", "thu_ky", "bi_cao"):
            self.repo._usage_rows().clear()       # the daily limit is not what this test is about
            other, other_state = self.create(role=role)
            self.client.post(f"/api/trials/{other}/abandon")
            self.assertIsNone(other_state["presiding"], role)
            self.assertIsNone(other_state["decision"], role)
            for action in ("item", "invite", "decide"):
                self.assertEqual(self.code(self.turn(other, {**other_state, "status": "active"}, action, item="x")),
                                 "trial_not_active")
            response = self.client.put(f"/api/trials/{other}/decision",
                                       json={"expected_version": 0, "decision": good_decision()})
            self.assertEqual(self.code(response), "trial_not_presiding")

    def test_presiding_actions_refused_for_other_roles(self):
        sid, state = self.create(role="ksv")
        state, _ = self.act(sid, state, "advance", target_step=2)
        for action in ("item", "ask", "invite", "remark", "return_to_questioning", "decide", "pronounce"):
            self.assertEqual(self.code(self.turn(sid, state, action, item="khai_mac", text="x")),
                             "trial_action_not_allowed", action)


class _Reached(Exception):
    def __init__(self, state):
        super().__init__("reached")
        self.state = state


if __name__ == "__main__":
    unittest.main()
