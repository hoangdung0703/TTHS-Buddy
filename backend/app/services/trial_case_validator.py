"""Code-level checks on a generated CaseDraft (design doc Mục 3.2). Returns a list of error
strings; empty means valid. The errors are fed back to the model on the single retry, so each one
says what is wrong in terms the model can fix. Errors never quote student text (there is none in
a case) and are safe to log as counts.

Checked here, against the case's real legal pack (not against model claims):
- the charge is the configured crime, an allowed khoản, and every điểm exists in that khoản;
- no điểm/khoản built on a minor, no death-penalty khoản;
- the khoản matches the property value / injury percent band, and that number matches evidence;
- every money amount and percent written anywhere matches a declared value;
- ids are unique and every reference resolves; participants match the student's options;
- every person is 18-80 and no text mentions a minor;
- no invented personal names (placeholders only), places from the abstract list;
- mitigating/aggravating points exist in Điều 51/52;
- every citation in the indictment passes the Rule 9 pair guard.
"""
from __future__ import annotations

import re
from collections.abc import Iterator

from app.models.trial import CaseDraft, CaseKnobs, CaseOptions, PersonDraft
from app.services.trial_config import (
    ABSTRACT_PLACES,
    BLHS_DOCUMENT,
    FORBIDDEN_PENALTY_TEXT,
    FORBIDDEN_POINT_TEXT,
    MAX_PERSON_AGE,
    MAX_STATEMENT_SIMILARITY,
    MIN_EVIDENCE,
    MIN_INDICTMENT_WORDS,
    MIN_PERSON_AGE,
    MIN_STATEMENT_WORDS,
    CrimeConfig,
)
from app.services.trial_legal_pack import LegalPack
from app.services.trial_names import COURT_ROLES, NAME_LIKE_PATTERN, placeholders_in
from app.services.trial_rule9 import check_citations
from app.services.trial_text_format import format_speech

# "12.500.000 đồng", "12.500.000đ", "12.500.000 VNĐ"
MONEY_PATTERN = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d{4,})\s*(?:đồng|đ\b|vnđ|vnd)", re.IGNORECASE)
PERCENT_PATTERN = re.compile(r"(\d{1,3})\s*%")
# An age under 18 written out ("15 tuổi", "17 tuổi").
MINOR_AGE_PATTERN = re.compile(r"(?<!\d)(?:[1-9]|1[0-7])\s*tuổi", re.IGNORECASE)


_CODE_PREFIX = re.compile(r"^\s*\{?\s*(?:điều|khoản|điểm)?\s*", re.IGNORECASE)


def _code(value: object) -> object:
    """'{BI_CAO}' -> 'BI_CAO', 'Điều 171' -> '171', 'khoản 1' -> '1', 'điểm c' -> 'c'."""
    if not isinstance(value, str):
        return value
    return _CODE_PREFIX.sub("", value).strip().strip("{}").strip()


def evidence_fact_map(evidence: list, fact_ids: set[str]) -> dict[str, str]:
    """evidence id -> the fact it proves, for evidence whose fact_id names a real fact. Accepts
    raw dicts (before validation) and EvidenceDraft models (nghị án)."""
    mapping = {}
    for item in evidence:
        eid = item.get("id") if isinstance(item, dict) else item.id
        fid = item.get("fact_id") if isinstance(item, dict) else item.fact_id
        if eid and fid in fact_ids:
            mapping[eid] = fid
    return mapping


def remap_fact_ids(fact_refs: list[str], fact_ids: set[str], by_evidence: dict[str, str]) -> list[str]:
    """A circumstance citing an EVIDENCE id where a fact id belongs is repaired when that evidence
    is linked to a fact; any other unknown id is kept as is, so the validator still rejects it."""
    return [by_evidence[ref] if ref not in fact_ids and ref in by_evidence else ref for ref in fact_refs]


