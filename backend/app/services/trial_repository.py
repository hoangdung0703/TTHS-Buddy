"""Persistence for "Phiên tòa giả định" (migrations 0012, 0014). Every query filters by user_id, so a
session id that exists but belongs to another user behaves exactly like one that does not exist
(the routes answer 404 in both cases, same ownership pattern as notes and conversations).

Two implementations of one interface: SupabaseTrialRepository (production, blocking - callers use
asyncio.to_thread) and InMemoryTrialRepository (unit tests). Concurrency is optimistic: a state
write carries the version it expects, and claiming a session for an AI turn also requires the
generation lock to be free; a write that matches 0 rows returns False and the route answers 409.
Inserts are single attempts (data_access policy: a retried insert could store twice).

The daily limits count USAGE_LOG (migration 0014), one row per successful case creation that outlives
the case: deleting a session or a case never frees quota.
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from supabase import Client

from app.core.data_access import DataUnavailable, execute_with_retry

CASES = "mock_trial_cases"
SESSIONS = "mock_trial_sessions"
UTTERANCES = "mock_trial_utterances"
USAGE_LOG = "mock_trial_usage_log"
# Rows older than this are deleted when a new one is written; the limits only look at one day.
USAGE_RETENTION_DAYS = 35

SESSION_STATE_COLUMNS = ("current_step", "slot_index", "slot_user_turns", "pending_ai", "status", "version")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    # "Z" rather than "+00:00": a literal "+" inside a PostgREST filter value would be read back
    # as a space from the query string.
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class TrialRepository(Protocol):
    def count_usage_since(self, user_id: str, since: datetime) -> int: ...
    def count_all_usage_since(self, since: datetime) -> int: ...
    def log_case_created(self, user_id: str) -> None: ...
    def count_active_sessions(self, user_id: str) -> int: ...
    def abandon_stale(self, user_id: str, cutoff: datetime) -> int: ...
    def insert_case(self, row: dict[str, Any]) -> str: ...
    def delete_case(self, user_id: str, case_id: str) -> None: ...
    def insert_session(self, row: dict[str, Any]) -> str: ...
    def get_session(self, user_id: str, session_id: str) -> dict[str, Any] | None: ...
    def get_case(self, user_id: str, case_id: str) -> dict[str, Any] | None: ...
    def list_sessions(self, user_id: str) -> list[dict[str, Any]]: ...
    def list_utterances(self, user_id: str, session_id: str) -> list[dict[str, Any]]: ...
    def insert_utterances(self, rows: list[dict[str, Any]]) -> None: ...
    def claim_and_update(self, user_id: str, session_id: str, expected_version: int, fields: dict[str, Any],
                         lock_until: datetime | None) -> bool: ...
    def update_state(self, user_id: str, session_id: str, expected_version: int, fields: dict[str, Any]) -> bool: ...
    def release_lock(self, user_id: str, session_id: str) -> None: ...
    def set_status(self, user_id: str, session_id: str, status: str) -> bool: ...
    def delete_session(self, user_id: str, session_id: str) -> bool: ...


class SupabaseTrialRepository:
    def __init__(self, client: Client):
        self.client = client

    def count_usage_since(self, user_id: str, since: datetime) -> int:
        response = execute_with_retry(
            lambda: self.client.table(USAGE_LOG).select("id", count="exact").eq("user_id", user_id)
            .gte("created_at", _iso(since)), "trial: count usage")
        return response.count or 0

    def count_all_usage_since(self, since: datetime) -> int:
        """Every user's creations (service role, no user filter): the system-wide daily cap."""
        response = execute_with_retry(
            lambda: self.client.table(USAGE_LOG).select("id", count="exact").gte("created_at", _iso(since)),
            "trial: count all usage")
        return response.count or 0

    def log_case_created(self, user_id: str) -> None:
        """One row per successful creation, then an opportunistic cleanup that may fail silently
        (the limits only read today's rows)."""
        try:
            self.client.table(USAGE_LOG).insert({"user_id": user_id}).execute()
        except Exception as error:
            raise DataUnavailable("trial: log usage", transient=False) from error
        cutoff = utc_now() - timedelta(days=USAGE_RETENTION_DAYS)
        try:
            self.client.table(USAGE_LOG).delete().lt("created_at", _iso(cutoff)).execute()
        except Exception:  # noqa: BLE001 - retried on the next creation
            pass

    def count_active_sessions(self, user_id: str) -> int:
        response = execute_with_retry(
            lambda: self.client.table(SESSIONS).select("id", count="exact").eq("user_id", user_id)
            .eq("status", "active"), "trial: count active sessions")
        return response.count or 0

    def abandon_stale(self, user_id: str, cutoff: datetime) -> int:
        response = execute_with_retry(
            lambda: self.client.table(SESSIONS).update({"status": "abandoned"}).eq("user_id", user_id)
            .eq("status", "active").lt("updated_at", _iso(cutoff)), "trial: abandon stale sessions")
        return len(response.data or [])

    def insert_case(self, row: dict[str, Any]) -> str:
        return self.client.table(CASES).insert(row).execute().data[0]["id"]

    def delete_case(self, user_id: str, case_id: str) -> None:
        execute_with_retry(lambda: self.client.table(CASES).delete().eq("user_id", user_id).eq("id", case_id),
                           "trial: delete case")

    def insert_session(self, row: dict[str, Any]) -> str:
        return self.client.table(SESSIONS).insert(row).execute().data[0]["id"]

    def get_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        response = execute_with_retry(
            lambda: self.client.table(SESSIONS).select("*").eq("user_id", user_id).eq("id", session_id).limit(1),
            "trial: read session")
        return (response.data or [None])[0]

    def get_case(self, user_id: str, case_id: str) -> dict[str, Any] | None:
        response = execute_with_retry(
            lambda: self.client.table(CASES).select("*").eq("user_id", user_id).eq("id", case_id).limit(1),
            "trial: read case")
        return (response.data or [None])[0]

    def list_sessions(self, user_id: str) -> list[dict[str, Any]]:
        response = execute_with_retry(
            lambda: self.client.table(SESSIONS)
            .select("id, case_id, user_role, current_step, status, updated_at, "
                    "mock_trial_cases(crime_key, title:case_json->draft->>title)")
            .eq("user_id", user_id).order("updated_at", desc=True), "trial: list sessions")
        rows = []
        for row in response.data or []:
            case = row.pop("mock_trial_cases", None) or {}
            rows.append({**row, "crime_key": case.get("crime_key", ""), "title": case.get("title") or ""})
        return rows

    def list_utterances(self, user_id: str, session_id: str) -> list[dict[str, Any]]:
        response = execute_with_retry(
            lambda: self.client.table(UTTERANCES).select("*").eq("user_id", user_id).eq("session_id", session_id)
            .order("seq"), "trial: read utterances")
        return response.data or []

    def insert_utterances(self, rows: list[dict[str, Any]]) -> None:
        if rows:
            self.client.table(UTTERANCES).insert(rows).execute()

    def claim_and_update(self, user_id: str, session_id: str, expected_version: int, fields: dict[str, Any],
                         lock_until: datetime | None) -> bool:
        payload = {**fields, "updated_at": _iso(utc_now()),
                   "generating_until": _iso(lock_until) if lock_until else None}
        response = (self.client.table(SESSIONS).update(payload).eq("user_id", user_id).eq("id", session_id)
                    .eq("version", expected_version)
                    .or_(f"generating_until.is.null,generating_until.lt.{_iso(utc_now())}").execute())
        return len(response.data or []) == 1

    def update_state(self, user_id: str, session_id: str, expected_version: int, fields: dict[str, Any]) -> bool:
        payload = {**fields, "updated_at": _iso(utc_now())}
        response = (self.client.table(SESSIONS).update(payload).eq("user_id", user_id).eq("id", session_id)
                    .eq("version", expected_version).execute())
        return len(response.data or []) == 1

    def release_lock(self, user_id: str, session_id: str) -> None:
        execute_with_retry(lambda: self.client.table(SESSIONS).update({"generating_until": None})
                           .eq("user_id", user_id).eq("id", session_id), "trial: release lock")

    def set_status(self, user_id: str, session_id: str, status: str) -> bool:
        response = execute_with_retry(
            lambda: self.client.table(SESSIONS).update({"status": status, "updated_at": _iso(utc_now())})
            .eq("user_id", user_id).eq("id", session_id), "trial: set status")
        return len(response.data or []) == 1

    def delete_session(self, user_id: str, session_id: str) -> bool:
        session = self.get_session(user_id, session_id)
        if session is None:
            return False
        # Hard delete (decision 2026-10-19): the case row cascades to the session and utterances.
        self.delete_case(user_id, session["case_id"])
        return True


