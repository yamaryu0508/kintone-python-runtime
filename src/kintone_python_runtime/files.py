from __future__ import annotations

import asyncio
from pathlib import Path

from ._session import HttpSession
from ._urls import api_path
from .models import UploadFileResponse


class Files:
    """kintone file upload/download (/k/v1/file) — async only."""

    def __init__(self, session: HttpSession, guest_space_id: str | int | None) -> None:
        self._session = session
        self._guest = guest_space_id

    def _path(self, path: str) -> str:
        return api_path(path, guest_space_id=self._guest)

    async def upload(self, *, filename: str, data: bytes) -> UploadFileResponse:
        """Upload bytes as multipart ``file`` (kintone field name)."""
        path = self._path("/k/v1/file")
        files = {"file": (filename, data)}
        r = await self._session.post_multipart(path, files=files)
        return UploadFileResponse.model_validate(r.json())

    async def upload_path(self, path: Path, *, filename: str | None = None) -> UploadFileResponse:
        """Read a local path (blocking I/O in a thread) and upload."""
        data = await asyncio.to_thread(path.read_bytes)
        name = filename if filename is not None else path.name
        return await self.upload(filename=name, data=data)

    async def download(self, file_key: str) -> bytes:
        """Download file body by ``fileKey``."""
        path = self._path("/k/v1/file")
        return await self._session.get_bytes(path, params={"fileKey": file_key})
