"""Unit tests for chặng 3D: panel anonymisation, long-speech layout, indictment sections and the
biên bản laid out after Mẫu 22-HS. No Gemini call."""
from __future__ import annotations

import asyncio
import json
import re
import unicodedata
import unittest
from dataclasses import replace
from datetime import datetime, timezone

from app.models.trial import CaseDraft, Participant
from app.services.trial_anonymise import anonymise_case_view, anonymise_text, display_names
from app.services.trial_case_validator import lacks_diacritics, normalise_draft_dict, validate_case_draft
from app.services.trial_config import DEFAULT_COURT_NAME, LEGACY_COURT_PLACEHOLDER, get_crime, procuracy_name
from app.services.trial_names import assign_names, short_name
from app.services.trial_record import (
    NOTICE_LINE,
    OBSERVER_NOTE,
    build_record,
    indictment_reference,
    render_record_text,
)
from app.services.trial_session_service import student_case_view
from app.services.trial_text_format import (
    INDICTMENT_SECTIONS,
    LONG_TEXT_MIN_CHARS,
    format_speech,
    format_utterance,
    indictment_sections,
    paragraphs,
)
from app.services.trial_turn_service import Utterance, run_ai_turn
from tests.test_trial_turns import make_ctx
from tests.trial_fixtures import (
    STATEMENT_BI_CAO,
    pack_for,
    valid_case_file,
    valid_draft_dict,
    valid_knobs,
    valid_options,
)

PEOPLE = {
    "BI_CAO": "Trần Đức Hùng", "BI_HAI": "Huỳnh Hữu Việt", "NLC_1": "Phạm Minh Tuấn", "NLQ": "Lê Hồng Chi",
    "CHU_TOA": "Nguyễn Văn An", "HOI_THAM_1": "Đỗ Công Bình", "HOI_THAM_2": "Ngô Thị Hoa",
    "THU_KY": "Võ Thị Lan", "KSV": "Đặng Quốc Sơn", "LUAT_SU": "Bùi Thanh Long",
}
PARTICIPANTS = {pid: Participant(id=pid, role=pid, name=name) for pid, name in PEOPLE.items()}
HIDDEN = ("BI_CAO", "BI_HAI", "NLC_1", "NLQ")


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text)


