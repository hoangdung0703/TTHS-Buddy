"""Fill-in-the-frame case generation (chặng 3H, phương án A).

CODE fixes the structure of a case before the model writes a word: the people (ids, order, how many
witnesses), the exact measure value and compensation, the charge (Điều, khoản, điểm), the plea and
the circumstances. The model only fills free text into a response schema built for this one case:
each person carries their own pretrial statement as a list of sentences (so a statement can be
neither missing nor doubled), the witness array has exactly the required length, and each chosen
circumstance point is a required key. Code then converts the fill into the stored CaseDraft shape
and the unchanged validator runs every old rule and threshold.

3G measurements showed the failures were all "count or remember the structure" errors
(statement_count, person_order, statement_words, money/percent mismatch, invented names); this
module removes the structural ones by construction.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from app.models.trial import CaseKnobs, CaseOptions
from app.services.trial_config import CrimeConfig, PLEA_LABELS

# Value ranges code draws the measure from, per measure kind and khoản: (low, high inclusive, step).
# Property khoản 1 starts at 2.000.000 đồng and Điều 134 khoản 1 at 11%, the thresholds at which
# the khoản applies without any extra circumstance; khoản 2 uses the value band of its điểm
# (property 50-200 million: điểm c; injury 31-60%: điểm a).
MEASURE_RANGES: dict[tuple[str, str], tuple[int, int, int]] = {
    ("value_vnd", "1"): (2_000_000, 49_000_000, 100_000),
    ("value_vnd", "2"): (50_000_000, 199_000_000, 1_000_000),
    ("injury_percent", "1"): (11, 30, 1),
    ("injury_percent", "2"): (31, 60, 1),
}
INJURY_COMPENSATION_RANGE = (5_000_000, 40_000_000, 500_000)
MIN_STATEMENT_SENTENCES = 3
MIN_EVIDENCE_ITEMS = 4


@dataclass(frozen=True)
class CaseFrame:
    person_ids: tuple[str, ...]
    witness_count: int
    has_related_party: bool
    measure_kind: str
    measure_value: int
    compensation_vnd: int | None
    dieu: str
    khoan: str
    diem: tuple[str, ...]
    crime_name: str
    plea: str
    mitigating_points: tuple[str, ...]
    aggravating_points: tuple[str, ...]


def _draw(rng: random.Random, low: int, high: int, step: int) -> int:
    return rng.randrange(low, high + 1, step) if step > 1 else rng.randint(low, high)


def build_frame(crime: CrimeConfig, options: CaseOptions, knobs: CaseKnobs, rng: random.Random) -> CaseFrame:
    measure = _draw(rng, *MEASURE_RANGES[(crime.measure, knobs.khoan)])
    band = next(b for b in crime.bands if b.low <= measure and (b.high is None or measure < b.high))
    compensation = None
    if knobs.has_compensation:
        if crime.measure == "value_vnd":
            compensation = max(100_000, round(measure * rng.uniform(0.2, 1.0) / 100_000) * 100_000)
        else:
            compensation = _draw(rng, *INJURY_COMPENSATION_RANGE)
    ids = ["BI_CAO", "BI_HAI", *(f"NLC_{i}" for i in range(1, options.witness_count + 1))]
    if options.has_related_party:
        ids.append("NLQ")
    return CaseFrame(
        person_ids=tuple(ids), witness_count=options.witness_count, has_related_party=options.has_related_party,
        measure_kind=crime.measure, measure_value=measure, compensation_vnd=compensation, dieu=crime.dieu,
        khoan=knobs.khoan, diem=(band.required_diem,) if band.required_diem else (), crime_name=crime.crime_name,
        plea=knobs.plea, mitigating_points=tuple(knobs.mitigating_points),
        aggravating_points=tuple(knobs.aggravating_points),
    )


def vnd(amount: int) -> str:
    return f"{amount:,}".replace(",", ".") + " đồng"


def frame_text(frame: CaseFrame) -> str:
    """The constants the model must copy verbatim (prompt section)."""
    diem = f"điểm {', '.join(frame.diem)} " if frame.diem else ""
    measure = (f"Giá trị tài sản theo kết luận định giá: {vnd(frame.measure_value)}" if frame.measure_kind == "value_vnd"
               else f"Tỷ lệ tổn thương cơ thể theo kết luận giám định: {frame.measure_value}%")
    lines = [
        f"- Truy tố: {frame.crime_name} theo {diem}khoản {frame.khoan} Điều {frame.dieu} Bộ luật Hình sự.",
        f"- {measure}. Chép đúng con số này vào chứng cứ định giá / giám định và vào mọi chỗ nhắc tới nó.",
        "- Bồi thường trước khi xét xử: " + (f"bị cáo đã bồi thường {vnd(frame.compensation_vnd)}; phải có một sự "
                                            "việc (fact) ghi nhận việc này." if frame.compensation_vnd
                                            else "KHÔNG có."),
        f"- Lập trường bị cáo: {PLEA_LABELS[frame.plea]}. Lời khai, thẻ nhân vật và thái độ của bị cáo phải đúng "
        "lập trường này.",
        "- Người tham gia, đúng thứ tự: " + ", ".join("{" + pid + "}" for pid in frame.person_ids) + ".",
        "- Tình tiết giảm nhẹ khoản 1 Điều 51 Bộ luật Hình sự: " + (
            ", ".join(f"điểm {p}" for p in frame.mitigating_points) if frame.mitigating_points else "không có") + ".",
        "- Tình tiết tăng nặng khoản 1 Điều 52 Bộ luật Hình sự: " + (
            ", ".join(f"điểm {p}" for p in frame.aggravating_points) if frame.aggravating_points else "không có") + ".",
    ]
    return "\n".join(lines)


# --- Per-case response schema ---------------------------------------------------------------------

_STR = {"type": "STRING"}
_INT = {"type": "INTEGER"}
_STR_LIST = {"type": "ARRAY", "items": _STR}


def _obj(properties: dict, required: list[str] | None = None, nullable: bool = False) -> dict:
    schema: dict = {"type": "OBJECT", "properties": properties,
                    "required": required if required is not None else list(properties)}
    if nullable:
        schema["nullable"] = True
    return schema


_STATEMENT = _obj({
    "sentences": {"type": "ARRAY", "items": _STR, "minItems": MIN_STATEMENT_SENTENCES},
    "inconsistencies": {"type": "ARRAY", "items": _obj(
        {"text": _STR, "claimed_amount_vnd": {"type": "INTEGER", "nullable": True}}, required=["text"])},
})
_PERSON = {"gender": {"type": "STRING", "enum": ["nam", "nu"]}, "age": _INT, "occupation": _STR, "stance": _STR,
           "statement_summary": _STR, "knowledge": _STR_LIST, "demeanor": _STR, "pretrial_statement": _STATEMENT}
_DEFENDANT = {**_PERSON, "education": _STR, "prior_record": _STR, "preventive_measure": _STR}


def _points_object(points: tuple[str, ...]) -> dict:
    return _obj({p: _STR_LIST for p in points})


def fill_schema(frame: CaseFrame) -> dict:
    properties: dict = {
        "title": _STR,
        "incident_summary": _STR,
        "defendant": _obj(_DEFENDANT),
        "victim": _obj(_PERSON),
        "facts": {"type": "ARRAY", "items": _obj({"id": _STR, "time": _STR, "place": _STR, "description": _STR})},
        "evidence": {"type": "ARRAY", "minItems": MIN_EVIDENCE_ITEMS, "items": _obj(
            {"id": _STR, "type": {"type": "STRING", "enum": ["vat_chung", "giam_dinh", "dinh_gia", "tai_lieu"]},
             "description": _STR, "value_vnd": {"type": "INTEGER", "nullable": True},
             "injury_percent": {"type": "INTEGER", "nullable": True},
             "fact_id": {"type": "STRING", "nullable": True}},
            required=["id", "type", "description"])},
        "extra_amounts": {"type": "ARRAY", "items": _obj(
            {"label": _STR, "amount_vnd": _INT, "evidence_id": {"type": "STRING", "nullable": True}},
            required=["label", "amount_vnd"])},
        "mitigating_khoan_2": {"type": "ARRAY", "items": _obj({"fact_ids": _STR_LIST})},
        "civil_claim": _obj({"claimant_id": _STR, "amount_vnd": _INT, "basis": _STR}, nullable=True),
        "indictment_text": _STR,
    }
    if frame.witness_count:
        properties["witnesses"] = {"type": "ARRAY", "items": _obj(_PERSON), "minItems": frame.witness_count,
                                   "maxItems": frame.witness_count}
    if frame.has_related_party:
        properties["related_party"] = _obj(_PERSON)
    if frame.mitigating_points:
        properties["mitigating_facts"] = _points_object(frame.mitigating_points)
    if frame.aggravating_points:
        properties["aggravating_facts"] = _points_object(frame.aggravating_points)
    optional = {"extra_amounts", "mitigating_khoan_2", "civil_claim"}
    return _obj(properties, required=[k for k in properties if k not in optional])


# --- Fill -> CaseDraft dict -----------------------------------------------------------------------

def _person(fill: dict, pid: str, statements: list[dict]) -> dict:
    person = dict(fill)
    statement = person.pop("pretrial_statement", None) or {}
    sentences = [str(s).strip() for s in statement.get("sentences") or [] if str(s).strip()]
    statements.append({"person_id": pid, "summary": " ".join(sentences),
                       "inconsistencies": statement.get("inconsistencies") or []})
    person["id"] = pid
    return person


def _sync_measure_evidence(evidence: list, frame: CaseFrame) -> None:
    """The valuation / assessment carries the frame's number (the model was told to copy it; code
    makes the structured value exact). Text that states another number still fails the money guard."""
    kind, key = ("dinh_gia", "value_vnd") if frame.measure_kind == "value_vnd" else ("giam_dinh", "injury_percent")
    for item in evidence:
        if isinstance(item, dict) and item.get("type") == kind:
            item[key] = frame.measure_value
            return


def fill_to_draft(fill: dict, frame: CaseFrame) -> dict:
    """The model's fill as a CaseDraft-shaped dict. Structure and constants come from the frame;
    nothing the model wrote is dropped except fields the frame owns."""
    statements: list[dict] = []
    witnesses = fill.get("witnesses") or []
    evidence = list(fill.get("evidence") or [])
    _sync_measure_evidence(evidence, frame)
    mitigating_facts = fill.get("mitigating_facts") or {}
    aggravating_facts = fill.get("aggravating_facts") or {}
    draft = {
        "title": fill.get("title"),
        "incident_summary": fill.get("incident_summary"),
        "defendant": _person(fill.get("defendant") or {}, "BI_CAO", statements),
        "victim": _person(fill.get("victim") or {}, "BI_HAI", statements),
        "witnesses": [_person(w, f"NLC_{i}", statements) for i, w in enumerate(witnesses, 1)],
        "related_party": (_person(fill["related_party"], "NLQ", statements)
                          if frame.has_related_party and isinstance(fill.get("related_party"), dict) else None),
        "facts": fill.get("facts") or [],
        "evidence": evidence,
        "pretrial_statements": statements,
        "charge": {"dieu": frame.dieu, "khoan": frame.khoan, "diem": list(frame.diem), "crime_name": frame.crime_name},
        "measure_value": frame.measure_value,
        "defendant_plea": frame.plea,
        "compensation_vnd": frame.compensation_vnd,
        "extra_amounts": fill.get("extra_amounts") or [],
        "mitigating": [{"khoan": "1", "diem": p, "fact_ids": list(mitigating_facts.get(p) or [])}
                       for p in frame.mitigating_points]
                      + [{"khoan": "2", "diem": "", "fact_ids": list(item.get("fact_ids") or [])}
                         for item in fill.get("mitigating_khoan_2") or [] if isinstance(item, dict)],
        "aggravating": [{"khoan": "1", "diem": p, "fact_ids": list(aggravating_facts.get(p) or [])}
                        for p in frame.aggravating_points],
        "civil_claim": fill.get("civil_claim"),
        "indictment_text": fill.get("indictment_text"),
    }
    return draft
