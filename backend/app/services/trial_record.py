"""Biên bản phiên tòa, built by CODE from the stored utterances (design doc Mục 7, chặng 2 B2).

Structure follows BLTTHS Điều 258: time and place of the hearing, everyone present, every
question, answer, statement and decision from opening to close (khoản 1-2), and the signatures of
Chủ tọa and Thư ký (khoản 3). No LLM call: the record is the transcript, arranged, so it can never
contain a line nobody said. The simulation notice is inserted by code at the top and the bottom.
Order-keeping notices (kind="notice", e.g. refusing to skip a step) are not part of the record.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.trial import TRIAL_DISCLAIMER, CaseFile
from app.services.trial_names import render
from app.services.trial_state_machine import ROLE_LABELS, STEP_BY_NUMBER
from app.services.trial_turn_service import Utterance, role_of

VIETNAM_TZ = timezone(timedelta(hours=7))
NOTICE_LINE = f"*** {TRIAL_DISCLAIMER.upper()} ***"


def _person_line(case: CaseFile, pid: str, extra: str = "") -> str:
    participant = case.participants[pid]
    return f"- {participant.role}: {participant.name}{extra}"


def build_record(case: CaseFile, utterances: list[Utterance], started_at: datetime | None,
                 completed_at: datetime | None) -> str:
    d = case.draft
    names = case.participants
    start = (started_at or datetime.now(timezone.utc)).astimezone(VIETNAM_TZ)
    end = (completed_at or datetime.now(timezone.utc)).astimezone(VIETNAM_TZ)
    birth_year = int(case.incident_date[-4:]) - d.defendant.age
    victim_presence = "có mặt" if case.options.victim_present else "vắng mặt, có đơn đề nghị xét xử vắng mặt"

    lines = [
        NOTICE_LINE, "",
        case.court.name.upper(), "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Độc lập - Tự do - Hạnh phúc", "",
        "BIÊN BẢN PHIÊN TÒA HÌNH SỰ SƠ THẨM", "",
        f"Vào hồi {start:%H} giờ {start:%M} phút ngày {case.court.hearing_date}, tại trụ sở {case.court.name}, "
        f"{case.court.venue}, mở phiên tòa xét xử sơ thẩm công khai vụ án hình sự đối với bị cáo "
        f"{names['BI_CAO'].name} bị Viện kiểm sát truy tố về {d.charge.crime_name.lower()} theo "
        f"{'điểm ' + ', '.join(d.charge.diem) + ' ' if d.charge.diem else ''}khoản {d.charge.khoan} "
        f"Điều {d.charge.dieu} Bộ luật Hình sự.", "",
        "I. NHỮNG NGƯỜI TIẾN HÀNH TỐ TỤNG",
        _person_line(case, "CHU_TOA"), _person_line(case, "HOI_THAM_1"), _person_line(case, "HOI_THAM_2"),
        _person_line(case, "THU_KY"), _person_line(case, "KSV", " - Viện kiểm sát nhân dân [giả định]"), "",
        "II. NHỮNG NGƯỜI THAM GIA TỐ TỤNG",
        _person_line(case, "BI_CAO", f", sinh năm {birth_year}; nơi cư trú: {d.defendant.residence_place}; nghề "
                                     f"nghiệp: {d.defendant.occupation}; trình độ học vấn: {d.defendant.education}; "
                                     f"tiền án, tiền sự: {d.defendant.prior_record}; biện pháp ngăn chặn: "
                                     f"{d.defendant.preventive_measure}. Có mặt."),
        _person_line(case, "LUAT_SU", ". Có mặt."),
        _person_line(case, "BI_HAI", f". {victim_presence[0].upper()}{victim_presence[1:]}."),
        *[_person_line(case, w.id, ". Có mặt.") for w in d.witnesses],
        *([_person_line(case, "NLQ", ". Có mặt.")] if d.related_party is not None else []), "",
        "III. DIỄN BIẾN PHIÊN TÒA",
    ]
    step = 0
    for utterance in utterances:
        if utterance.kind == "notice":
            continue
        if utterance.step != step:
            step = utterance.step
            lines += ["", f"{step}. {STEP_BY_NUMBER[step].title.upper()}"]
        who = names[utterance.speaker_id].name if utterance.speaker_id in names else utterance.speaker_id
        role = ROLE_LABELS.get(role_of(utterance.speaker_id), utterance.speaker_id)
        lines.append(f"{role} {who}: {render(utterance.text, names)}")
    lines += [
        "", "IV. KẾT THÚC PHIÊN TÒA",
        f"Phiên tòa kết thúc vào hồi {end:%H} giờ {end:%M} phút cùng ngày. Biên bản được lập theo Điều 258 Bộ luật "
        f"Tố tụng hình sự; chủ tọa phiên tòa đã kiểm tra biên bản và cùng Thư ký ký tên.", "",
        f"THƯ KÝ PHIÊN TÒA: {names['THU_KY'].name}          THẨM PHÁN - CHỦ TỌA PHIÊN TÒA: {names['CHU_TOA'].name}",
        "", NOTICE_LINE,
    ]
    return "\n".join(lines)
