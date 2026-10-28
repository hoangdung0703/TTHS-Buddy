"""Summaries for the biên bản (chặng 3E): parts IV.2 (hỏi và trả lời) and IV.3 (tranh luận) of
Mẫu 22-HS, whose guidance (27)-(28) asks the clerk to record a summary. IV.1 (cáo trạng) and IV.4
(lời nói sau cùng) stay verbatim.

One flash-lite call per session, right after tuyên án. Every section is checked by CODE; a section
that fails is regenerated once, then falls back to verbatim and is flagged. Any error or timeout
also means verbatim: the summary is never needed for the session to be completed. The result,
including a fallback, is stored with the session (verdict_json["record_summary"]) so it is computed
at most once.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.logging import get_logger
from app.prompts.trial_prompts import RECORD_SUMMARY_SYSTEM_PROMPT
from app.services.trial_case_validator import MONEY_PATTERN, parse_money
from app.services.trial_names import NAME_LIKE_PATTERN, placeholders_in
from app.services.trial_rule9 import check_citations, extract_citations
from app.services.trial_state_machine import ROLE_LABELS
from app.services.trial_turn_service import (
    TrialContext,
    _known_numbers,
    _name_to_placeholder,
    _sanitise_student_text,
    role_of,
)

logger = get_logger(__name__)

SECTION_STEPS: dict[str, tuple[int, ...]] = {"iv2": (4, 5), "iv3": (6, 7, 8)}
CONTEXT_STEPS = (9,)
MAX_SECTION_CHARS = 2500
MAX_SOURCE_SHARE = 0.4
MAX_ATTEMPTS = 2
SUMMARY_TIMEOUT_SECONDS = 60
SUMMARY_TEMPERATURE = 0.3
SUMMARY_SCHEMA_VERSION = 1

_SCHEMA = {"type": "OBJECT", "properties": {"iv2": {"type": "STRING"}, "iv3": {"type": "STRING"}},
           "required": ["iv2", "iv3"]}
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_PLACEHOLDER = re.compile(r"\{[A-Z_0-9]+\}")
_MARKDOWN = re.compile(r"\*\*|__|`|^\s{0,3}#|^\s*\*\s", re.MULTILINE)


class _SummaryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    iv2: str
    iv3: str


def _line(ctx: TrialContext, u) -> str:
    label = f"[Bước {u.step}] {{{u.speaker_id}}} ({ROLE_LABELS.get(role_of(u.speaker_id), 'Hệ thống')})"
    if u.is_user:
        return f"{label}: <<<LOI_NGUOI_HOC\n{_sanitise_student_text(_name_to_placeholder(u.text, ctx.case))}\n>>>"
    return f"{label}: {u.text}"


def section_sources(ctx: TrialContext) -> dict[str, str]:
    """Placeholder-form transcript of each summarised section (notices excluded)."""
    return {key: "\n".join(_line(ctx, u) for u in ctx.transcript if u.kind != "notice" and u.step in steps)
            for key, steps in SECTION_STEPS.items()}


def section_limit(source: str) -> int:
    return min(MAX_SECTION_CHARS, int(len(source) * MAX_SOURCE_SHARE))


def _numbers(text: str) -> set[str]:
    return {re.sub(r"[.,]", "", m) for m in _NUMBER.findall(_PLACEHOLDER.sub(" ", text))}


def check_summary(ctx: TrialContext, text: str, source: str, all_sources: str) -> list[str]:
    """Violation labels for one summarised section (labels only, never text)."""
    if not text.strip():
        return ["empty"]
    violations: list[str] = []
    reference = all_sources + "\n" + ctx.case.draft.model_dump_json()
    if _numbers(text) - _numbers(reference):
        violations.append("unknown_number")
    amounts, _ = _known_numbers(ctx)
    amounts |= {parse_money(m.group(1)) for m in MONEY_PATTERN.finditer(reference)}
    if any(parse_money(m.group(1)) not in amounts for m in MONEY_PATTERN.finditer(text)):
        violations.append("unknown_amount")
    violations += [f"citation:{v.label()}" for v in check_citations(text, ctx.pack, "lenient")]
    # Pair rule: every (law, Điều) in the summary was cited in the hearing or the case file.
    cited_in_source = extract_citations(reference)
    if any(not any(s.dieu == c.dieu and (c.law is None or s.law is None or s.law == c.law) for s in cited_in_source)
           for c in extract_citations(text)):
        violations.append("citation_not_in_source")
    if placeholders_in(text) - set(ctx.case.participants):
        violations.append("unknown_placeholder")
    if NAME_LIKE_PATTERN.search(text):
        violations.append("invented_name")
    if _MARKDOWN.search(text):
        violations.append("markdown")
    if len(text) > section_limit(source):
        violations.append("too_long")
    return violations


def _user_prompt(ctx: TrialContext, sources: dict[str, str], todo: list[str], feedback: str) -> str:
    d = ctx.case.draft
    charge = f"{'điểm ' + ', '.join(d.charge.diem) + ' ' if d.charge.diem else ''}khoản {d.charge.khoan} Điều " \
             f"{d.charge.dieu} Bộ luật Hình sự"
    context = "\n".join(_line(ctx, u) for u in ctx.transcript if u.kind != "notice" and u.step in CONTEXT_STEPS)
    parts = [
        "=== TÓM TẮT HỒ SƠ ===\n" + d.incident_summary + f"\nTruy tố: {d.charge.crime_name}, {charge}.",
        "=== MỤC iv2: HỎI VÀ TRẢ LỜI TẠI PHIÊN TÒA ===\n" + (sources["iv2"] or "(không có lời nào)"),
        "=== MỤC iv3: TRANH LUẬN TẠI PHIÊN TÒA ===\n" + (sources["iv3"] or "(không có lời nào)"),
        "=== LỜI NÓI SAU CÙNG (chỉ để tham khảo, KHÔNG tóm tắt) ===\n" + (context or "(không có)"),
        "=== YÊU CẦU ===\n" + "\n".join(
            f"- {key}: tối đa {section_limit(sources[key])} ký tự." for key in todo)
        + f"\nNgười học đóng vai {ROLE_LABELS[ctx.state.user_role]}.",
    ]
    return "\n\n".join(parts) + feedback


async def _generate(ctx: TrialContext) -> dict[str, Any]:
    sources = section_sources(ctx)
    all_sources = "\n".join(sources.values())
    result: dict[str, Any] = {"version": SUMMARY_SCHEMA_VERSION, "iv2": None, "iv3": None, "flags": []}
    todo = [key for key, source in sources.items() if source]
    feedback = ""
    last: dict[str, list[str]] = {}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if not todo:
            break
        response, record = await ctx.recorder.call(
            ctx.settings, call_type="record_summary", slot="bien_ban", attempt=attempt,
            system_prompt=RECORD_SUMMARY_SYSTEM_PROMPT, user_prompt=_user_prompt(ctx, sources, todo, feedback),
            response_schema=_SCHEMA, thinking_level=None, temperature=SUMMARY_TEMPERATURE)
        try:
            out = _SummaryOut.model_validate(json.loads(response.text)).model_dump()
        except (ValueError, ValidationError):
            record.guard_violations, record.accepted = ["schema"], False
            last = {key: ["schema"] for key in todo}
            feedback = "\n\nBẢN TRƯỚC BỊ TỪ CHỐI vì: sai định dạng JSON."
            continue
        failed: dict[str, list[str]] = {}
        for key in todo:
            violations = check_summary(ctx, out[key], sources[key], all_sources)
            if violations:
                failed[key] = violations
            else:
                result[key] = out[key].strip()
        record.guard_violations = sorted({f"{k}:{v}" for k, vs in failed.items() for v in vs})
        record.accepted = not failed
        todo, last = list(failed), failed
        feedback = "\n\nBẢN TRƯỚC BỊ TỪ CHỐI, viết lại các mục: " + "; ".join(
            f"{k} ({', '.join(sorted(set(vs)))})" for k, vs in failed.items()) + \
            ". Chỉ dùng số, Điều, người có trong diễn biến; không markdown; đúng giới hạn ký tự."
    result["flags"] = [f"{key}:verbatim_fallback:{','.join(sorted(set(last.get(key, []))))}" for key in todo]
    return result


async def summarise_record(ctx: TrialContext) -> dict[str, Any]:
    """Always returns a storable result; errors and timeouts become verbatim fallbacks."""
    started = asyncio.get_running_loop().time()
    try:
        result = await asyncio.wait_for(_generate(ctx), SUMMARY_TIMEOUT_SECONDS)
    except TimeoutError:
        result = {"version": SUMMARY_SCHEMA_VERSION, "iv2": None, "iv3": None, "flags": ["timeout"]}
    except Exception as error:  # noqa: BLE001 - a failed summary must never fail the hearing
        result = {"version": SUMMARY_SCHEMA_VERSION, "iv2": None, "iv3": None,
                  "flags": [f"error:{type(error).__name__}"]}
    calls = [r for r in ctx.recorder.records if r.call_type == "record_summary"]
    sources = section_sources(ctx)
    logger.info("TRIAL_RECORD_SUMMARY %s", json.dumps({
        "source_chars": {k: len(v) for k, v in sources.items()},
        "summary_chars": {k: len(result[k]) if result[k] else 0 for k in SECTION_STEPS},
        "calls": len(calls), "prompt_tokens": sum(r.prompt_tokens for r in calls),
        "output_tokens": sum(r.output_tokens for r in calls),
        "latency": round(asyncio.get_running_loop().time() - started, 2), "flags": result["flags"],
    }))
    return result