def normalise_draft_dict(data: dict) -> dict:
    """Deterministic clean-up of CODE fields only (ids, Điều/khoản/điểm), applied before schema
    validation. Spike 2026-10-19: the model wrote ids as "{BI_CAO}" (the placeholder form used in
    text) in 5/5 first attempts, and once wrote charge.dieu as "Điều 171"; each such slip cascaded
    into a dozen validation errors. Free-text fields keep their words; only the indictment's layout
    (markup, blank lines) is normalised by trial_text_format (chặng 3D)."""
    if isinstance(data.get("indictment_text"), str):
        data["indictment_text"] = format_speech(data["indictment_text"], multi_paragraph=True)
    people = [data.get("defendant"), data.get("victim"), *(data.get("witnesses") or []), data.get("related_party")]
    for index, p in enumerate(people):
        if isinstance(p, dict):
            p["id"] = _code(p.get("id"))
            # Code-assigned (chặng 3C): the model is no longer asked for a residence, so a real or
            # off-list place can never cost a regeneration. One abstract place per person, in order.
            p["residence_place"] = ABSTRACT_PLACES[index % len(ABSTRACT_PLACES)]
    for statement in data.get("pretrial_statements") or []:
        if isinstance(statement, dict):
            statement["person_id"] = _code(statement.get("person_id"))
    charge = data.get("charge")
    if isinstance(charge, dict):
        charge["dieu"], charge["khoan"] = _code(charge.get("dieu")), _code(charge.get("khoan"))
        charge["diem"] = [_code(d) for d in charge.get("diem") or []]
    for key in ("mitigating", "aggravating"):
        for item in data.get(key) or []:
            if isinstance(item, dict):
                item["khoan"], item["diem"] = _code(item.get("khoan")), _code(item.get("diem"))
                item["fact_ids"] = [_code(f) for f in item.get("fact_ids") or []]
    for key in ("facts", "evidence"):
        for item in data.get(key) or []:
            if isinstance(item, dict):
                item["id"] = _code(item.get("id"))
    for extra in data.get("extra_amounts") or []:
        if isinstance(extra, dict) and extra.get("evidence_id"):
            extra["evidence_id"] = _code(extra["evidence_id"])
    claim = data.get("civil_claim")
    if isinstance(claim, dict):
        claim["claimant_id"] = _code(claim.get("claimant_id"))
    for item in data.get("evidence") or []:
        if isinstance(item, dict) and item.get("fact_id"):
            item["fact_id"] = _code(item["fact_id"])
    fact_ids = {f.get("id") for f in data.get("facts") or [] if isinstance(f, dict)}
    by_evidence = evidence_fact_map(data.get("evidence") or [], fact_ids)
    for key in ("mitigating", "aggravating"):
        for item in data.get(key) or []:
            if isinstance(item, dict):
                item["fact_ids"] = remap_fact_ids(item.get("fact_ids") or [], fact_ids, by_evidence)
    return data


def parse_money(raw: str) -> int:
    return int(raw.replace(".", ""))


def _people(draft: CaseDraft) -> list[PersonDraft]:
    people: list[PersonDraft] = [draft.defendant, draft.victim, *draft.witnesses]
    if draft.related_party is not None:
        people.append(draft.related_party)
    return people


def iter_texts(draft: CaseDraft) -> Iterator[tuple[str, str]]:
    """(field path, text) for every free-text field of the draft."""
    yield "title", draft.title
    yield "incident_summary", draft.incident_summary
    yield "indictment_text", draft.indictment_text
    for person in _people(draft):
        yield f"{person.id}.statement_summary", person.statement_summary
        yield f"{person.id}.stance", person.stance
        yield f"{person.id}.demeanor", person.demeanor
        yield f"{person.id}.occupation", person.occupation
        for i, item in enumerate(person.knowledge):
            yield f"{person.id}.knowledge[{i}]", item
    yield "defendant.prior_record", draft.defendant.prior_record
    yield "defendant.preventive_measure", draft.defendant.preventive_measure
    for fact in draft.facts:
        yield f"{fact.id}.description", fact.description
        yield f"{fact.id}.time", fact.time
        yield f"{fact.id}.place", fact.place
    for item in draft.evidence:
        yield f"{item.id}.description", item.description
    for statement in draft.pretrial_statements:
        yield f"statement[{statement.person_id}].summary", statement.summary
        for i, item in enumerate(statement.inconsistencies):
            yield f"statement[{statement.person_id}].inconsistencies[{i}]", item.text
    if draft.civil_claim is not None:
        yield "civil_claim.basis", draft.civil_claim.basis
    for i, extra in enumerate(draft.extra_amounts):
        yield f"extra_amounts[{i}].label", extra.label


def expected_person_ids(options: CaseOptions) -> list[str]:
    ids = ["BI_CAO", "BI_HAI"] + [f"NLC_{i}" for i in range(1, options.witness_count + 1)]
    if options.has_related_party:
        ids.append("NLQ")
    return ids


def declared_amounts(draft: CaseDraft, crime: CrimeConfig) -> set[int]:
    amounts = {e.value_vnd for e in draft.evidence if e.value_vnd is not None}
    if crime.measure == "value_vnd":
        amounts.add(draft.measure_value)
    if draft.civil_claim is not None:
        amounts.add(draft.civil_claim.amount_vnd)
    if draft.compensation_vnd:
        amounts.add(draft.compensation_vnd)
    amounts.update(extra.amount_vnd for extra in draft.extra_amounts)
    amounts.update(item.claimed_amount_vnd for statement in draft.pretrial_statements
                   for item in statement.inconsistencies if item.claimed_amount_vnd is not None)
    if amounts:
        amounts.add(sum(e.value_vnd for e in draft.evidence if e.value_vnd is not None))
    return amounts


