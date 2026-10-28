"""Field-level repair of a generated case draft (chặng 3G).

When every validator error sits in an identifiable free-text field (a money amount that matches
nothing declared, an invented name, a statement too short or missing...), the model is asked to
rewrite ONLY those fields; code splices them back into the draft and the full validator runs again.
Any other error (structure, knobs, measure, schema...) still means a full regeneration. Thresholds
are unchanged: the repaired draft must pass exactly the same checks.

Measured before (seeds 7001-7012): money_mismatch, statement_count and invented_name were the
three most frequent failures, and all three are field-local.
"""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.services.trial_case_validator import error_label

# Labels whose message starts with "<field path>: ".
_PATH_PREFIXED = frozenset({"money_mismatch", "percent_mismatch", "invented_name", "placeholder_unknown",
                            "minor_mention", "text_citation", "indictment_citation"})
_PATH = re.compile(
    r"^(statement\[[A-Z_0-9]+\]\.(?:summary|inconsistencies\[\d+\])"
    r"|[A-Z_0-9]+\.(?:statement_summary|stance|demeanor|occupation|description|time|place|knowledge\[\d+\])"
    r"|incident_summary|indictment_text|title|extra_amounts\[\d+\]\.label): ")
_STATEMENT_OF = re.compile(r"^Lời khai của ([A-Z_0-9]+) ")
_DUPLICATE_PAIR = re.compile(r"^Lời khai của [A-Z_0-9]+ và ([A-Z_0-9]+) gần như trùng nhau")
_MISSING_STATEMENT = re.compile(r"; ([A-Z_0-9]+) có 0$")

REPAIR_SCHEMA = {"type": "OBJECT", "properties": {"fields": {"type": "ARRAY", "items": {
    "type": "OBJECT", "properties": {"path": {"type": "STRING"}, "text": {"type": "STRING"}},
    "required": ["path", "text"]}}}, "required": ["fields"]}


class _Field(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    text: str


class _RepairOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: list[_Field]


def _path_of(error: str) -> str | None:
    label = error_label(error)
    if label in _PATH_PREFIXED:
        match = _PATH.match(error)
        return match.group(1) if match else None
    if label == "statement_words":
        match = _STATEMENT_OF.match(error)
        return f"statement[{match.group(1)}].summary" if match else None
    if label == "statement_duplicate":
        match = _DUPLICATE_PAIR.match(error)
        return f"statement[{match.group(1)}].summary" if match else None
    if label == "statement_count":
        match = _MISSING_STATEMENT.search(error)   # more than one is merged by code; only "0" is left
        return f"statement[{match.group(1)}].summary" if match else None
    if label == "indictment_words":
        return "indictment_text"
    return None


def repair_plan(errors: list[str], draft: dict) -> dict[str, list[str]] | None:
    """{field path: its errors} when EVERY error is repairable field by field, else None."""
    plan: dict[str, list[str]] = {}
    for error in errors:
        path = _path_of(error)
        if path is None or (not path.startswith("statement[") and get_field(draft, path) is None):
            return None
        plan.setdefault(path, []).append(error)
    return plan or None


def _statement(draft: dict, pid: str, create: bool = False) -> dict | None:
    for statement in draft.get("pretrial_statements") or []:
        if isinstance(statement, dict) and statement.get("person_id") == pid:
            return statement
    if not create:
        return None
    statement = {"person_id": pid, "summary": "", "inconsistencies": []}
    draft.setdefault("pretrial_statements", []).append(statement)
    return statement


def _locate(draft: dict, path: str, create: bool = False) -> tuple[Any, Any] | None:
    """(container, key) of a text field, or None if the path does not exist."""
    if m := re.fullmatch(r"statement\[([A-Z_0-9]+)\]\.(summary|inconsistencies\[(\d+)\])", path):
        statement = _statement(draft, m.group(1), create=create and m.group(2) == "summary")
        if statement is None:
            return None
        if m.group(3) is None:
            return statement, "summary"
        items = statement.get("inconsistencies") or []
        index = int(m.group(3))
        return (items[index], "text") if index < len(items) and isinstance(items[index], dict) else None
    if m := re.fullmatch(r"extra_amounts\[(\d+)\]\.label", path):
        items = draft.get("extra_amounts") or []
        index = int(m.group(1))
        return (items[index], "label") if index < len(items) else None
    if path in ("incident_summary", "indictment_text", "title"):
        return draft, path
    owner, _, field = path.partition(".")
    if m := re.fullmatch(r"knowledge\[(\d+)\]", field):
        field, index = "knowledge", int(m.group(1))
    else:
        index = None
    people = [draft.get("defendant"), draft.get("victim"), *(draft.get("witnesses") or []), draft.get("related_party")]
    for item in [*people, *(draft.get("facts") or []), *(draft.get("evidence") or [])]:
        if isinstance(item, dict) and item.get("id") == owner and field in item:
            if index is None:
                return item, field
            values = item[field]
            return (values, index) if isinstance(values, list) and index < len(values) else None
    return None


def get_field(draft: dict, path: str) -> str | None:
    located = _locate(draft, path)
    if located is None:
        return None
    container, key = located
    value = container[key]
    return value if isinstance(value, str) else None


class RepairNotApplied(ValueError):
    """The answer changed none of the fields asked for."""


def _normalise_path(path: str) -> str:
    # Ids may come back in placeholder form ("statement[{NLC_1}].summary"), as in case generation.
    return re.sub(r"[{}\s]", "", path)


def apply_repair(draft: dict, plan: dict[str, list[str]], raw: str) -> dict:
    """Splice the repaired texts into a copy of the draft. Paths not asked for are ignored; an
    answer that changes no asked-for field raises RepairNotApplied."""
    out = _RepairOut.model_validate(json.loads(raw))
    repaired = json.loads(json.dumps(draft))
    applied = 0
    for field in out.fields:
        path = _normalise_path(field.path)
        if path in plan and field.text.strip() and field.text != get_field(draft, path):
            located = _locate(repaired, path, create=True)
            if located is not None:
                container, key = located
                container[key] = field.text
                applied += 1
    if not applied:
        raise RepairNotApplied("no field repaired")
    return repaired
