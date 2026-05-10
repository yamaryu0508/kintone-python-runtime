from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Protocol

import anyio
from aiolimiter import AsyncLimiter
from anyio.abc import ObjectReceiveStream
from pydantic import ValidationError

from .declarative import (
    ExecutionBackend,
    RecordOperationSpec,
    RecordWriteMode,
    RunEvent,
    RunSpec,
    RunSummary,
)

EventSink = Callable[[RunEvent], Awaitable[None]]


def _chunk(records: list[dict], chunk_size: int) -> list[list[dict]]:
    return [records[i : i + chunk_size] for i in range(0, len(records), chunk_size)]


class RecordsAPI(Protocol):
    async def add_records(self, app: int, records: list[dict]) -> object: ...

    async def update_records(
        self,
        app: int,
        records: list[dict],
        *,
        upsert: bool = False,
    ) -> object: ...


class RuntimeWithRecords(Protocol):
    @property
    def records(self) -> RecordsAPI: ...


class DeclarativeRunner(Protocol):
    async def execute(self, spec: RunSpec, run_id: str, emit: EventSink) -> RunSummary: ...


class RunHandle:
    def __init__(
        self,
        *,
        run_id: str,
        receiver: ObjectReceiveStream[RunEvent],
        task: asyncio.Task[RunSummary],
    ) -> None:
        self.run_id = run_id
        self._receiver = receiver
        self._task = task

    async def events(self) -> AsyncIterator[RunEvent]:
        async with self._receiver:
            async for event in self._receiver:
                yield event

    async def wait(self) -> RunSummary:
        return await self._task


