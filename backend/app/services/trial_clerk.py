"""The Thư ký role's own work (chặng R2, design doc Mục 11.3 and decisions 5-8 of 11.8).

The student playing Thư ký speaks once (the step-1 report, through the state machine); the rest of
the role is work that is NOT an utterance and never goes through /turn:
- notes taken during the hearing, stored on the server (user_work.notes) because the frontend may
  not keep session content in the browser;
- parts IV.2 (hỏi và trả lời) and IV.3 (tranh luận) of the biên bản, written after tuyên án, saved
  as a draft and then finalised. The other parts stay built by code (trial_record).

Neither the notes nor the draft is ever put into a prompt, logged, or shown in any response other
than the clerk routes and the clerk's own biên bản. A Thư ký session makes no record-summary call
(decision 7): nothing here calls the LLM.

The review of the draft gives FEEDBACK only (decision 6): "Lưu ý" items next to a section, never a
score and never a reason to refuse finalising. It reuses the ideas of trial_record_summary's checks,
but compares each section with what was said in THAT section of the hearing (Mục 11.3.5).

Stored shape (mock_trial_sessions.user_work, migration 0013, jsonb):
    {"v": 1, "notes": str, "notes_updated_at": iso,
     "record": {"iv2": str, "iv3": str, "updated_at": iso, "finalized_at": iso | null}}
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models.trial import CaseFile
from app.services.trial_case_validator import MONEY_PATTERN, PERCENT_PATTERN, parse_money
from app.services.trial_config import LAW_SHORT_NAMES
from app.services.trial_names import NAME_LIKE_PATTERN, render
from app.services.trial_record_summary import SECTION_STEPS
from app.services.trial_rule9 import extract_citations
from app.services.trial_state_machine import ROLE_LABELS, STEPS, CaseShape
from app.services.trial_turn_service import Utterance, _name_to_placeholder, attendance_report

USER_WORK_VERSION = 1
NOTES_MAX_CHARS = 20_000
# Mục 11.3.1: each section 200-4.000 characters. Outside that range is a "Lưu ý", not a refusal;
# SECTION_HARD_MAX_CHARS only bounds storage (same bound as a long speech).
SECTION_MIN_CHARS = 200
SECTION_MAX_CHARS = 4000
SECTION_HARD_MAX_CHARS = 6000
CLERK_SECTIONS = ("iv2", "iv3")
SECTION_NUMBERS = {"iv2": 2, "iv3": 3}
SECTION_TOPICS = {"iv2": "hỏi và trả lời", "iv3": "tranh luận"}
AUTHOR_NOTE = "Do Thư ký (người học) ghi"

# --- Note-taking prompts (Mục 11.3.6-7) -----------------------------------------------------------
# One line per step telling the clerk what to write down. Static, 0 LLM calls. Drafted by the
# developer from the steps' content and Mẫu 22-HS guidance (27)-(28); NOT yet reviewed by the legal
# team (Mục 11.3.8), so `reviewed` is false.
CLERK_PROMPTS_REVIEWED = False
CLERK_PROMPTS: dict[int, str] = {
    1: "Báo cáo Hội đồng xét xử danh sách người có mặt, người vắng mặt và lý do vắng mặt; xác nhận đã phổ biến "
       "nội quy phiên tòa.",
    2: "Ghi: việc kiểm tra căn cước bị cáo, việc giải thích quyền và nghĩa vụ, ý kiến về việc thay đổi người tiến "
       "hành tố tụng, việc người làm chứng cam đoan.",
    3: "Kiểm sát viên công bố cáo trạng: mục IV.1 do hệ thống chép nguyên văn. Ghi ý kiến bổ sung (nếu có).",
    4: "Ghi cho mục IV.2: ai hỏi, hỏi ai, nội dung chính của câu hỏi và câu trả lời; điểm khác với lời khai ở "
       "giai đoạn điều tra.",
    5: "Ghi cho mục IV.2: câu hỏi chính của Kiểm sát viên và luật sư, câu trả lời của từng người.",
    6: "Ghi cho mục IV.3: tội danh, điểm, khoản, Điều mà Kiểm sát viên đề nghị áp dụng; tình tiết tăng nặng, giảm "
       "nhẹ; mức hình phạt đề nghị; trách nhiệm dân sự, vật chứng.",
    7: "Ghi cho mục IV.3: các luận điểm bào chữa chính và đề nghị của luật sư; ý kiến của bị hại (nếu có).",
    8: "Ghi cho mục IV.3: ai đối đáp, đáp lại ý kiến nào, lập luận chính.",
    9: "Lời nói sau cùng của bị cáo: mục IV.4 do hệ thống chép nguyên văn.",
    10: "Hội đồng xét xử vào phòng nghị án: không có lời nào cần ghi.",
    11: "Lời tuyên án được đính kèm nguyên văn ở phụ lục. Sau khi tuyên án, Thư ký hoàn thiện mục IV.2 và IV.3.",
}
assert set(CLERK_PROMPTS) == {s.number for s in STEPS}


def clerk_prompt(step: int) -> dict:
    """The note-taking prompt of `step` as the API returns it (TrialStateOut.clerk_prompt)."""
    return {"step": step, "text": CLERK_PROMPTS[step], "reviewed": CLERK_PROMPTS_REVIEWED}


def attendance(case: CaseFile, shape: CaseShape) -> list[dict[str, Any]]:
    """Who the case file summons and whether they are present - for the clerk to check the report
    against (Mục 11.3.1). Court officials are not listed: Thư ký reports on the summoned people."""
    ids = ["KSV", "BI_CAO", "LUAT_SU", "BI_HAI", *(f"NLC_{i}" for i in range(1, shape.witness_count + 1))]
    if shape.has_related_party:
        ids.append("NLQ")
    names = case.participants
    rows = []
    for pid in ids:
        role = "nguoi_lam_chung" if pid.startswith("NLC_") else {"KSV": "ksv", "BI_CAO": "bi_cao", "LUAT_SU": "luat_su",
                                                                 "BI_HAI": "bi_hai", "NLQ": "nguoi_lq"}[pid]
        rows.append({"speaker_id": pid, "role": ROLE_LABELS[role], "name": names[pid].name if pid in names else "",
                     "present": shape.victim_present if pid == "BI_HAI" else True})
    return rows


def report_prefill(case: CaseFile, shape: CaseShape) -> str:
    """The template report with the names rendered, as the student will edit it."""
    return render(attendance_report(shape), case.participants)


# --- Text cleaning --------------------------------------------------------------------------------

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EMPHASIS = re.compile(r"\*\*|__|`")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_STAR_BULLET = re.compile(r"^(\s*)[*+]\s+", re.MULTILINE)
_TRAILING_SPACE = re.compile(r"[ \t]+$", re.MULTILINE)
_BLANK_LINES = re.compile(r"\n{3,}")


def clean_notes(text: str) -> str:
    """Notes are a private scratch pad: only normalised (NFC, newlines, control characters)."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROL.sub("", text)