class InMemoryTrialRepository:
    """Test double with the same filtering, version and lock semantics as the Supabase one."""

    def __init__(self) -> None:
        self.usage: list[dict[str, Any]] = []
        # False simulates migration 0014 not run: every usage-log access fails like Supabase would.
        self.usage_available = True
        self.cases: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.utterances: list[dict[str, Any]] = []

    def _usage_rows(self) -> list[dict[str, Any]]:
        if not self.usage_available:
            raise DataUnavailable("trial: usage log", transient=False)
        return self.usage

    def count_usage_since(self, user_id: str, since: datetime) -> int:
        return sum(1 for r in self._usage_rows() if r["user_id"] == user_id and r["created_at"] >= since)

    def count_all_usage_since(self, since: datetime) -> int:
        return sum(1 for r in self._usage_rows() if r["created_at"] >= since)

    def log_case_created(self, user_id: str) -> None:
        rows = self._usage_rows()
        rows.append({"id": str(uuid.uuid4()), "user_id": user_id, "created_at": utc_now()})
        cutoff = utc_now() - timedelta(days=USAGE_RETENTION_DAYS)
        self.usage = [r for r in rows if r["created_at"] >= cutoff]

    def count_active_sessions(self, user_id: str) -> int:
        return sum(1 for s in self.sessions.values() if s["user_id"] == user_id and s["status"] == "active")

    def abandon_stale(self, user_id: str, cutoff: datetime) -> int:
        stale = [s for s in self.sessions.values()
                 if s["user_id"] == user_id and s["status"] == "active" and s["updated_at"] < cutoff]
        for session in stale:
            session["status"] = "abandoned"
        return len(stale)

    def insert_case(self, row: dict[str, Any]) -> str:
        case_id = str(uuid.uuid4())
        self.cases[case_id] = {"created_at": utc_now(), **copy.deepcopy(row), "id": case_id}
        return case_id

    def delete_case(self, user_id: str, case_id: str) -> None:
        case = self.cases.get(case_id)
        if case and case["user_id"] == user_id:
            del self.cases[case_id]
            for sid in [s for s, row in self.sessions.items() if row["case_id"] == case_id]:
                del self.sessions[sid]
                self.utterances = [u for u in self.utterances if u["session_id"] != sid]

    def insert_session(self, row: dict[str, Any]) -> str:
        session_id = str(uuid.uuid4())
        now = utc_now()
        self.sessions[session_id] = {"created_at": now, "updated_at": now, "generating_until": None,
                                     "completed_at": None, **copy.deepcopy(row), "id": session_id}
        return session_id

    def get_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        row = self.sessions.get(session_id)
        return copy.deepcopy(row) if row and row["user_id"] == user_id else None

    def get_case(self, user_id: str, case_id: str) -> dict[str, Any] | None:
        row = self.cases.get(case_id)
        return copy.deepcopy(row) if row and row["user_id"] == user_id else None

    def list_sessions(self, user_id: str) -> list[dict[str, Any]]:
        rows = []
        for s in sorted(self.sessions.values(), key=lambda r: r["updated_at"], reverse=True):
            if s["user_id"] == user_id:
                case = self.cases[s["case_id"]]
                rows.append({**s, "crime_key": case["crime_key"], "title": case["case_json"]["draft"]["title"]})
        return rows

    def list_utterances(self, user_id: str, session_id: str) -> list[dict[str, Any]]:
        return sorted((copy.deepcopy(u) for u in self.utterances
                       if u["session_id"] == session_id and u["user_id"] == user_id), key=lambda u: u["seq"])

    def insert_utterances(self, rows: list[dict[str, Any]]) -> None:
        existing = {(u["session_id"], u["seq"]) for u in self.utterances}
        for row in rows:
            if (row["session_id"], row["seq"]) in existing:
                raise ValueError("duplicate (session_id, seq)")  # the unique constraint of 0012
        self.utterances.extend(copy.deepcopy(rows))

    def _match(self, user_id: str, session_id: str, expected_version: int) -> dict[str, Any] | None:
        row = self.sessions.get(session_id)
        if row is None or row["user_id"] != user_id or row["version"] != expected_version:
            return None
        return row

    def claim_and_update(self, user_id: str, session_id: str, expected_version: int, fields: dict[str, Any],
                         lock_until: datetime | None) -> bool:
        row = self._match(user_id, session_id, expected_version)
        if row is None or (row["generating_until"] is not None and row["generating_until"] >= utc_now()):
            return False
        row.update(copy.deepcopy(fields), updated_at=utc_now(), generating_until=lock_until)
        return True

    def update_state(self, user_id: str, session_id: str, expected_version: int, fields: dict[str, Any]) -> bool:
        row = self._match(user_id, session_id, expected_version)
        if row is None:
            return False
        row.update(copy.deepcopy(fields), updated_at=utc_now())
        return True

    def release_lock(self, user_id: str, session_id: str) -> None:
        row = self.sessions.get(session_id)
        if row and row["user_id"] == user_id:
            row["generating_until"] = None

    def set_status(self, user_id: str, session_id: str, status: str) -> bool:
        row = self.sessions.get(session_id)
        if not row or row["user_id"] != user_id:
            return False
        row.update(status=status, updated_at=utc_now())
        return True

    def delete_session(self, user_id: str, session_id: str) -> bool:
        row = self.sessions.get(session_id)
        if not row or row["user_id"] != user_id:
            return False
        self.delete_case(user_id, row["case_id"])
        return True


def lock_deadline(seconds: int) -> datetime:
    return utc_now() + timedelta(seconds=seconds)
