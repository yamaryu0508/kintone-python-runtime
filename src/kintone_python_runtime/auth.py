from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ApiTokenAuth(BaseModel):
    """Single-app API token authentication."""

    model_config = {"frozen": True}

    token: str = Field(min_length=1)

    @field_validator("token")
    @classmethod
    def strip_token(cls, v: str) -> str:
        t = v.strip()
        if not t:
            msg = "token must not be empty"
            raise ValueError(msg)
        return t

    def headers(self) -> dict[str, str]:
        return {"X-Cybozu-API-Token": self.token}
