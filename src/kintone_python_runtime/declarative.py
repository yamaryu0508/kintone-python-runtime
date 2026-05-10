from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RecordWriteMode(StrEnum):
    INSERT = "insert"
    UPDATE = "update"
    UPSERT = "upsert"
    QUERY = "query"


class ExecutionBackend(StrEnum):
    LOCAL = "local"
    REDIS = "redis"


class RateLimitSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    per_second: float = Field(gt=0)


class RecordOperationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app: int
    records: list[dict[str, Any]] = Field(default_factory=list)
    mode: RecordWriteMode = RecordWriteMode.UPSERT
    query: str | None = None
    fields: list[str] | None = None
    total_count: bool = False
    chunk_size: int = Field(default=100, ge=1, le=100)
    concurrency: int = Field(default=5, ge=1, le=100)
    continue_on_error: bool = False

    @model_validator(mode="after")
    def _records_match_mode(self) -> RecordOperationSpec:
        if self.mode is RecordWriteMode.QUERY:
            if self.records:
                msg = "QUERY mode does not use records; pass query/fields instead"
                raise ValueError(msg)
            return self
        if not self.records:
            msg = "write modes require at least one record in records"
            raise ValueError(msg)
        return self


class RunSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operations: list[RecordOperationSpec] = Field(min_length=1)
    backend: ExecutionBackend = ExecutionBackend.LOCAL
    run_id: str | None = None
    rate_limit: RateLimitSpec | None = None

    def resolved_run_id(self) -> str:
        return self.run_id or f"run-{uuid4().hex}"


EventType = Literal[
    "run_started",
    "operation_started",
    "chunk_succeeded",
    "chunk_failed",
    "operation_finished",
    "run_finished",
]


class RunEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    type: EventType
    at: datetime
    operation_index: int | None = None
    chunk_index: int | None = None
    total_chunks: int | None = None
    message: str | None = None
    data: dict[str, Any] | None = None
    error: str | None = None

    @classmethod
    def now(
        cls,
        *,
        run_id: str,
        type: EventType,
        operation_index: int | None = None,
        chunk_index: int | None = None,
        total_chunks: int | None = None,
        message: str | None = None,
        data: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> RunEvent:
        return cls(
            run_id=run_id,
            type=type,
            at=datetime.now(UTC),
            operation_index=operation_index,
            chunk_index=chunk_index,
            total_chunks=total_chunks,
            message=message,
            data=data,
            error=error,
        )


class RunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    succeeded_chunks: int = 0
    failed_chunks: int = 0
    succeeded_records: int = 0
    failed_operations: int = 0
