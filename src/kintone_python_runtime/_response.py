from __future__ import annotations

import httpx

from .errors import KintoneAPIError


def raise_for_kintone(response: httpx.Response) -> None:
    if response.is_success:
        return
    body: object
    try:
        body = response.json()
    except ValueError:
        body = response.text
    message = response.reason_phrase or "request failed"
    if isinstance(body, dict):
        raw_msg = body.get("message")
        if raw_msg is not None:
            message = str(raw_msg)
    raise KintoneAPIError(
        message,
        status_code=response.status_code,
        url=str(response.request.url),
        method=response.request.method,
        body=body,
    )