def declared_percents(draft: CaseDraft, crime: CrimeConfig) -> set[int]:
    percents = {e.injury_percent for e in draft.evidence if e.injury_percent is not None}
    if crime.measure == "injury_percent":
        percents.add(draft.measure_value)
    return percents


def _check_charge(draft: CaseDraft, crime: CrimeConfig, pack: LegalPack, errors: list[str]) -> None:
    charge = draft.charge
    if charge.dieu != crime.dieu:
        errors.append(f"charge.dieu phải là {crime.dieu} (tội đã chọn), không phải {charge.dieu}")
        return
    if charge.khoan not in crime.allowed_khoan:
        errors.append(f"charge.khoan {charge.khoan} không được phép; chỉ dùng khoản {', '.join(crime.allowed_khoan)}")
        return
    article = pack.get(BLHS_DOCUMENT, crime.dieu)
    if article is None or not article.has_khoan(charge.khoan):
        errors.append(f"Khoản {charge.khoan} Điều {crime.dieu} không có trong văn bản luật")
        return
    khoan = article.khoans[charge.khoan]
    if FORBIDDEN_PENALTY_TEXT.search(khoan.text):
        errors.append(f"Khoản {charge.khoan} Điều {crime.dieu} có hình phạt tử hình, không dùng cho vụ học tập")
    for letter in charge.diem:
        if not article.has_diem(charge.khoan, letter):
            errors.append(f"Điểm {letter} không có trong khoản {charge.khoan} Điều {crime.dieu}")
        elif FORBIDDEN_POINT_TEXT.search(khoan.diem_text(letter)):
            errors.append(f"Điểm {letter} khoản {charge.khoan} Điều {crime.dieu} liên quan người dưới 18 tuổi, không được dùng")

    band = next((b for b in crime.bands if b.low <= draft.measure_value and
                 (b.high is None or draft.measure_value < b.high)), None)
    unit = "đồng" if crime.measure == "value_vnd" else "%"
    if band is None or not band.allowed:
        errors.append(f"measure_value {draft.measure_value} {unit} nằm ngoài phạm vi cho phép của vụ học tập")
    elif charge.khoan not in band.required_khoan:
        errors.append(f"Với measure_value {draft.measure_value} {unit}, khoản phải là "
                      f"{' hoặc '.join(band.required_khoan)}, không phải {charge.khoan}")
    elif band.required_diem and band.required_diem not in charge.diem:
        errors.append(f"Với measure_value {draft.measure_value} {unit}, charge.diem phải có điểm {band.required_diem}")


def _check_measure_evidence(draft: CaseDraft, crime: CrimeConfig, errors: list[str]) -> None:
    if crime.measure == "value_vnd":
        valuations = [e.value_vnd for e in draft.evidence if e.type == "dinh_gia"]
        if draft.measure_value not in valuations:
            errors.append("Phải có một evidence type=dinh_gia với value_vnd bằng đúng measure_value")
    else:
        assessments = [e.injury_percent for e in draft.evidence if e.type == "giam_dinh"]
        if draft.measure_value not in assessments:
            errors.append("Phải có một evidence type=giam_dinh với injury_percent bằng đúng measure_value")


def _check_numbers_in_text(draft: CaseDraft, crime: CrimeConfig, errors: list[str]) -> None:
    amounts, percents = declared_amounts(draft, crime), declared_percents(draft, crime)
    for path, text in iter_texts(draft):
        for match in MONEY_PATTERN.finditer(text):
            if parse_money(match.group(1)) not in amounts:
                errors.append(f"{path}: số tiền {match.group(1)} đồng không khớp giá trị nào đã khai "
                              f"trong evidence/measure_value/civil_claim")
        for match in PERCENT_PATTERN.finditer(text):
            if int(match.group(1)) not in percents:
                errors.append(f"{path}: tỷ lệ {match.group(1)}% không khớp kết luận giám định đã khai")


