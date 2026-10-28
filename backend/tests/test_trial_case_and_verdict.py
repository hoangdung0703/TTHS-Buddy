"""Unit tests: case schema + validator, names, verdict guard (design doc Mục 3.2, 5.2, 8.1)."""
from __future__ import annotations

import asyncio
import copy
import json
import random
import unicodedata
import unittest
from types import SimpleNamespace
from unittest import mock

from pydantic import ValidationError

from app.models.trial import CaseDraft, CaseKnobs, CaseOptions, Verdict
from app.prompts.trial_prompts import CASE_GENERATION_SYSTEM_PROMPT
from app.services import trial_case_service
from app.services.trial_case_frame import build_frame, fill_schema, fill_to_draft, frame_text
from app.services.trial_case_service import CaseGenerationFailed, create_case
from app.services.trial_case_validator import DIACRITIC_ERROR, error_label, normalise_draft_dict, validate_case_draft
from app.services.trial_config import ABSTRACT_PLACES, AGGRAVATING_POOL, BLHS_DOCUMENT, CRIMES, get_crime
from app.services.trial_knobs import choose_knobs
from app.services.trial_legal_pack import Khoan
from app.services.trial_names import assign_names, name_hash, render
from app.services.trial_verdict_guard import check_verdict, parse_penalty_frame
from tests.test_trial_turns import ScriptedRecorder
from tests.trial_fixtures import (
    STATEMENT_BI_HAI,
    fill_from_draft,
    pack_for,
    valid_case_file,
    valid_draft_dict,
    valid_frame,
    valid_knobs,
    valid_options,
)


def errors_for(draft: dict, options: CaseOptions | None = None, crime_key: str = "blhs_173") -> list[str]:
    options = options or valid_options().model_copy(update={"crime_key": crime_key})
    return validate_case_draft(CaseDraft.model_validate(draft), options, get_crime(crime_key), pack_for(crime_key))


