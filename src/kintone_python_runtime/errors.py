from __future__ import annotations

from typing import Any


class KintoneAPIError(Exception):
    """Raised when the kintone API returns a non-success response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        url: str | None = None,
        method: str | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url
        self.method = method
        self.body = body