class LocalRunner:
    def __init__(self, runtime: RuntimeWithRecords, *, state_dir: Path) -> None:
        self._runtime = runtime
        self._state_dir = state_dir
        self._state_dir.mkdir(parents=True, exist_ok=True)

    async def execute(self, spec: RunSpec, run_id: str, emit: EventSink) -> RunSummary:
        summary = RunSummary(run_id=run_id)
        db_path = self._state_dir / "runs.sqlite3"
        event_log = self._state_dir / f"{run_id}.events.jsonl"
        self._init_sqlite(db_path)
        self._upsert_run_row(db_path, run_id, "running")

        await emit(RunEvent.now(run_id=run_id, type="run_started", message="run started"))
        try:
            for op_idx, operation in enumerate(spec.operations):
                await self._execute_operation(
                    db_path=db_path,
                    event_log=event_log,
                    run_id=run_id,
                    operation=operation,
                    operation_index=op_idx,
                    summary=summary,
                    emit=emit,
                    limiter=AsyncLimiter(spec.rate_limit.per_second, 1)
                    if spec.rate_limit is not None
                    else None,
                )
            self._upsert_run_row(db_path, run_id, "finished")
            await emit(
                RunEvent.now(
                    run_id=run_id,
                    type="run_finished",
                    message="run finished",
                    data=summary.model_dump(mode="json"),
                )
            )
            return summary
        except Exception:
            self._upsert_run_row(db_path, run_id, "failed")
            raise

    async def _execute_operation(
        self,
        *,
        db_path: Path,
        event_log: Path,
        run_id: str,
        operation: RecordOperationSpec,
        operation_index: int,
        summary: RunSummary,
        emit: EventSink,
        limiter: AsyncLimiter | None,
    ) -> None:
        chunks = _chunk(operation.records, operation.chunk_size)
        total_chunks = len(chunks)
        await emit(
            RunEvent.now(
                run_id=run_id,
                type="operation_started",
                operation_index=operation_index,
                total_chunks=total_chunks,
                data={"app": operation.app, "mode": operation.mode.value},
            )
        )
        semaphore = anyio.Semaphore(operation.concurrency)
        local_errors: list[str] = []

        async def worker(chunk_index: int, chunk_records: list[dict]) -> None:
            async with semaphore:
                if limiter is not None:
                    async with limiter:
                        await self._write_chunk(
                            db_path,
                            event_log,
                            run_id,
                            operation,
                            operation_index,
                            chunk_index,
                            total_chunks,
                            chunk_records,
                            summary,
                            local_errors,
                            emit,
                        )
                    return
                await self._write_chunk(
                    db_path,
                    event_log,
                    run_id,
                    operation,
                    operation_index,
                    chunk_index,
                    total_chunks,
                    chunk_records,
                    summary,
                    local_errors,
                    emit,
                )

        async with anyio.create_task_group() as tg:
            for chunk_index, chunk_records in enumerate(chunks):
                tg.start_soon(worker, chunk_index, chunk_records)

        if local_errors and not operation.continue_on_error:
            summary.failed_operations += 1
            msg = f"operation {operation_index} failed: {local_errors[0]}"
            raise RuntimeError(msg)

        await emit(
            RunEvent.now(
                run_id=run_id,
                type="operation_finished",
                operation_index=operation_index,
                total_chunks=total_chunks,
                data={"errors": len(local_errors)},
            )
        )

    async def _write_chunk(
        self,
        db_path: Path,
        event_log: Path,
        run_id: str,
        operation: RecordOperationSpec,
        operation_index: int,
        chunk_index: int,
        total_chunks: int,
        chunk_records: list[dict],
        summary: RunSummary,
        local_errors: list[str],
        emit: EventSink,
    ) -> None:
        try:
            if operation.mode is RecordWriteMode.INSERT:
                await self._runtime.records.add_records(operation.app, chunk_records)
            elif operation.mode is RecordWriteMode.UPDATE:
                await self._runtime.records.update_records(operation.app, chunk_records)
            else:
                await self._runtime.records.update_records(
                    operation.app, chunk_records, upsert=True
                )

            summary.succeeded_chunks += 1
            summary.succeeded_records += len(chunk_records)
            event = RunEvent.now(
                run_id=run_id,
                type="chunk_succeeded",
                operation_index=operation_index,
                chunk_index=chunk_index,
                total_chunks=total_chunks,
                data={"records": len(chunk_records)},
            )
            await emit(event)
            self._append_event_log(event_log, event)
            self._mark_chunk(db_path, run_id, operation_index, chunk_index, "ok", None)
        except Exception as exc:
            summary.failed_chunks += 1
            local_errors.append(str(exc))
            event = RunEvent.now(
                run_id=run_id,
                type="chunk_failed",
                operation_index=operation_index,
                chunk_index=chunk_index,
                total_chunks=total_chunks,
                error=str(exc),
            )
            await emit(event)
            self._append_event_log(event_log, event)
            self._mark_chunk(db_path, run_id, operation_index, chunk_index, "ng", str(exc))
            if not operation.continue_on_error:
                raise

    @staticmethod
    def _init_sqlite(db_path: Path) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    run_id TEXT NOT NULL,
                    operation_index INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (run_id, operation_index, chunk_index)
                )
                """
            )

    @staticmethod
    def _upsert_run_row(db_path: Path, run_id: str, status: str) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO runs (run_id, status) VALUES (?, ?)
                ON CONFLICT(run_id) DO UPDATE
                SET status=excluded.status, updated_at=CURRENT_TIMESTAMP
                """,
                (run_id, status),
            )

    @staticmethod
    def _mark_chunk(
        db_path: Path,
        run_id: str,
        operation_index: int,
        chunk_index: int,
        status: str,
        error: str | None,
    ) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO chunks (run_id, operation_index, chunk_index, status, error)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id, operation_index, chunk_index)
                DO UPDATE
                SET status=excluded.status, error=excluded.error, updated_at=CURRENT_TIMESTAMP
                """,
                (run_id, operation_index, chunk_index, status, error),
            )

    @staticmethod
    def _append_event_log(path: Path, event: RunEvent) -> None:
        line = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
        with path.open("a", encoding="utf-8") as fp:
            fp.write(line + "\n")


class RedisRunner(LocalRunner):
    def __init__(
        self,
        runtime: RuntimeWithRecords,
        *,
        state_dir: Path,
        redis_url: str,
        namespace: str = "krc",
    ) -> None:
        super().__init__(runtime, state_dir=state_dir)
        self._redis_url = redis_url
        self._namespace = namespace

    async def execute(self, spec: RunSpec, run_id: str, emit: EventSink) -> RunSummary:
        redis = await self._connect_redis()
        try:
            await redis.hset(f"{self._namespace}:runs:{run_id}", mapping={"status": "running"})
            summary = await super().execute(spec, run_id, emit)
            await redis.hset(
                f"{self._namespace}:runs:{run_id}",
                mapping={"status": "finished", "summary": summary.model_dump_json()},
            )
            return summary
        except Exception as exc:
            await redis.hset(
                f"{self._namespace}:runs:{run_id}",
                mapping={"status": "failed", "error": str(exc)},
            )
            raise
        finally:
            await redis.aclose()

    async def _connect_redis(self):
        try:
            from redis.asyncio import Redis  # pyright: ignore[reportMissingImports]
        except ImportError as exc:
            msg = "Redis backend requires extras: uv sync --extra redis"
            raise RuntimeError(msg) from exc
        redis = Redis.from_url(self._redis_url, decode_responses=True)
        try:
            await redis.ping()
        except Exception as exc:  # pragma: no cover - integration env dependent
            msg = f"failed to connect redis: {self._redis_url}"
            raise RuntimeError(msg) from exc
        return redis


def create_runner(
    runtime: RuntimeWithRecords,
    *,
    backend: ExecutionBackend,
    state_dir: Path,
    redis_url: str | None,
) -> DeclarativeRunner:
    if backend is ExecutionBackend.LOCAL:
        return LocalRunner(runtime, state_dir=state_dir)
    if redis_url is None:
        msg = "backend='redis' requires redis_url"
        raise ValueError(msg)
    return RedisRunner(runtime, state_dir=state_dir, redis_url=redis_url)


def spawn_run(
    *,
    runtime: RuntimeWithRecords,
    spec: RunSpec,
    state_dir: Path,
    redis_url: str | None,
) -> RunHandle:
    run_id = spec.resolved_run_id()
    send_stream, receive_stream = anyio.create_memory_object_stream[RunEvent](1024)
    runner = create_runner(runtime, backend=spec.backend, state_dir=state_dir, redis_url=redis_url)

    async def emit(event: RunEvent) -> None:
        await send_stream.send(event)

    async def _execute() -> RunSummary:
        async with send_stream:
            try:
                return await runner.execute(spec, run_id, emit)
            except ValidationError as exc:
                await emit(
                    RunEvent.now(
                        run_id=run_id,
                        type="run_finished",
                        message="validation failed",
                        error=str(exc),
                    )
                )
                raise

    task = asyncio.create_task(_execute())
    return RunHandle(run_id=run_id, receiver=receive_stream, task=task)