def clean_section(text: str) -> str:
    """A biên bản section as stored and printed: plain text in the record's paragraph convention
    (paragraphs separated by one blank line, "- " bullets). Markdown markers are removed - the
    record is a plain-text form - but no word is changed."""
    text = clean_notes(text)
    text = _HEADING.sub("", text)
    text = _STAR_BULLET.sub(r"\1- ", text)
    text = _EMPHASIS.sub("", text)
    text = _TRAILING_SPACE.sub("", text)
    return _BLANK_LINES.sub("\n\n", text).strip()


# --- user_work ------------------------------------------------------------------------------------

def _base(work: dict | None) -> dict[str, Any]:
    data = dict(work or {})
    data["v"] = USER_WORK_VERSION
    return data


def notes_of(work: dict | None) -> tuple[str, str | None]:
    work = work or {}
    return work.get("notes") or "", work.get("notes_updated_at")


def with_notes(work: dict | None, notes: str, now: datetime) -> dict[str, Any]:
    data = _base(work)
    data["notes"], data["notes_updated_at"] = notes, now.isoformat()
    return data


@dataclass(frozen=True)
class RecordDraft:
    iv2: str
    iv3: str
    updated_at: str | None
    finalized_at: str | None

    @property
    def finalized(self) -> bool:
        return self.finalized_at is not None

    def sections(self) -> dict[str, str]:
        return {"iv2": self.iv2, "iv3": self.iv3}


def draft_of(work: dict | None) -> RecordDraft:
    record = (work or {}).get("record") or {}
    return RecordDraft(record.get("iv2") or "", record.get("iv3") or "", record.get("updated_at"),
                       record.get("finalized_at"))