class AnonymisationTests(unittest.TestCase):
    def test_short_form(self):
        self.assertEqual(short_name("Trần Đức Hùng"), "Trần Đức H")
        self.assertEqual(short_name("Huỳnh Hữu Việt"), "Huỳnh Hữu V")
        self.assertEqual(short_name("Phạm Minh Tuấn"), "Phạm Minh T")
        self.assertEqual(short_name("Lê Hồng Chi"), "Lê Hồng C")

    def test_full_names_any_case(self):
        text = "Bị cáo Trần Đức Hùng khai với TRẦN ĐỨC HÙNG và trần đức hùng rằng Huỳnh Hữu Việt có mặt."
        out = anonymise_text(text, PARTICIPANTS)
        self.assertEqual(out, "Bị cáo Trần Đức H khai với Trần Đức H và Trần Đức H rằng Huỳnh Hữu V có mặt.")

    def test_lone_given_name_only_after_address_word(self):
        cases = {
            "Bị cáo Hùng khai nhận.": "Bị cáo H khai nhận.",
            "Lời khai của bị hại Việt.": "Lời khai của bị hại V.",
            "anh Tuấn chứng kiến, chị Chi nhận xe.": "anh T chứng kiến, chị C nhận xe.",
            "người làm chứng Tuấn": "người làm chứng T",
            "Hùng nói rằng": "Hùng nói rằng",                       # no address word: left as is
            "Cộng hòa xã hội chủ nghĩa Việt Nam": "Cộng hòa xã hội chủ nghĩa Việt Nam",
            "người anh hùng của làng": "người anh hùng của làng",   # common word, lower case
            "ông Việt Nam": "ông Việt Nam",                          # longer proper noun
            "bị hại Việt, sinh năm": "bị hại V, sinh năm",
        }
        for text, expected in cases.items():
            self.assertEqual(anonymise_text(text, PARTICIPANTS), expected, text)

    def test_nested_names_in_one_text(self):
        text = ("Tại nhà Lê Hồng Chi, Trần Đức Hùng đưa cho Phạm Minh Tuấn chiếc xe của Huỳnh Hữu Việt; "
                "sau đó bị cáo Hùng gọi anh Tuấn.")
        out = anonymise_text(text, PARTICIPANTS)
        for pid in HIDDEN:
            self.assertNotIn(PEOPLE[pid], out)
        self.assertIn("Lê Hồng C", out)
        self.assertIn("bị cáo H gọi anh T", out)

    def test_court_side_names_kept(self):
        text = ("Chủ tọa Nguyễn Văn An, Hội thẩm Đỗ Công Bình, Ngô Thị Hoa, Thư ký Võ Thị Lan, Kiểm sát viên "
                "Đặng Quốc Sơn, luật sư Bùi Thanh Long; ông An hỏi bà Lan.")
        self.assertEqual(anonymise_text(text, PARTICIPANTS), text)
        names = display_names(PARTICIPANTS)
        for pid in ("CHU_TOA", "HOI_THAM_1", "HOI_THAM_2", "THU_KY", "KSV", "LUAT_SU"):
            self.assertEqual(names[pid], PEOPLE[pid])
        self.assertEqual(names["BI_CAO"], "Trần Đức H")

    def test_case_view_has_no_hidden_full_name(self):
        case = valid_case_file()
        view = student_case_view(case)
        dumped = json.dumps(view, ensure_ascii=False)
        for pid, person in case.participants.items():
            if pid in HIDDEN:
                self.assertNotIn(person.name, dumped)
                self.assertIn(short_name(person.name), dumped)
        self.assertEqual(view["defendant"]["name"], short_name(case.participants["BI_CAO"].name))
        self.assertEqual(view["display_names"]["KSV"], case.participants["KSV"].name)
        self.assertNotIn("{BI_CAO}", dumped)

    def test_view_function_is_single_entry_point(self):
        view = {"incident_summary": "Trần Đức Hùng lấy xe", "defendant": {"id": "BI_CAO"},
                "witnesses": [{"id": "NLC_1"}], "nested": [{"deep": ["bị hại Việt"]}]}
        out = anonymise_case_view(view, PARTICIPANTS)
        self.assertEqual(out["incident_summary"], "Trần Đức H lấy xe")
        self.assertEqual(out["witnesses"][0]["name"], "Phạm Minh T")
        self.assertEqual(out["nested"][0]["deep"], ["bị hại V"])

    def test_short_forms_unique_within_a_case(self):
        people = [("CHU_TOA", "x", "nam"), ("BI_CAO", "x", "nam"), ("BI_HAI", "x", "nam"),
                  ("NLC_1", "x", "nam"), ("NLC_2", "x", "nam"), ("NLQ", "x", "nam")]
        for seed in range(400):
            names = assign_names(people, seed, excluded=frozenset())
            shorts = [short_name(names[pid].name) for pid in ("BI_CAO", "BI_HAI", "NLC_1", "NLC_2", "NLQ")]
            self.assertEqual(len(shorts), len(set(shorts)), seed)


MARKDOWN_SPEECH = ("**Về hành vi phạm tội:**   bị cáo đã chiếm đoạt chiếc xe.\n\n\n\n"
                   "### Về chứng cứ:\n* Kết luận định giá\n*   Biên bản thu giữ\n• Lời khai người làm chứng\n\n"
                   "  Đề nghị xử phạt bị cáo   từ 12 đến 18 tháng tù.  ")


class FormatTests(unittest.TestCase):
    def test_markdown_removed_and_layout_normalised(self):
        out = format_speech(MARKDOWN_SPEECH, multi_paragraph=True)
        self.assertNotIn("*", out)
        self.assertNotIn("#", out)
        self.assertNotIn("\n\n\n", out)
        self.assertEqual(out.splitlines()[0], "Về hành vi phạm tội: bị cáo đã chiếm đoạt chiếc xe.")
        self.assertIn("Về chứng cứ:\n- Kết luận định giá\n- Biên bản thu giữ\n- Lời khai người làm chứng", out)
        self.assertEqual(len(paragraphs(out)), 3)
        self.assertEqual(_words(out), _words(MARKDOWN_SPEECH))   # words and numbers unchanged

    def test_short_text_flattened_to_one_paragraph(self):
        out = format_speech("Dạ,\n\n**tôi** không nhớ\n- rõ ạ.", multi_paragraph=False)
        self.assertEqual(out, "Dạ, tôi không nhớ rõ ạ.")

    def test_segment_utterance_keeps_paragraphs_only_when_long(self):
        short = "Đoạn một.\n\nĐoạn hai."
        self.assertEqual(format_utterance(short), "Đoạn một. Đoạn hai.")
        long = ("Về quyền của bị cáo: " + "bị cáo có quyền trình bày ý kiến. " * 12 + "\n\n"
                "Về quyền của bị hại: " + "bị hại có quyền đề nghị bồi thường. " * 12)
        self.assertGreater(len(long), LONG_TEXT_MIN_CHARS)
        self.assertEqual(len(paragraphs(format_utterance(long))), 2)

    def test_long_speech_is_formatted_before_guard(self):
        speech = json.dumps({"text": MARKDOWN_SPEECH}, ensure_ascii=False)
        ctx = make_ctx([speech], role="luat_su")
        ctx.state = replace(ctx.state, current_step=6, slot_index=0, pending_ai=True)
        produced = asyncio.run(run_ai_turn(ctx))
        self.assertEqual([u.speaker_id for u in produced], ["KSV"])
        self.assertNotIn("**", produced[0].text)
        self.assertEqual(len(paragraphs(produced[0].text)), 3)
        self.assertEqual([r.accepted for r in ctx.recorder.records], [True])


