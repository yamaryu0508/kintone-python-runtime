from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from ._session import HttpSession
from ._urls import api_path
from .bulk import run_in_chunks
from .models import (
    AddRecordResponse,
    AddRecordsResponse,
    GetRecordsResponse,
    UpdateRecordResponse,
    UpdateRecordsResponse,
)


class Records:
    """kintone record APIs (/k/v1/record(s)) — async only."""

    def __init__(self, session: HttpSession, guest_space_id: str | int | None) -> None:
        self._session = session
        self._guest = guest_space_id

    def _path(self, path: str) -> str:
        return api_path(path, guest_space_id=self._guest)

    async def get_records(
        self,
        app: int,
        *,
        query: str | None = None,
        fields: list[str] | None = None,
        total_count: bool = False,
    ) -> GetRecordsResponse:
        path = self._path("/k/v1/records")
        params: list[tuple[str, str | int]] = [("app", app)]
        if query is not None:
            params.append(("query", query))
        if total_count:
            params.append(("totalCount", "true"))
        for f in fields or []:
            params.append(("fields", f))
        r = await self._session.request("GET", path, params=params)
        return GetRecordsResponse.model_validate(r.json())

    async def iterate_records_by_id(
        self,
        app: int,
        *,
        condition: str | None = None,
        fields: list[str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream all records using $id cursor paging (500 rows per request).

        Yields one record dict at a time (kintone field shape: {"field": {"value": ...}}).
        """
        last_id = 0
        selected = list(fields) if fields else []
        if "$id" not in selected:
            selected = [*selected, "$id"]

        while True:
            inner = f"$id > {last_id} order by $id asc limit 500"
            q = f"({condition}) and ({inner})" if condition else inner
            page = await self.get_records(app, query=q, fields=selected or None)
            rows = page.records
            if not rows:
                break
            for row in rows:
                yield row
            if len(rows) < 500:
                break
            last_id = int(rows[-1]["$id"]["value"])

    async def add_record(self, app: int, record: dict[str, Any]) -> AddRecordResponse:
        path = self._path("/k/v1/record")
        body = {"app": app, "record": record}
        r = await self._session.request("POST", path, json_body=body)
        return AddRecordResponse.model_validate(r.json())

    async def add_records(self, app: int, records: list[dict[str, Any]]) -> AddRecordsResponse:
        path = self._path("/k/v1/records")
        body = {"app": app, "records": records}
        r = await self._session.request("POST", path, json_body=body)
        return AddRecordsResponse.model_validate(r.json())

    async def update_record(
        self,
        app: int,
        record_id: int,
        record: dict[str, Any],
        *,
        revision: str | int | None = None,
    ) -> UpdateRecordResponse:
        path = self._path("/k/v1/record")
        body: dict[str, Any] = {"app": app, "id": record_id, "record": record}
        if revision is not None:
            body["revision"] = str(revision)
        r = await self._session.request("PUT", path, json_body=body)
        return UpdateRecordResponse.model_validate(r.json())

    async def update_records(
        self,
        app: int,
        records: list[dict[str, Any]],
        *,
        upsert: bool = False,
    ) -> UpdateRecordsResponse:
        path = self._path("/k/v1/records")
        body: dict[str, Any] = {"app": app, "records": records}
        if upsert:
            body["upsert"] = True
        r = await self._session.request("PUT", path, json_body=body)
        return UpdateRecordsResponse.model_validate(r.json())

    async def add_records_chunked(
        self,
        app: int,
        records: list[dict[str, Any]],
        *,
        chunk_size: int = 100,
        concurrency: int = 5,
    ) -> AddRecordsResponse:
        if chunk_size > 100:
            msg = "kintone allows at most 100 records per add_records request"
            raise ValueError(msg)

        async def proc(chunk: list[dict[str, Any]]) -> AddRecordsResponse:
            return await self.add_records(app, chunk)

        parts = await run_in_chunks(records, chunk_size, proc, concurrency=concurrency)
        ids: list[str] = []
        revs: list[str] = []
        for p in parts:
            ids.extend(p.ids)
            revs.extend(p.revisions)
        return AddRecordsResponse(ids=ids, revisions=revs)

    async def update_records_chunked(
        self,
        app: int,
        records: list[dict[str, Any]],
        *,
        chunk_size: int = 100,
        concurrency: int = 5,
    ) -> UpdateRecordsResponse:
        if chunk_size > 100:
            msg = "kintone allows at most 100 records per update_records request"
            raise ValueError(msg)

        async def proc(chunk: list[dict[str, Any]]) -> UpdateRecordsResponse:
            return await self.update_records(app, chunk)

        parts = await run_in_chunks(records, chunk_size, proc, concurrency=concurrency)
        merged = [item for p in parts for item in p.records]
        return UpdateRecordsResponse(records=merged)
