"""StudyPack and its provenance (content/schema/study-pack.schema.json)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from thinkbible_core.models._base import (
    BookCode,
    ContractModel,
    PackVersion,
    Sha256,
    TranslationId,
)
from thinkbible_core.models.section import Section


class Book(ContractModel):
    id: BookCode
    name: str


class TranslationRef(ContractModel):
    id: TranslationId
    name: str
    abbreviation: Annotated[str, StringConstraints(max_length=8)]
    path: str
    sha256: Sha256


class Source(ContractModel):
    id: str
    kind: Literal["translation", "commentary"]
    name: str
    short_name: str
    tradition: str | None = None
    license: str
    license_url: str
    origin: str
    api_version: str | None = None
    retrieved_at: date
    upstream_sha256: Sha256
    snapshot_sha256: Sha256


class Build(ContractModel):
    prompt_versions: dict[str, str]
    question_guide_version: str
    models: dict[str, str]


class StudyPack(ContractModel):
    format_version: Literal[1]
    book: Book
    pack_version: PackVersion
    published_at: datetime
    translations: Annotated[list[TranslationRef], Field(min_length=1)]
    sources: Annotated[list[Source], Field(min_length=1)]
    build: Build
    sections: Annotated[list[Section], Field(min_length=1)]