def with_draft(work: dict | None, sections: dict[str, str | None], now: datetime) -> dict[str, Any]:
    """Sections given as None keep their stored text; a finalised draft is never changed (the
    route refuses before calling this)."""
    data = _base(work)
    current = draft_of(work)
    record = {**current.sections(), "updated_at": now.isoformat(), "finalized_at": None}
    for key in CLERK_SECTIONS:
        if sections.get(key) is not None:
            record[key] = clean_section(sections[key] or "")
    data["record"] = record
    return data


def with_finalized(work: dict | None, now: datetime) -> dict[str, Any]:
    data = _base(work)
    data["record"] = {**(data.get("record") or {}), "finalized_at": now.isoformat()}
    return data


# --- Review ("Lưu ý", Mục 11.3.5) -----------------------------------------------------------------

@dataclass(frozen=True)
class ClerkNotice:
    section: str
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"section": self.section, "code": self.code, "message": self.message}


def _law_label(dieu: str, law: str | None) -> str:
    return f"Điều {dieu} {LAW_SHORT_NAMES[law]}" if law in LAW_SHORT_NAMES else f"Điều {dieu}"


def section_source(transcript: list[Utterance], key: str) -> str:
    """What was said in the hearing steps a section records (order-keeping notices excluded)."""
    return "\n".join(u.text for u in transcript if u.kind != "notice" and u.step in SECTION_STEPS[key])


def review_section(case: CaseFile, transcript: list[Utterance], key: str, text: str) -> list[ClerkNotice]:
    """Feedback on one clerk-written section. Labels and messages only; never blocks anything."""
    n, topic = SECTION_NUMBERS[key], SECTION_TOPICS[key]
    notices: list[ClerkNotice] = []

    def add(code: str, message: str) -> None:
        notice = ClerkNotice(key, code, message)
        if notice not in notices:
            notices.append(notice)

    length = len(text.strip())
    if length == 0:
        add("empty", f"Mục {n} chưa có nội dung.")
        return notices
    if length < SECTION_MIN_CHARS:
        add("too_short", f"Mục {n} có {length} ký tự, ngắn hơn mức gợi ý {SECTION_MIN_CHARS} ký tự.")
    elif length > SECTION_MAX_CHARS:
        add("too_long", f"Mục {n} có {length} ký tự, dài hơn mức gợi ý {SECTION_MAX_CHARS} ký tự.")

    source = section_source(transcript, key)
    spoken_amounts = {parse_money(m.group(1)) for m in MONEY_PATTERN.finditer(source)}
    for match in MONEY_PATTERN.finditer(text):
        if parse_money(match.group(1)) not in spoken_amounts:
            add("unknown_amount", f"Mục {n} nêu {match.group(0)}; con số này không xuất hiện trong phần {topic}.")
    spoken_percents = {int(m.group(1)) for m in PERCENT_PATTERN.finditer(source)}
    for match in PERCENT_PATTERN.finditer(text):
        if int(match.group(1)) not in spoken_percents:
            add("unknown_percent", f"Mục {n} nêu {match.group(0)}; con số này không xuất hiện trong phần {topic}.")

    placeholder_text = _name_to_placeholder(text, case)
    cited_in_source = extract_citations(source)
    for cited in extract_citations(placeholder_text):
        if cited.law is None:
            add("citation_missing_law", f"Mục {n} viện dẫn Điều {cited.dieu} nhưng chưa ghi tên luật (Bộ luật Hình "
                                        f"sự hay Bộ luật Tố tụng hình sự).")
        if not any(s.dieu == cited.dieu and (cited.law is None or s.law is None or s.law == cited.law)
                   for s in cited_in_source):
            add("citation_not_in_section", f"Mục {n} viện dẫn {_law_label(cited.dieu, cited.law)}; không ai viện "
                                           f"dẫn Điều này trong phần {topic}.")
    for match in NAME_LIKE_PATTERN.finditer(placeholder_text):
        add("unknown_name", f"Mục {n} có tên \"{match.group(0)}\"; tên này không có trong phiên tòa.")
    return notices


def review_draft(case: CaseFile, transcript: list[Utterance], draft: RecordDraft) -> list[ClerkNotice]:
    return [notice for key in CLERK_SECTIONS for notice in review_section(case, transcript, key, draft.sections()[key])]