class CaseValidatorTests(unittest.TestCase):
    def test_valid_fixture_passes(self):
        self.assertEqual(errors_for(valid_draft_dict()), [])

    def test_code_fields_are_normalised_before_validation(self):
        draft = valid_draft_dict()
        draft["defendant"]["id"] = "{BI_CAO}"
        draft["pretrial_statements"][0]["person_id"] = "{BI_CAO}"
        draft["charge"].update({"dieu": "Điều 173", "khoan": "Khoản 1"})
        draft["mitigating"][0]["diem"] = "điểm b"
        self.assertEqual(errors_for(normalise_draft_dict(draft)), [])
        self.assertEqual(normalise_draft_dict({"charge": {"dieu": "x", "khoan": "1", "diem": ["đ"]}})["charge"]["diem"],
                         ["đ"])

    def test_residence_is_assigned_by_code(self):
        draft = valid_draft_dict()
        for person in (draft["defendant"], draft["victim"], *draft["witnesses"]):
            person.pop("residence_place")
        draft["victim"]["residence_place"] = "Quận 1, TP Hồ Chí Minh"   # an off-list value is overwritten
        normalised = normalise_draft_dict(draft)
        places = [normalised["defendant"]["residence_place"], normalised["victim"]["residence_place"],
                  normalised["witnesses"][0]["residence_place"]]
        self.assertTrue(all(p in ABSTRACT_PLACES for p in places))
        self.assertEqual(errors_for(normalised), [])
        self.assertNotIn("residence_place", json.dumps(fill_schema(valid_frame())))

    def test_extra_field_is_rejected_by_schema(self):
        draft = valid_draft_dict()
        draft["defendant"]["real_name"] = "x"
        with self.assertRaises(ValidationError):
            CaseDraft.model_validate(draft)

    def test_charge_must_be_allowed_and_exist(self):
        for change, needle in (({"khoan": "3"}, "không được phép"), ({"diem": ["z"]}, "Điểm z"),
                               ({"dieu": "174"}, "phải là 173")):
            draft = valid_draft_dict()
            draft["charge"].update(change)
            with self.subTest(change=change):
                self.assertTrue(any(needle in e for e in errors_for(draft)), errors_for(draft))

    def test_value_band_decides_khoan(self):
        draft = valid_draft_dict()
        draft["measure_value"] = 80000000
        draft["evidence"][1]["value_vnd"] = 80000000
        draft["incident_summary"] = "{BI_CAO} lấy chiếc xe máy của {BI_HAI}."
        self.assertTrue(any("khoản phải là 2" in e for e in errors_for(draft)))
        draft["charge"].update({"khoan": "2", "diem": ["c"]})
        self.assertEqual(errors_for(draft), [])

    def test_value_out_of_learning_range(self):
        draft = valid_draft_dict()
        draft["measure_value"] = 300000000
        draft["evidence"][1]["value_vnd"] = 300000000
        draft["incident_summary"] = "Vụ việc."
        self.assertTrue(any("ngoài phạm vi" in e for e in errors_for(draft)))

    def test_measure_must_match_evidence(self):
        draft = valid_draft_dict()
        draft["evidence"][1]["value_vnd"] = 13000000
        self.assertTrue(any("dinh_gia" in e for e in errors_for(draft)))

    def test_money_in_text_must_match_declared_values(self):
        draft = valid_draft_dict()
        draft["facts"][0]["description"] = "{BI_CAO} bán xe được 9.000.000 đồng."
        self.assertTrue(any("9.000.000" in e for e in errors_for(draft)))

    def test_declared_extra_amount_is_accepted_and_checked(self):
        draft = valid_draft_dict()
        draft["facts"][0]["description"] = "{BI_CAO} định bán xe với giá 7.000.000 đồng."
        self.assertEqual(errors_for(draft), [])
        draft["extra_amounts"][0]["evidence_id"] = "E9"
        self.assertTrue(any("E9" in e for e in errors_for(draft)))

    def test_claimed_amount_in_inconsistency_is_declared_by_code(self):
        draft = valid_draft_dict()
        draft["pretrial_statements"][1]["inconsistencies"] = [
            {"text": "Bị hại khai ban đầu chiếc xe trị giá 15.000.000 đồng", "claimed_amount_vnd": 15000000}]
        self.assertEqual(errors_for(draft), [])
        draft["pretrial_statements"][1]["inconsistencies"][0]["claimed_amount_vnd"] = None
        self.assertTrue(any("15.000.000" in e for e in errors_for(draft)))

    def test_evidence_id_cited_as_fact_is_repaired_only_when_linked(self):
        draft = valid_draft_dict()
        draft["mitigating"][0]["fact_ids"] = ["E4"]          # E4 is linked to F2
        repaired = normalise_draft_dict(draft)
        self.assertEqual(repaired["mitigating"][0]["fact_ids"], ["F2"])
        self.assertEqual(errors_for(repaired), [])
        draft = valid_draft_dict()
        draft["mitigating"][0]["fact_ids"] = ["E1"]          # E1 has no fact link: still an error
        self.assertTrue(any("E1" in e for e in errors_for(normalise_draft_dict(draft))))
        draft = valid_draft_dict()
        draft["evidence"][3]["fact_id"] = "F9"
        self.assertTrue(any("F9" in e for e in errors_for(draft)))

    def test_minimum_requirements(self):
        draft = valid_draft_dict()
        draft["evidence"] = draft["evidence"][:3]
        draft["extra_amounts"] = []
        draft["indictment_text"] = "Truy tố bị cáo {BI_CAO} theo khoản 1 Điều 173 Bộ luật Hình sự."
        draft["pretrial_statements"][2]["summary"] = draft["pretrial_statements"][1]["summary"]
        errors = errors_for(draft)
        for needle in ("ít nhất 4 chứng cứ", "300 từ", "gần như trùng nhau"):
            self.assertTrue(any(needle in e for e in errors), needle)
        draft = valid_draft_dict()
        draft["pretrial_statements"] = draft["pretrial_statements"][:2]
        self.assertTrue(any("NLC_1 có 0" in e for e in errors_for(draft)))

    def test_knobs_are_enforced(self):
        draft = CaseDraft.model_validate(valid_draft_dict())
        knobs = valid_knobs()
        self.assertEqual(validate_case_draft(draft, valid_options(), get_crime("blhs_173"), pack_for("blhs_173"),
                                             knobs), [])
        for change, needle in (({"plea": "choi_toi"}, "defendant_plea"),
                               ({"aggravating_points": ["g"]}, "tăng nặng"),
                               ({"mitigating_points": ["a"]}, "giảm nhẹ"),
                               ({"has_compensation": False}, "compensation_vnd"),
                               ({"khoan": "2"}, "charge.khoan")):
            with self.subTest(change=change):
                errors = validate_case_draft(draft, valid_options(), get_crime("blhs_173"), pack_for("blhs_173"),
                                             knobs.model_copy(update=change))
                self.assertTrue(any(needle in e for e in errors), errors)

    def test_minor_age_and_minor_text(self):
        draft = valid_draft_dict()
        draft["witnesses"][0]["age"] = 17
        self.assertTrue(any("age" in e for e in errors_for(draft)))
        draft = valid_draft_dict()
        draft["facts"][0]["description"] = "Có một em 15 tuổi đứng xem."
        self.assertTrue(any("dưới 18" in e for e in errors_for(draft)))

    def test_minor_circumstance_point_forbidden(self):
        draft = valid_draft_dict()
        draft["charge"] = {"dieu": "134", "khoan": "1", "diem": ["c"], "crime_name": "x"}
        draft["measure_value"] = 15
        draft["evidence"][1] = {"id": "E2", "type": "giam_dinh", "description": "Giám định",
                                "value_vnd": None, "injury_percent": 15}
        draft["incident_summary"] = "{BI_CAO} gây thương tích cho {BI_HAI}."
        draft["indictment_text"] = "Truy tố theo khoản 1 Điều 134 Bộ luật Hình sự."
        draft["civil_claim"] = None
        draft["facts"][1]["description"] = "{BI_CAO} đến xin lỗi."
        errors = errors_for(draft, crime_key="blhs_134")
        self.assertTrue(any("người dưới 18 tuổi" in e for e in errors), errors)

    def test_dangling_references(self):
        draft = valid_draft_dict()
        draft["mitigating"][0]["fact_ids"] = ["F9"]
        draft["pretrial_statements"][0]["person_id"] = "NLC_2"
        draft["civil_claim"]["claimant_id"] = "XYZ"
        errors = errors_for(draft)
        for needle in ("F9", "NLC_2", "XYZ"):
            self.assertTrue(any(needle in e for e in errors), needle)

    def test_participants_must_match_options(self):
        draft = valid_draft_dict()
        options = valid_options().model_copy(update={"witness_count": 2})
        self.assertTrue(any("người làm chứng" in e for e in errors_for(draft, options)))

    def test_invented_name_place_and_placeholder(self):
        draft = valid_draft_dict()
        draft["facts"][0]["description"] = "Nguyễn Văn Tèo lấy xe của {BI_HAI} tại {NHA_RIENG}."
        draft["victim"]["residence_place"] = "Quận 1, TP Hồ Chí Minh"
        errors = errors_for(draft)
        for needle in ("tên người tự đặt", "residence_place", "NHA_RIENG"):
            self.assertTrue(any(needle in e for e in errors), needle)

    def test_indictment_citations_are_rule9_checked(self):
        draft = valid_draft_dict()
        draft["indictment_text"] += " Áp dụng Điều 326 Bộ luật Hình sự."
        self.assertTrue(any("indictment_text" in e and "unknown_pair" in e for e in errors_for(draft)))

    def test_circumstance_points_must_exist(self):
        draft = valid_draft_dict()
        draft["mitigating"][0]["diem"] = "z"
        draft["aggravating"] = [{"khoan": "1", "diem": "", "fact_ids": ["F1"]}]
        errors = errors_for(draft)
        self.assertTrue(any("điểm z" in e for e in errors))
        self.assertTrue(any("phải nêu điểm" in e for e in errors))


