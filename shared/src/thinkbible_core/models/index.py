"""PackIndex: the per-environment list of published books (content/schema/index.schema.json)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from thinkbible_core.models._base import ContractModel, PackVersion, Sha256, TranslationId
from thinkbible_core.models.pack import Book


class FileRef(ContractModel):
    path: str
    sha256: Sha256
    bytes: Annotated[int, Field(ge=1)]


class IndexBook(ContractModel):
    book: Book
    latest: PackVersion
    study: FileRef
    verses: dict[TranslationId, FileRef]
    min_app_format_version: Annotated[int, Field(ge=1)] | None = None


class PackIndex(ContractModel):
    format_version: Literal[1]
    generated_at: datetime
    books: list[IndexBook]
