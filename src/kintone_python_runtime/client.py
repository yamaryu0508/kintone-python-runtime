from __future__ import annotations

from pathlib import Path

from ._session import HttpSession
from .auth import ApiTokenAuth
from .declarative import ExecutionBackend, RunSpec
from .files import Files
from .records import Records
from .runtime import RunHandle, spawn_run
from .version import __version__

__all__ = [
    "ApiTokenAuth",
    "KintoneClient",
    "__version__",
]


class KintoneClient:
    """
    Async kintone REST API client (one instance per kintone domain / auth).

    Resources: ``records`` (レコード API), ``files`` (ファイル API)。
    Use ``async with`` or call ``await aclose()`` when done.
    """

    def __init__(
        self,
        base_url: str,
        *,
        auth: ApiTokenAuth,
        guest_space_id: str | int | None = None,
        timeout: float = 30.0,
        max_connections: int = 100,
        max_concurrent_requests: int = 10,
        rate_limit_per_second: float | None = None,
        http2: bool = True,
        user_agent: str | None = None,
        state_dir: str = ".kintone_runs",
        redis_url: str | None = None,
    ) -> None:
        ua = user_agent or f"kintone_python_runtime/{__version__}; python"
        self._guest = guest_space_id
        self._state_dir = state_dir
        self._redis_url = redis_url
        self._http = HttpSession(
            base_url=base_url,
            auth_headers=auth.headers(),
            user_agent=ua,
            timeout=timeout,
            http2=http2,
            max_connections=max_connections,
            max_concurrent_requests=max_concurrent_requests,
            rate_limit_per_second=rate_limit_per_second,
        )
        self.records = Records(self._http, guest_space_id)
        self.files = Files(self._http, guest_space_id)

    @property
    def guest_space_id(self) -> str | int | None:
        return self._guest

    def run(
        self,
        spec: RunSpec,
        *,
        backend: ExecutionBackend | None = None,
    ) -> RunHandle:
        if backend is not None:
            spec = spec.model_copy(update={"backend": backend})
        return spawn_run(
            client=self,
            spec=spec,
            state_dir=Path(self._state_dir),
            redis_url=self._redis_url,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> KintoneClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()
