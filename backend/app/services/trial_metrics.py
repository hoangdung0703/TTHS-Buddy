"""Per-call measurement for the mock trial: every Gemini call the trial makes goes through
TrialCallRecorder.call, which records call type, latency and token counts (prompt, output,
thinking, cached) and the guard outcome. Used by the spike script now and by request telemetry
later. Records hold counts and labels only - never prompt or answer text."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field

from app.core.config import Settings
from app.services.gemini_client import GeminiJsonResult, generate_json_with_usage


@dataclass
class CallRecord:
    call_type: str
    slot: str
    attempt: int
    latency_seconds: float
    prompt_tokens: int
    output_tokens: int
    thinking_tokens: int
    cached_tokens: int
    thinking_level: str | None
    guard_violations: list[str] = field(default_factory=list)
    accepted: bool = True


@dataclass
class TrialCallRecorder:
    records: list[CallRecord] = field(default_factory=list)

    async def call(self, settings: Settings, *, call_type: str, slot: str, attempt: int, system_prompt: str,
                   user_prompt: str, response_schema: dict, thinking_level: str | None,
                   temperature: float, model: str | None = None) -> tuple[GeminiJsonResult, CallRecord]:
        result = await asyncio.to_thread(
            generate_json_with_usage, system_prompt, user_prompt, settings, response_schema,
            thinking_level=thinking_level, temperature=temperature, model=model,
        )
        record = CallRecord(
            call_type=call_type, slot=slot, attempt=attempt, latency_seconds=round(result.latency_seconds, 3),
            prompt_tokens=result.prompt_tokens, output_tokens=result.output_tokens,
            thinking_tokens=result.thinking_tokens, cached_tokens=result.cached_tokens,
            thinking_level=thinking_level,
        )
        self.records.append(record)
        return result, record

    def as_dicts(self) -> list[dict]:
        return [asdict(r) for r in self.records]