class KnobTests(unittest.TestCase):
    def test_knobs_respect_rules_over_many_seeds(self):
        seen_pleas, seen_aggravating, seen_mitigating = set(), 0, set()
        for key in CRIMES:
            crime, pack = get_crime(key), pack_for(key)
            for seed in range(60):
                knobs = choose_knobs(crime, pack, random.Random(seed))
                seen_pleas.add(knobs.plea)
                seen_aggravating += bool(knobs.aggravating_points)
                seen_mitigating.update(knobs.mitigating_points)
                with self.subTest(crime=key, seed=seed):
                    self.assertIn(knobs.khoan, crime.allowed_khoan)
                    self.assertTrue(set(knobs.aggravating_points) <= set(AGGRAVATING_POOL[crime.dieu]))
                    m = set(knobs.mitigating_points)
                    if knobs.plea != "nhan_toan_bo":
                        self.assertFalse(m & {"r", "s"})
                    if knobs.plea == "choi_toi":
                        self.assertNotIn("t", m)
                    if not knobs.has_compensation:
                        self.assertNotIn("b", m)
                    if "i" in m:
                        self.assertEqual(knobs.khoan, "1")
                        self.assertNotEqual(crime.dieu, "171")
                    if "e" in m:
                        self.assertEqual(crime.dieu, "134")
                    for p in m:
                        self.assertTrue(pack.get(BLHS_DOCUMENT, "51").has_diem("1", p))
        self.assertEqual(seen_pleas, {"nhan_toan_bo", "nhan_mot_phan", "choi_toi"})
        self.assertGreater(seen_aggravating, 0)
        self.assertGreater(len(seen_mitigating), 5)

    def test_aggravating_pool_avoids_minor_points(self):
        for key in CRIMES:
            self.assertFalse({"i", "o"} & set(AGGRAVATING_POOL[get_crime(key).dieu]))