def _check_ids(draft: CaseDraft, options: CaseOptions, errors: list[str]) -> None:
    people = _people(draft)
    person_ids = [p.id for p in people]
    expected = expected_person_ids(options)
    if person_ids != expected:
        errors.append(f"Danh sách người tham gia phải đúng thứ tự id {expected}, hiện là {person_ids}")
    if (options.has_related_party) != (draft.related_party is not None):
        errors.append("related_party phải " + ("có" if options.has_related_party else "là null"))
    if len(draft.witnesses) != options.witness_count:
        errors.append(f"Phải có đúng {options.witness_count} người làm chứng")

    fact_ids = [f.id for f in draft.facts]
    evidence_ids = [e.id for e in draft.evidence]
    for label, ids in (("facts", fact_ids), ("evidence", evidence_ids), ("people", person_ids)):
        if len(ids) != len(set(ids)):
            errors.append(f"id trùng lặp trong {label}")
    if not draft.facts or not draft.evidence:
        errors.append("Phải có ít nhất một fact và một evidence")
    known_people = set(person_ids)
    for statement in draft.pretrial_statements:
        if statement.person_id not in known_people:
            errors.append(f"pretrial_statements tham chiếu person_id không tồn tại: {statement.person_id}")
    for circumstance in [*draft.mitigating, *draft.aggravating]:
        for fid in circumstance.fact_ids:
            if fid not in fact_ids:
                errors.append(f"Tình tiết tham chiếu fact_id không tồn tại: {fid}")
    for item in draft.evidence:
        if item.fact_id is not None and item.fact_id not in fact_ids:
            errors.append(f"evidence {item.id}.fact_id không tồn tại: {item.fact_id}")
    for extra in draft.extra_amounts:
        if extra.evidence_id is not None and extra.evidence_id not in evidence_ids:
            errors.append(f"extra_amounts tham chiếu evidence_id không tồn tại: {extra.evidence_id}")
    if draft.civil_claim is not None and draft.civil_claim.claimant_id not in known_people:
        errors.append(f"civil_claim.claimant_id không tồn tại: {draft.civil_claim.claimant_id}")

    allowed_placeholders = known_people | set(COURT_ROLES)
    for path, text in iter_texts(draft):
        unknown = placeholders_in(text) - allowed_placeholders
        if unknown:
            errors.append(f"{path}: placeholder không tồn tại {sorted(unknown)}")


def _check_people(draft: CaseDraft, errors: list[str]) -> None:
    for person in _people(draft):
        if not MIN_PERSON_AGE <= person.age <= MAX_PERSON_AGE:
            errors.append(f"{person.id}.age phải từ {MIN_PERSON_AGE} đến {MAX_PERSON_AGE}")
        if person.residence_place not in ABSTRACT_PLACES:
            errors.append(f"{person.id}.residence_place phải là một trong {list(ABSTRACT_PLACES)}")
    for path, text in iter_texts(draft):
        if MINOR_AGE_PATTERN.search(text) or FORBIDDEN_POINT_TEXT.search(text):
            errors.append(f"{path}: không được nhắc tới người dưới 18 tuổi")
        if NAME_LIKE_PATTERN.search(text):
            errors.append(f"{path}: có tên người tự đặt; chỉ dùng placeholder như {{BI_CAO}}")


def _check_circumstances(draft: CaseDraft, pack: LegalPack, errors: list[str]) -> None:
    for label, dieu, items in (("mitigating", "51", draft.mitigating), ("aggravating", "52", draft.aggravating)):
        article = pack.get(BLHS_DOCUMENT, dieu)
        if article is None:
            errors.append(f"Thiếu Điều {dieu} trong gói pháp lý")
            continue
        for item in items:
            if not article.has_khoan(item.khoan):
                errors.append(f"{label}: khoản {item.khoan} Điều {dieu} không tồn tại")
                continue
            if item.diem and not article.has_diem(item.khoan, item.diem):
                errors.append(f"{label}: điểm {item.diem} khoản {item.khoan} Điều {dieu} không tồn tại")
                continue
            if not item.diem and article.khoans[item.khoan].diem:
                errors.append(f"{label}: khoản {item.khoan} Điều {dieu} có điểm, phải nêu điểm")
                continue
            if item.diem and FORBIDDEN_POINT_TEXT.search(article.khoans[item.khoan].diem_text(item.diem)):
                errors.append(f"{label}: điểm {item.diem} khoản {item.khoan} Điều {dieu} liên quan người dưới 18 tuổi")


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def _similarity(a: str, b: str) -> float:
    left, right = set(_words(a)), set(_words(b))
    return len(left & right) / max(1, len(left | right))


# Vietnamese prose has roughly one letter in five carrying a diacritic. Chặng 3D seed 4002 came back
# entirely without diacritics (summary, statements, indictment) and still passed every other check.
MIN_DIACRITIC_SHARE = 0.05
MIN_LETTERS_FOR_DIACRITIC_CHECK = 100