STRUCTURED_INDICTMENT = (
    "VIỆN KIỂM SÁT NHÂN DÂN [GIẢ ĐỊNH]\nSố: 15/CT-VKS-HS\nNgày 5 tháng 9 năm 2026\n\n"
    "I. Nội dung vụ án\n{BI_CAO} lấy xe.\n\n**II. Hành vi phạm tội và chứng cứ**\n* Kết luận định giá\n\n"
    "III. NHÂN THÂN VÀ TÌNH TIẾT\nBị cáo chưa có tiền án.\n\nIV. Kết luận và truy tố\nTruy tố bị cáo."
)


class IndictmentTests(unittest.TestCase):
    def test_sections_counted_on_own_lines(self):
        cleaned = format_speech(STRUCTURED_INDICTMENT, multi_paragraph=True)
        self.assertEqual(indictment_sections(cleaned), list(INDICTMENT_SECTIONS))
        self.assertEqual(indictment_sections("Nội dung I. Nội dung vụ án nằm giữa câu."), [])

    def test_normaliser_formats_indictment_without_changing_words(self):
        data = valid_draft_dict()
        data["indictment_text"] = STRUCTURED_INDICTMENT
        out = normalise_draft_dict(data)["indictment_text"]
        self.assertIn("\n- Kết luận định giá", out)
        self.assertNotIn("*", out)
        self.assertEqual(_words(out), _words(STRUCTURED_INDICTMENT))

    def test_reference_read_from_header(self):
        self.assertEqual(indictment_reference(STRUCTURED_INDICTMENT), ("15/CT-VKS-HS", "ngày 5 tháng 9 năm 2026"))
        self.assertEqual(indictment_reference("Viện kiểm sát nhân dân phường A\nSố: 01/CT-VKS-A\nNgày: 20/10/2026"),
                         ("01/CT-VKS-A", "ngày 20 tháng 10 năm 2026"))
        self.assertEqual(indictment_reference("Viện kiểm sát truy tố bị cáo."), (None, None))

    def test_text_without_diacritics_is_rejected(self):
        def strip(text: str) -> str:
            text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
            return "".join(c for c in text if not unicodedata.combining(c))
        self.assertFalse(lacks_diacritics(STATEMENT_BI_CAO))
        self.assertTrue(lacks_diacritics(strip(STATEMENT_BI_CAO)))
        self.assertFalse(lacks_diacritics("OK"))                    # too short to judge
        data = valid_draft_dict()
        data["indictment_text"] = strip(data["indictment_text"])
        draft = CaseDraft.model_validate(normalise_draft_dict(data))
        errors = validate_case_draft(draft, valid_options(), get_crime("blhs_173"), pack_for("blhs_173"),
                                     valid_knobs())
        self.assertIn("indictment_text phải viết tiếng Việt có dấu đầy đủ", errors)