class CasePromptTests(unittest.TestCase):
    def test_retry_prompt_carries_errors_previous_draft_and_constants(self):
        from app.prompts.trial_prompts import build_case_generation_prompt
        common = dict(constants=frame_text(valid_frame()), victim_present=True, places=["phường A, tỉnh X"],
                      incident_date="1", hearing_date="2", legal_text="L")
        first = build_case_generation_prompt(retry_errors=None, previous_draft="{}", **common)
        retry = build_case_generation_prompt(retry_errors=["lỗi A"], previous_draft='{"title": "T"}', **common)
        self.assertNotIn("BẢN TRƯỚC (JSON)", first)
        self.assertIn("lỗi A", retry)
        self.assertIn('{"title": "T"}', retry)
        self.assertIn("12.500.000 đồng", first)
        self.assertIn("điểm b, điểm s", first)
        self.assertIn("{BI_CAO}, {BI_HAI}, {NLC_1}", first)


class NameTests(unittest.TestCase):
    def test_unique_reproducible_and_exclusion(self):
        people = [(f"P{i}", "x", "nam" if i % 2 else "nu") for i in range(10)]
        first = assign_names(people, seed=3, excluded=frozenset())
        self.assertEqual(first, assign_names(people, seed=3, excluded=frozenset()))
        given = [p.name.split()[-1] for p in first.values()]
        self.assertEqual(len(given), len(set(given)))
        blocked = frozenset({name_hash(first["P0"].name)})
        self.assertNotEqual(assign_names(people, seed=3, excluded=blocked)["P0"].name, first["P0"].name)

    def test_render(self):
        case = valid_case_file()
        text = render("{BI_CAO} và {UNKNOWN}", case.participants)
        self.assertIn(case.participants["BI_CAO"].name, text)
        self.assertIn("{UNKNOWN}", text)


def verdict(**overrides) -> Verdict:
    base = {"guilty": True, "dieu": "173", "khoan": "1", "diem": [], "penalty_type": "tu", "penalty_months": 12,
            "fine_vnd": None, "suspended": False, "probation_months": None, "applies_dieu_54": False,
            "mitigating": [{"khoan": "1", "diem": "s", "fact_ids": ["F2"]}], "aggravating": [],
            "civil_amount_vnd": 2000000, "reasoning_summary": "..."}
    base.update(overrides)
    return Verdict.model_validate(base)


