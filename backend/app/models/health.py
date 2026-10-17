from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    # Short commit SHA of the code actually running, or "unknown" - see api/health.py.
    version: str = "unknown"
