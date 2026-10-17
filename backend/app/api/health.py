import os
import re

from fastapi import APIRouter

from app.models.health import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])

# Render sets RENDER_GIT_COMMIT to the commit SHA of the running deploy, at build time AND at
# runtime (https://render.com/docs/environment-variables, "default environment variables"). It
# answers "which commit is live?" from outside - so far that was only answerable by probing for
# routes a given commit added or removed. A commit SHA is not sensitive, but the value is still
# validated rather than echoed, so this endpoint can never reflect anything else placed in that
# variable: anything that is not a hex SHA reports "unknown", as does its absence (local runs).
_COMMIT_SHA = re.compile(r"[0-9a-f]{7,40}")
SHORT_SHA_LENGTH = 7


def running_version() -> str:
    sha = (os.getenv("RENDER_GIT_COMMIT") or "").strip().lower()
    return sha[:SHORT_SHA_LENGTH] if _COMMIT_SHA.fullmatch(sha) else "unknown"


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    return HealthResponse(version=running_version())