class VerdictGuardTests(unittest.TestCase):
    def setUp(self):
        self.case = valid_case_file()
        self.pack = pack_for("blhs_173")

    def check(self, **overrides):
        return check_verdict(verdict(**overrides), self.case, self.pack)

    def test_penalty_frames_parse_from_real_text(self):
        art173 = self.pack.get(BLHS_DOCUMENT, "173")
        frame = parse_penalty_frame(art173.khoans["1"])
        self.assertEqual((frame.prison_min_months, frame.prison_max_months, frame.non_custodial_max_months),
                         (6, 36, 36))
        frame2 = parse_penalty_frame(art173.khoans["2"])
        self.assertEqual((frame2.prison_min_months, frame2.prison_max_months), (24, 84))
        self.assertIsNone(parse_penalty_frame(art173.khoans["5"]))  # supplementary fine only
        frame171 = parse_penalty_frame(pack_for("blhs_171").get(BLHS_DOCUMENT, "171").khoans["1"])
        self.assertEqual((frame171.prison_min_months, frame171.prison_max_months), (12, 60))

    def test_within_frame_passes(self):
        result = self.check()
        self.assertEqual((result.errors, result.flags), ([], []))

    def test_above_and_below_frame(self):
        self.assertTrue(self.check(penalty_months=40).errors)
        self.assertTrue(self.check(penalty_months=3).errors)

    def test_below_frame_with_dieu_54(self):
        two = [{"khoan": "1", "diem": "s", "fact_ids": ["F2"]}, {"khoan": "1", "diem": "b", "fact_ids": ["F2"]}]
        self.assertEqual(self.check(penalty_months=3, applies_dieu_54=True, mitigating=two).errors, [])
        self.assertTrue(self.check(penalty_months=3, applies_dieu_54=True).errors)  # one mitigating only

    def test_limits_of_trial_dieu_298(self):
        self.assertTrue(self.check(dieu="174").errors)
        self.assertTrue(self.check(khoan="2", penalty_months=30).errors)  # heavier than charged

    def test_suspended_sentence_rules(self):
        self.assertEqual(self.check(suspended=True, probation_months=24).errors, [])
        self.assertTrue(self.check(suspended=True, probation_months=6).errors)
        draft = valid_draft_dict()
        draft["charge"].update({"khoan": "2", "diem": ["a"]})
        case2 = valid_case_file(draft=draft)
        result = check_verdict(verdict(khoan="2", diem=["a"], penalty_months=48, suspended=True, probation_months=24),
                               case2, self.pack)
        self.assertTrue(any("Án treo" in e for e in result.errors))

    def test_non_custodial_only_where_frame_allows(self):
        self.assertEqual(self.check(penalty_type="cai_tao_khong_giam_giu", penalty_months=12).errors, [])
        draft = valid_draft_dict()
        draft["charge"].update({"khoan": "2", "diem": ["a"]})
        result = check_verdict(verdict(khoan="2", diem=["a"], penalty_type="cai_tao_khong_giam_giu",
                                       penalty_months=12), valid_case_file(draft=draft), self.pack)
        self.assertTrue(result.errors)

    def test_unparseable_frame_is_flagged_not_blocked(self):
        pack = copy.copy(self.pack)
        pack.articles = dict(self.pack.articles)
        original = self.pack.get(BLHS_DOCUMENT, "173")
        khoans = dict(original.khoans)
        khoans["1"] = Khoan("1", "1. Người nào trộm cắp tài sản thì bị xử lý theo quy định.", frozenset())
        pack.articles[(BLHS_DOCUMENT, "173")] = type(original)(
            original.source_document, original.dieu_number, original.dieu_title, original.text, khoans,
            original.cross_refs)
        result = check_verdict(verdict(), self.case, pack)
        self.assertEqual((result.errors, result.flags), ([], ["penalty_unchecked"]))

    def test_verdict_evidence_id_repaired_only_when_linked(self):
        from app.services.trial_verdict_guard import normalise_verdict
        linked = normalise_verdict(verdict(mitigating=[{"khoan": "1", "diem": "s", "fact_ids": ["E4"]}]), self.case)
        self.assertEqual(linked.mitigating[0].fact_ids, ["F2"])
        self.assertEqual(check_verdict(linked, self.case, self.pack).errors, [])
        unlinked = normalise_verdict(verdict(mitigating=[{"khoan": "1", "diem": "s", "fact_ids": ["E1"]}]), self.case)
        self.assertTrue(check_verdict(unlinked, self.case, self.pack).errors)

    def test_acquittal_and_bad_references(self):
        self.assertEqual(self.check(guilty=False, penalty_type="khong", penalty_months=None).errors, [])
        self.assertTrue(self.check(mitigating=[{"khoan": "1", "diem": "s", "fact_ids": ["F9"]}]).errors)
        self.assertTrue(self.check(penalty_type="khong").errors)



def _strip_diacritics(text: str) -> str:
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in text if not unicodedata.combining(c))


def _create(answers: list, frame=None) -> tuple[ScriptedRecorder, object]:
    recorder = ScriptedRecorder(answers=[a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)
                                         for a in answers])
    creation = asyncio.run(create_case(valid_options(), SimpleNamespace(trial_court_name=None), None, recorder,
                                       pack=pack_for("blhs_173"), seed=1, knobs=valid_knobs(),
                                       frame=frame or valid_frame()))
    return recorder, creation


