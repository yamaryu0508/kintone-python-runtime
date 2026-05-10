from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

import httpx
from aiolimiter import AsyncLimiter

from ._response import raise_for_kintone
from ._urls import normalize_base_url


class HttpSession:
    """Per-tenant HTTP session: httpx client + concurrency + optional rate limit."""

    def __init__(
        self,
        *,
        base_url: str,
        auth_headers: dict[str, str],
        user_agent: str,
        timeout: float,
        http2: bool,
        max_connections: int,
        max_concurrent_requests: int,
        rate_limit_per_second: float | None,
    ) -> None:
        self._base_url = normalize_base_url(base_url)
        limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_connections,
        )
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
            http2=http2,
            limits=limits,
        )
        self._auth_headers = auth_headers
        self._user_agent = user_agent
        self._semaphore = asyncio.Semaphore(max_concurrent_requests)
        self._limiter: AsyncLimiter | None = None
        if rate_limit_per_second is not None and rate_limit_per_second > 0:
            self._limiter = AsyncLimiter(rate_limit_per_second, time_period=1)

    def _headers(self) -> dict[str, str]:
        merged = dict(self._auth_headers)
        merged["User-Agent"] = self._user_agent
        return merged

    @asynccontextmanager
    async def _limit(self) -> AsyncIterator[None]:
        async with self._semaphore:
            if self._limiter is not None:
                async with self._limiter:
                    yield
            else:
                yield

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: list[tuple[str, str | int]] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        async with self._limit():
            return await self._send(method, path, params=params, json_body=json_body)

    async def _send(
        self,
        method: str,
        path: str,
        *,
        params: list[tuple[str, str | int]] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        kw: dict[str, Any] = {"headers": self._headers()}
        if params is not None:
            kw["params"] = params
        if json_body is not None:
            kw["json"] = json_body
        r = await self._client.request(method, path, **kw)
        raise_for_kintone(r)
        return r

    async def post_multipart(
        self,
        path: str,
        *,
        files: dict[str, tuple[str, bytes]],
    ) -> httpx.Response:
        """POST multipart/form-data (e.g. kintone file upload)."""
        async with self._limit():
            r = await self._client.post(path, files=files, headers=self._headers())
            raise_for_kintone(r)
            return r

    async def get_bytes(
        self,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
    ) -> bytes:
        """GET that returns raw body (e.g. kintone file download)."""
        async with self._limit():
            r = await self._client.get(path, params=params, headers=self._headers())
            raise_for_kintone(r)
            return r.content

    async def aclose(self) -> None:
        await self._client.aclose()