def lacks_diacritics(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < MIN_LETTERS_FOR_DIACRITIC_CHECK:
        return False
    return sum(1 for c in letters if not c.isascii()) / len(letters) < MIN_DIACRITIC_SHARE


def _check_minimums(draft: CaseDraft, errors: list[str]) -> None:
    """Chặng 2 A3: a case thin enough to be useless for questioning is regenerated."""
    for field_name, text in (("incident_summary", draft.incident_summary), ("indictment_text", draft.indictment_text),
                             *((f"lời khai của {s.person_id}", s.summary) for s in draft.pretrial_statements)):
        if lacks_diacritics(text):
            errors.append(f"{field_name} phải viết tiếng Việt có dấu đầy đủ")
    if len(draft.evidence) < MIN_EVIDENCE:
        errors.append(f"Phải có ít nhất {MIN_EVIDENCE} chứng cứ (evidence), hiện có {len(draft.evidence)}")
    words = len(_words(draft.indictment_text))
    if words < MIN_INDICTMENT_WORDS:
        errors.append(f"indictment_text phải dài ít nhất {MIN_INDICTMENT_WORDS} từ, hiện khoảng {words} từ")
    people = [p.id for p in _people(draft)]
    by_person: dict[str, list[str]] = {}
    for statement in draft.pretrial_statements:
        by_person.setdefault(statement.person_id, []).append(statement.summary)
    for person_id in people:
        summaries = by_person.get(person_id, [])
        if len(summaries) != 1:
            errors.append(f"Mỗi người phải có đúng một lời khai giai đoạn điều tra; {person_id} có {len(summaries)}")
        elif len(_words(summaries[0])) < MIN_STATEMENT_WORDS:
            errors.append(f"Lời khai của {person_id} phải có ít nhất {MIN_STATEMENT_WORDS} từ")
    statements = [(s.person_id, s.summary) for s in draft.pretrial_statements]
    for i in range(len(statements)):
        for j in range(i + 1, len(statements)):
            if _similarity(statements[i][1], statements[j][1]) >= MAX_STATEMENT_SIMILARITY:
                errors.append(f"Lời khai của {statements[i][0]} và {statements[j][0]} gần như trùng nhau; "
                              f"mỗi lời khai phải có nội dung riêng")


def _check_knobs(draft: CaseDraft, knobs: CaseKnobs, errors: list[str]) -> None:
    if draft.charge.khoan != knobs.khoan:
        errors.append(f"charge.khoan phải là {knobs.khoan} theo yêu cầu vụ án")
    if draft.defendant_plea != knobs.plea:
        errors.append(f"defendant_plea phải là {knobs.plea}")
    mitigating = {m.diem for m in draft.mitigating if m.khoan == "1"}
    if mitigating != set(knobs.mitigating_points):
        errors.append(f"Tình tiết giảm nhẹ khoản 1 Điều 51 phải đúng các điểm {sorted(knobs.mitigating_points)}, "
                      f"hiện là {sorted(mitigating)}")
    aggravating = {a.diem for a in draft.aggravating}
    if aggravating != set(knobs.aggravating_points):
        errors.append("Tình tiết tăng nặng phải đúng các điểm " + (str(sorted(knobs.aggravating_points))
                      if knobs.aggravating_points else "[] (không có tình tiết tăng nặng)"))
    paid = bool(draft.compensation_vnd)
    if paid != knobs.has_compensation:
        errors.append("compensation_vnd phải " + ("là số tiền bị cáo đã bồi thường (> 0)" if knobs.has_compensation
                                                  else "là null (bị cáo chưa bồi thường)"))


def validate_case_draft(draft: CaseDraft, options: CaseOptions, crime: CrimeConfig, pack: LegalPack,
                        knobs: CaseKnobs | None = None) -> list[str]:
    errors: list[str] = []
    _check_minimums(draft, errors)
    if knobs is not None:
        _check_knobs(draft, knobs, errors)
    _check_charge(draft, crime, pack, errors)
    _check_measure_evidence(draft, crime, errors)
    _check_numbers_in_text(draft, crime, errors)
    _check_ids(draft, options, errors)
    _check_people(draft, errors)
    _check_circumstances(draft, pack, errors)
    for violation in check_citations(draft.indictment_text, pack, "lenient"):
        errors.append(f"indictment_text: viện dẫn không hợp lệ ({violation.label()})")
    for path, text in iter_texts(draft):
        if path != "indictment_text" and check_citations(text, pack, "lenient"):
            errors.append(f"{path}: viện dẫn điều luật không hợp lệ")
    # De-duplicate, keep order: the retry prompt should not repeat itself.
    return list(dict.fromkeys(errors))