class FrameTests(unittest.TestCase):
    """Chặng 3H: code fixes the case frame, the model fills free text into a per-case schema."""

    def test_fill_of_valid_draft_round_trips_and_passes(self):
        recorder, creation = _create([fill_from_draft(valid_draft_dict())])
        self.assertEqual(creation.attempts, 1)
        draft = creation.case.draft
        self.assertEqual([s.person_id for s in draft.pretrial_statements], ["BI_CAO", "BI_HAI", "NLC_1"])
        self.assertEqual((draft.measure_value, draft.compensation_vnd, draft.charge.khoan), (12_500_000, 2_000_000, "1"))

    def test_frame_owns_ids_order_charge_and_constants(self):
        fill = fill_from_draft(valid_draft_dict())
        fill["defendant"]["id"] = "NLC_1"                         # the model cannot misplace people
        draft = fill_to_draft(fill, valid_frame())
        self.assertEqual([draft["defendant"]["id"], draft["victim"]["id"], draft["witnesses"][0]["id"]],
                         ["BI_CAO", "BI_HAI", "NLC_1"])
        self.assertEqual(draft["charge"], {"dieu": "173", "khoan": "1", "diem": [], "crime_name": "Tội trộm cắp tài sản"})
        self.assertEqual(draft["defendant_plea"], "nhan_toan_bo")
        self.assertEqual([(m["diem"], m["fact_ids"]) for m in draft["mitigating"]], [("b", ["F2"]), ("s", ["F2"])])

    def test_statement_sentences_are_joined_and_old_thresholds_still_apply(self):
        fill = fill_from_draft(valid_draft_dict())
        fill["victim"]["pretrial_statement"]["sentences"] = ["Tôi mất xe.", "Tôi báo công an.", "Tôi đề nghị xử lý."]
        draft = CaseDraft.model_validate(normalise_draft_dict(fill_to_draft(fill, valid_frame())))
        self.assertEqual(draft.pretrial_statements[1].summary, "Tôi mất xe. Tôi báo công an. Tôi đề nghị xử lý.")
        errors = validate_case_draft(draft, valid_options(), get_crime("blhs_173"), pack_for("blhs_173"), valid_knobs())
        self.assertEqual([error_label(e) for e in errors], ["statement_words"])   # 25-word minimum unchanged

    def test_measure_evidence_takes_the_frame_value_but_text_is_still_checked(self):
        fill = fill_from_draft(valid_draft_dict())
        next(e for e in fill["evidence"] if e["type"] == "dinh_gia")["value_vnd"] = 13_000_000
        draft = fill_to_draft(fill, valid_frame())
        self.assertEqual(next(e for e in draft["evidence"] if e["type"] == "dinh_gia")["value_vnd"], 12_500_000)
        fill["incident_summary"] += " Chiếc xe trị giá 13.000.000 đồng."
        self.assertIn("money_mismatch", [error_label(e) for e in errors_for(
            normalise_draft_dict(fill_to_draft(fill, valid_frame())))])

    def test_schema_built_per_case(self):
        frame = build_frame(get_crime("blhs_134"), CaseOptions(crime_key="blhs_134", user_role="ksv", witness_count=2,
                                                               has_related_party=True),
                            CaseKnobs(khoan="2", plea="choi_toi", has_compensation=False, aggravating_points=["i"],
                                      mitigating_points=["s"]), random.Random(4))
        schema = fill_schema(frame)
        self.assertEqual((schema["properties"]["witnesses"]["minItems"], schema["properties"]["witnesses"]["maxItems"]),
                         (2, 2))
        self.assertIn("related_party", schema["required"])
        self.assertEqual(schema["properties"]["mitigating_facts"]["required"], ["s"])
        self.assertEqual(schema["properties"]["aggravating_facts"]["required"], ["i"])
        self.assertEqual(schema["properties"]["evidence"]["minItems"], 4)
        statement = schema["properties"]["defendant"]["properties"]["pretrial_statement"]
        self.assertEqual(statement["properties"]["sentences"]["minItems"], 3)
        self.assertNotIn("measure_value", schema["properties"])
        self.assertEqual((frame.diem, frame.person_ids[-1]), (("a",), "NLQ"))
        self.assertTrue(31 <= frame.measure_value <= 60)

    def test_frame_values_respect_the_legal_bands(self):
        for key in CRIMES:
            crime = get_crime(key)
            for khoan in crime.allowed_khoan:
                for seed in range(30):
                    knobs = CaseKnobs(khoan=khoan, plea="nhan_toan_bo", has_compensation=True, aggravating_points=[],
                                      mitigating_points=[])
                    frame = build_frame(crime, valid_options(), knobs, random.Random(seed))
                    band = next(b for b in crime.bands if b.low <= frame.measure_value
                                and (b.high is None or frame.measure_value < b.high))
                    self.assertTrue(band.allowed and khoan in band.required_khoan, (key, khoan, frame.measure_value))
                    if crime.measure == "value_vnd":
                        self.assertTrue(0 < frame.compensation_vnd <= frame.measure_value)