def _transcript() -> list[Utterance]:
    rows = [(1, "THU_KY", False, "procedural", "Báo cáo sự có mặt."),
            (2, "CHU_TOA", False, "speech", "Khai mạc phiên tòa xét xử {BI_CAO}."),
            (2, "CHU_TOA", False, "notice", "Đề nghị giữ trật tự, chưa chuyển bước."),
            (3, "KSV", True, "speech", "Bản cáo trạng do người học đọc."),
            (5, "BI_CAO", False, "speech", "Dạ, tôi khai đúng."),
            (6, "KSV", False, "speech", "Về hành vi phạm tội:\n\nĐề nghị xử phạt."),
            (8, "LUAT_SU", False, "speech", "Đối đáp."),
            (9, "BI_CAO", False, "speech", "Xin giảm nhẹ."),
            (10, "CHU_TOA", False, "procedural", "Hội đồng xét xử vào phòng nghị án."),
            (11, "CHU_TOA", False, "speech", "NHÂN DANH NƯỚC ... QUYẾT ĐỊNH tuyên bố bị cáo phạm tội.")]
    return [Utterance(i, step, sp, user, kind, text, [], None) for i, (step, sp, user, kind, text) in enumerate(rows, 1)]


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.case = valid_case_file()
        start = datetime(2026, 10, 19, 1, 5, tzinfo=timezone.utc)
        end = datetime(2026, 10, 19, 2, 40, tzinfo=timezone.utc)
        self.record = build_record(self.case, _transcript(), start, end)
        self.text = render_record_text(self.record)

    def test_form_structure(self):
        r = self.record
        self.assertEqual((r.title, r.subtitle), ("BIÊN BẢN", "PHIÊN TÒA HÌNH SỰ SƠ THẨM"))
        self.assertEqual([s.heading for s in r.sections], [
            "I. Những người tiến hành tố tụng", "II. Những người tham gia tố tụng",
            "III. Phần thủ tục bắt đầu phiên tòa", "IV. Phần tranh tụng tại phiên tòa"])
        debate = r.sections[3]
        self.assertEqual([[e.step for e in s.entries] for s in debate.subsections], [[3], [5], [6, 8], [9]])
        self.assertEqual([e.step for e in r.sections[2].entries], [1, 2])
        self.assertEqual([s.name for s in r.signatures],
                         [self.case.participants["THU_KY"].name, self.case.participants["CHU_TOA"].name])

    def test_times_from_session_and_blank_when_no_data(self):
        opening = {f.label: f for f in self.record.opening}
        self.assertEqual(opening["Vào hồi"].value, "08 giờ 05 phút ngày 19 tháng 10 năm 2026")
        self.assertTrue(opening["Vào hồi"].simulated)
        self.assertIsNone(opening["Tại Cáo trạng số"].value)       # fixture indictment has no header
        closing = {f.label: f for f in self.record.closing}
        self.assertEqual(closing["Phiên tòa kết thúc vào hồi"].value, "09 giờ 40 phút ngày 19 tháng 10 năm 2026")
        self.assertIn("Tại Cáo trạng số: ......", self.text)

    def test_notices_and_judgment_text_excluded_full_names_kept(self):
        self.assertNotIn("giữ trật tự, chưa chuyển bước", self.text)
        # The judgment is only in the appendix, after the signatures (form guidance 29).
        self.assertGreater(self.text.index("NHÂN DANH"), self.text.index("THẨM PHÁN - CHỦ TỌA PHIÊN TÒA"))
        self.assertEqual([e.step for e in self.record.appendix[0].entries], [11])
        self.assertIn("PHỤ LỤC", self.record.appendix[0].heading)
        self.assertIn("Hội đồng xét xử tuyên án theo bản án đã được Hội đồng xét xử thông qua", self.text)
        self.assertIn(self.case.participants["BI_CAO"].name, self.text)
        self.assertNotIn("{BI_CAO}", self.text)
        self.assertEqual(self.text.count(NOTICE_LINE), 2)
        self.assertTrue(self.text.startswith(NOTICE_LINE) and self.text.endswith(NOTICE_LINE))

    def test_prosecutor_office(self):
        self.assertEqual(procuracy_name("Tòa án nhân dân khu vực 1 - tỉnh X"),
                         "Viện kiểm sát nhân dân khu vực 1 - tỉnh X")
        # No "[giả định]" placeholder any more: unset or legacy names use the default court.
        self.assertEqual(procuracy_name(DEFAULT_COURT_NAME), "Viện kiểm sát nhân dân khu vực 1, tỉnh X")
        self.assertEqual(procuracy_name(LEGACY_COURT_PLACEHOLDER), "Viện kiểm sát nhân dân khu vực 1, tỉnh X")

    def test_record_uses_configured_offices_and_marks_observer_sessions(self):
        fields = {f.label: f for f in self.record.opening}
        self.assertEqual(self.record.court_name, self.case.court.name)
        self.assertEqual(fields["Bị Viện kiểm sát"].value, procuracy_name(self.case.court.name))
        self.assertFalse(fields["Bị Viện kiểm sát"].simulated)
        self.assertNotIn("[giả định]", self.text)
        self.assertEqual(self.record.preamble, [])
        legacy = self.case.model_copy(update={"court": self.case.court.model_copy(
            update={"name": LEGACY_COURT_PLACEHOLDER})})
        observed = build_record(legacy, [], None, None, observer=True)
        self.assertEqual(observed.court_name, DEFAULT_COURT_NAME)
        self.assertEqual(observed.preamble, [OBSERVER_NOTE])
        text = render_record_text(observed)
        self.assertTrue(text.startswith(NOTICE_LINE + "\n" + OBSERVER_NOTE))
        self.assertNotIn("chờ nhóm luật", text)


if __name__ == "__main__":
    unittest.main()
