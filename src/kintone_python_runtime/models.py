from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GetRecordsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    records: list[dict[str, Any]]
    totalCount: str | None = None


class AddRecordResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    revision: str


class AddRecordsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ids: list[str]
    revisions: list[str]


class UpdateRecordResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    revision: str


class UpdatedRecordItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    revision: str


class UpdateRecordsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    records: list[UpdatedRecordItem] = Field(default_factory=list)


class UploadFileResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fileKey: str