class CaseRetryTests(unittest.TestCase):
    def test_unaccented_fill_is_regenerated_from_scratch(self):
        draft = valid_draft_dict()
        draft["incident_summary"] = _strip_diacritics(draft["incident_summary"] + " " + STATEMENT_BI_HAI)
        draft["indictment_text"] = _strip_diacritics(draft["indictment_text"])
        recorder, creation = _create([fill_from_draft(draft), fill_from_draft(valid_draft_dict())])
        self.assertEqual(creation.attempts, 2)
        self.assertTrue(any(DIACRITIC_ERROR in e for e in creation.errors_per_attempt[0]))
        self.assertEqual(recorder.prompts[0], recorder.prompts[1])     # same fresh prompt

    def test_other_errors_are_fixed_on_the_previous_fill(self):
        draft = valid_draft_dict()
        draft["evidence"] = draft["evidence"][:3]
        recorder, creation = _create([fill_from_draft(draft), fill_from_draft(valid_draft_dict())])
        self.assertEqual(creation.attempts, 2)
        self.assertIn("=== BẢN TRƯỚC (JSON) ===", recorder.prompts[1])
        self.assertEqual(recorder.records[0].guard_violations, ["evidence_min"])

    def test_broken_fill_is_a_schema_error_not_a_crash(self):
        recorder, creation = _create(['{"defendant": "x"}', fill_from_draft(valid_draft_dict())])
        self.assertEqual(recorder.records[0].guard_violations, ["schema"])
        self.assertEqual(creation.attempts, 2)

    def test_third_call_only_within_time_budget(self):
        bad = fill_from_draft({**valid_draft_dict(), "evidence": valid_draft_dict()["evidence"][:3]})
        recorder, creation = _create([bad, bad, fill_from_draft(valid_draft_dict())])
        self.assertEqual(creation.attempts, 3)
        with mock.patch.object(trial_case_service, "THIRD_ATTEMPT_MAX_ELAPSED", -1.0):
            with self.assertRaises(CaseGenerationFailed) as failure:
                _create([bad, bad, fill_from_draft(valid_draft_dict())])
        self.assertEqual(len(failure.exception.errors), 2)

    def test_prompt_asks_for_diacritics(self):
        self.assertIn("CÓ DẤU", CASE_GENERATION_SYSTEM_PROMPT)

    def test_case_model_override_reaches_the_call(self):
        recorder = ScriptedRecorder(answers=[json.dumps(fill_from_draft(valid_draft_dict()), ensure_ascii=False)])
        seen = []
        original = recorder.call

        async def call(*args, **kwargs):
            seen.append(kwargs.get("model"))
            return await original(*args, **kwargs)
        recorder.call = call
        asyncio.run(create_case(valid_options(), SimpleNamespace(trial_court_name=None, trial_case_model="m-x"), None,
                                recorder, pack=pack_for("blhs_173"), seed=1, knobs=valid_knobs(), frame=valid_frame()))
        self.assertEqual(seen, ["m-x"])


class ErrorLabelTests(unittest.TestCase):
    def test_error_labels(self):
        cases = {
            "incident_summary: số tiền 99.000.000 đồng không khớp giá trị nào đã khai (x)": "money_mismatch",
            "Mỗi người phải có đúng một lời khai giai đoạn điều tra; NLC_1 có 0": "statement_count",
            "BI_CAO.statement_summary: có tên người tự đặt; chỉ dùng placeholder như {BI_CAO}": "invented_name",
            "Lời khai của BI_HAI phải có ít nhất 25 từ": "statement_words",
            "Phải có ít nhất 4 chứng cứ (evidence), hiện có 3": "evidence_min",
            "JSON không hợp lệ theo schema: ValidationError": "schema",
        }
        for message, label in cases.items():
            self.assertEqual(error_label(message), label, message)


if __name__ == "__main__":
    unittest.main()
