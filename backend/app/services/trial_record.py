"""Biên bản phiên tòa, built by CODE from the stored case and utterances (design doc Mục 7; layout
of Mẫu số 22-HS, Nghị quyết 05/2017/NQ-HĐTP, chặng 3D).

Content rules (BLTTHS Điều 258): time and place, everyone taking part, every question, answer and
statement in order, the end time and the signatures of Thư ký and Chủ tọa. No LLM call: the record
is the transcript arranged into the form, so it can never contain a line nobody said.
- Only data the system holds is used (case file, participants, utterances, session timestamps).
  A field with no data is None, which the frontend shows as the form's dotted blank; a value the
  simulation assigns by code (hearing date, venue, "công khai") is flagged
  `simulated`.
- Full names everywhere (the panel's anonymisation does not apply here).
- Order-keeping notices (kind="notice") are not part of the record.
- Tuyên án: per guidance (29) of the form, the record says the panel pronounced the judgment
  adopted in deliberation; the judgment text is added verbatim as an appendix outside the form.
- IV.2 and IV.3 use the clerk's summary (trial_record_summary, chặng 3E) when one passed its
  checks; otherwise they are verbatim. IV.1 and IV.4 are always verbatim.
- The simulation notice is inserted by code at the top and bottom of the text rendering.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from app.models.trial import TRIAL_DISCLAIMER, CaseFile, Participant
from app.models.trial_api import (
    TrialRecordEntry,
    TrialRecordField,
    TrialRecordOut,
    TrialRecordSection,
    TrialRecordSignature,
)
from app.services.trial_config import DEFAULT_COURT_NAME, LEGACY_COURT_PLACEHOLDER, procuracy_name
from app.services.trial_names import render
from app.services.trial_state_machine import ROLE_LABELS
from app.services.trial_turn_service import Utterance, role_of

VIETNAM_TZ = timezone(timedelta(hours=7))
NOTICE_LINE = f"*** {TRIAL_DISCLAIMER.upper()} ***"
FORM_REFERENCE = ("Mẫu số 22-HS (Ban hành kèm theo Nghị quyết số 05/2017/NQ-HĐTP ngày 19 tháng 9 năm 2017 "
                  "của Hội đồng Thẩm phán Tòa án nhân dân tối cao)")
BLANK = "......"
# Outside the form, first line of a Người xem record (design doc Mục 11.1.5).
OBSERVER_NOTE = "Phiên tòa mô phỏng do hệ thống đóng mọi vai; người học quan sát."

# Hearing steps -> numbered items of form part IV ("Phần tranh tụng tại phiên tòa"); the last
# element is the record_summary key for the items that may be summarised.
DEBATE_ITEMS: tuple[tuple[str, tuple[int, ...], str | None], ...] = (
    ("1. Kiểm sát viên công bố bản cáo trạng và trình bày ý kiến bổ sung (nếu có)", (3,), None),
    ("2. Hỏi và trả lời tại phiên tòa", (4, 5), "iv2"),
    ("3. Tranh luận tại phiên tòa", (6, 7, 8), "iv3"),
    ("4. Lời nói sau cùng của bị cáo", (9,), None),
)
JUDGMENT_STEP = 11
APPENDIX_HEADING = "PHỤ LỤC (ngoài Mẫu số 22-HS): Lời tuyên án"
APPENDIX_NOTE = "Phụ lục do hệ thống mô phỏng đính kèm, chép nguyên văn lời tuyên án tại phiên tòa."
OPENING_STEPS = (1, 2)
DELIBERATION_NOTES = (
    "Hội đồng xét xử vào phòng nghị án để nghị án.",
    "Hội đồng xét xử vào phòng xử án và tuyên án.",
    "Hội đồng xét xử tuyên án theo bản án đã được Hội đồng xét xử thông qua tại phòng nghị án.",
)

_INDICTMENT_NUMBER = re.compile(r"Số\s*:?\s*([0-9A-Za-zĐđ][\w/.\-]*)")
_VN_DATE = re.compile(r"ngày\s*:?\s*(\d{1,2})(?:\s+tháng\s+|/)(\d{1,2})(?:\s+năm\s+|/)(\d{4})", re.IGNORECASE)


def _honorific(p: Participant) -> str:
    return {"nam": "Ông", "nu": "Bà"}.get(p.gender or "", "Ông (Bà)")


def _named(p: Participant) -> str:
    return f"{_honorific(p)} {p.name}"


def _vn_datetime(date_ddmmyyyy: str, moment: datetime) -> str:
    day, month, year = date_ddmmyyyy.split("/")
    return f"{moment:%H} giờ {moment:%M} phút ngày {int(day)} tháng {int(month)} năm {year}"


def court_office(case: CaseFile) -> str:
    """The court printed on the record. Cases from before chặng R1 stored a placeholder; they show
    the default court instead."""
    return DEFAULT_COURT_NAME if case.court.name == LEGACY_COURT_PLACEHOLDER else case.court.name


def indictment_reference(indictment: str) -> tuple[str | None, str | None]:
    """(number, date) of the cáo trạng, read from its header lines; None when not written there."""
    head = "\n".join(indictment.split("\n")[:6])
    number = _INDICTMENT_NUMBER.search(head)
    date = _VN_DATE.search(head)
    return (number.group(1).rstrip(".,;") if number else None,
            f"ngày {int(date.group(1))} tháng {int(date.group(2))} năm {date.group(3)}" if date else None)


def _charge_text(case: CaseFile) -> str:
    c = case.draft.charge
    diem = f"điểm {', '.join(c.diem)} " if c.diem else ""
    return f"{diem}khoản {c.khoan} Điều {c.dieu} Bộ luật Hình sự"


def _opening(case: CaseFile, start: datetime) -> list[TrialRecordField]:
    names = case.participants
    number, date = indictment_reference(case.draft.indictment_text)
    return [
        TrialRecordField(label="Vào hồi", value=_vn_datetime(case.court.hearing_date, start), simulated=True),
        TrialRecordField(label="Tại", value=f"trụ sở {court_office(case)}, {case.court.venue}", simulated=True),
        TrialRecordField(label="Tòa án", value=court_office(case)),
        TrialRecordField(label="Mở phiên tòa để xét xử sơ thẩm vụ án hình sự đối với bị cáo",
                         value=names["BI_CAO"].name),
        TrialRecordField(label="Bị Viện kiểm sát", value=procuracy_name(court_office(case))),
        TrialRecordField(label="Truy tố về tội", value=case.draft.charge.crime_name),
        TrialRecordField(label="Theo", value=_charge_text(case)),
        TrialRecordField(label="Tại Cáo trạng số", value=number),
        TrialRecordField(label="Ngày", value=date),
        TrialRecordField(label="Vụ án được xét xử", value="công khai", simulated=True),
    ]


def _court_section(case: CaseFile) -> TrialRecordSection:
    n = case.participants
    office = procuracy_name(court_office(case))
    return TrialRecordSection(heading="I. Những người tiến hành tố tụng", fields=[
        TrialRecordField(label="Thẩm phán - Chủ tọa phiên tòa", value=_named(n["CHU_TOA"])),
        TrialRecordField(label="Các Hội thẩm nhân dân",
                         value=f"{_named(n['HOI_THAM_1'])} và {_named(n['HOI_THAM_2'])}"),
        TrialRecordField(label="Thư ký phiên tòa", value=_named(n["THU_KY"])),
        TrialRecordField(label="Đại diện Viện kiểm sát tham gia phiên tòa",
                         value=f"{office}: {_named(n['KSV'])} - Kiểm sát viên."),
    ])


def _lay_person(case: CaseFile, pid: str, presence: str) -> str:
    person = next(p for p in [case.draft.victim, *case.draft.witnesses, case.draft.related_party]
                  if p is not None and p.id == pid)
    return (f"{_named(case.participants[pid])}, {person.age} tuổi; nghề nghiệp: {person.occupation}; "
            f"nơi cư trú: {person.residence_place}. {presence}")


def _parties_section(case: CaseFile) -> TrialRecordSection:
    d, n = case.draft, case.participants
    defendant = d.defendant
    birth_year = int(case.incident_date[-4:]) - defendant.age
    gender = {"nam": "Nam", "nu": "Nữ"}.get(defendant.gender, BLANK)
    fields = [
        TrialRecordField(label="Bị cáo", value=(
            f"{n['BI_CAO'].name}, sinh năm {birth_year} tại {BLANK}; nơi cư trú: {defendant.residence_place}; "
            f"nghề nghiệp: {defendant.occupation}; trình độ văn hoá (học vấn): {defendant.education}; dân tộc: "
            f"{BLANK}; giới tính: {gender}; con ông {BLANK} và bà {BLANK}; tiền án, tiền sự: "
            f"{defendant.prior_record}; biện pháp ngăn chặn: {defendant.preventive_measure}. Có mặt.")),
        TrialRecordField(label="Người bào chữa cho bị cáo", value=(
            f"{_named(n['LUAT_SU'])}, Luật sư Văn phòng luật sư {BLANK} thuộc Đoàn luật sư {BLANK}, bào chữa "
            f"cho bị cáo {n['BI_CAO'].name}. Có mặt.")),
        TrialRecordField(label="Bị hại", value=_lay_person(
            case, "BI_HAI", "Có mặt." if case.options.victim_present
            else "Vắng mặt, có đơn đề nghị xét xử vắng mặt.")),
    ]
    if d.related_party is not None:
        fields.append(TrialRecordField(label="Người có quyền lợi, nghĩa vụ liên quan đến vụ án",
                                       value=_lay_person(case, d.related_party.id, "Có mặt.")))
    fields += [TrialRecordField(label="Người làm chứng", value=_lay_person(case, w.id, "Có mặt."))
               for w in d.witnesses]
    return TrialRecordSection(heading="II. Những người tham gia tố tụng", fields=fields)


def _entries(case: CaseFile, utterances: list[Utterance], steps: tuple[int, ...]) -> list[TrialRecordEntry]:
    names = case.participants
    return [TrialRecordEntry(
        seq=u.seq, step=u.step, speaker_role=ROLE_LABELS.get(role_of(u.speaker_id), u.speaker_id),
        speaker_name=names[u.speaker_id].name if u.speaker_id in names else "",
        text=u.text if u.is_user else render(u.text, names),
    ) for u in utterances if u.kind != "notice" and u.step in steps]


def _debate_item(case: CaseFile, utterances: list[Utterance], heading: str, steps: tuple[int, ...],
                 key: str | None, summary: dict | None) -> TrialRecordSection:
    text = (summary or {}).get(key) if key else None
    if text:
        return TrialRecordSection(heading=heading, content="summary", summary=render(text, case.participants))
    fallback = bool(key and summary and any(f.startswith(f"{key}:") for f in summary.get("flags", [])))
    return TrialRecordSection(heading=heading, entries=_entries(case, utterances, steps), summary_fallback=fallback)


def build_record(case: CaseFile, utterances: list[Utterance], started_at: datetime | None,
                 completed_at: datetime | None, summary: dict | None = None,
                 observer: bool = False) -> TrialRecordOut:
    start = (started_at or datetime.now(timezone.utc)).astimezone(VIETNAM_TZ)
    end = (completed_at or datetime.now(timezone.utc)).astimezone(VIETNAM_TZ)
    names = case.participants
    return TrialRecordOut(
        disclaimer=TRIAL_DISCLAIMER, form_reference=FORM_REFERENCE, preamble=[OBSERVER_NOTE] if observer else [],
        court_name=court_office(case),
        national_header=["CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Độc lập - Tự do - Hạnh phúc"],
        title="BIÊN BẢN", subtitle="PHIÊN TÒA HÌNH SỰ SƠ THẨM",
        opening=_opening(case, start),
        sections=[
            _court_section(case),
            _parties_section(case),
            TrialRecordSection(heading="III. Phần thủ tục bắt đầu phiên tòa",
                               entries=_entries(case, utterances, OPENING_STEPS)),
            TrialRecordSection(heading="IV. Phần tranh tụng tại phiên tòa", subsections=[
                _debate_item(case, utterances, heading, steps, key, summary) for heading, steps, key in DEBATE_ITEMS
            ], notes=list(DELIBERATION_NOTES)),
        ],
        closing=[
            TrialRecordField(label="Những sửa đổi, bổ sung theo yêu cầu của Kiểm sát viên và những người tham gia "
                                   "tố tụng", value=None),
            TrialRecordField(label="Phiên tòa kết thúc vào hồi", value=_vn_datetime(case.court.hearing_date, end),
                             simulated=True),
        ],
        signatures=[
            TrialRecordSignature(title="THƯ KÝ GHI BIÊN BẢN PHIÊN TÒA", note="(Ký tên, ghi rõ họ tên)",
                                 name=names["THU_KY"].name),
            TrialRecordSignature(title="THẨM PHÁN - CHỦ TỌA PHIÊN TÒA", note="(Ký tên, ghi rõ họ tên, đóng dấu)",
                                 name=names["CHU_TOA"].name),
        ],
        appendix=[TrialRecordSection(heading=APPENDIX_HEADING, notes=[APPENDIX_NOTE],
                                     entries=_entries(case, utterances, (JUDGMENT_STEP,)))],
    )


def _field_line(f: TrialRecordField) -> str:
    return f"{f.label}: {f.value if f.value is not None else BLANK}"


def _section_lines(section: TrialRecordSection, top: bool) -> list[str]:
    lines = ["", section.heading.upper() if top else section.heading]
    lines += [_field_line(f) for f in section.fields]
    if section.content == "summary" and section.summary:
        lines.append(section.summary)
    lines += [f"{e.speaker_role} {e.speaker_name}: {e.text}".replace(" :", ":") for e in section.entries]
    for sub in section.subsections:
        lines += _section_lines(sub, top=False)
    if section.notes:
        lines += ["", *section.notes]
    return lines


def render_record_text(record: TrialRecordOut) -> str:
    """Plain-text rendering for copy/print. Headings of the form's parts are in capitals (the
    frontend styles capitalised lines as headings)."""
    lines = [NOTICE_LINE, *record.preamble, "", record.court_name.upper(), *[h.upper() for h in record.national_header], "",
             record.title, record.subtitle, ""]
    lines += [_field_line(f) for f in record.opening]
    for section in record.sections:
        lines += _section_lines(section, top=True)
    lines += ["", *[_field_line(f) for f in record.closing], ""]
    lines += [f"{s.title}: {s.name}" for s in record.signatures]
    for section in record.appendix:
        lines += ["", section.heading.upper(), *section.notes]
        lines += [f"{e.speaker_role} {e.speaker_name}: {e.text}".replace(" :", ":") for e in section.entries]
    lines += ["", NOTICE_LINE]
    return "\n".join(lines)
