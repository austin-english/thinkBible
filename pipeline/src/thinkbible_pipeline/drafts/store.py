"""Read and write a book's drafts (data-model §2) in a ``BlobStore``: S3 in the cloud, a folder
in tests and early local runs. Keys are relative to the store, e.g. ``mrk/sections/mrk-1-1.json``.
"""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel

from thinkbible_pipeline.drafts.models import (
    BookState,
    RunRecord,
    SectionDraft,
    SectionMap,
    SectionMapEntry,
)
from thinkbible_pipeline.jsonio import JsonModel, canonical_json
from thinkbible_pipeline.storage import BlobStore

M = TypeVar("M", bound=BaseModel)


class DraftStore:
    def __init__(self, book_slug: str, blobs: BlobStore) -> None:
        self.book = book_slug
        self.blobs = blobs

    # --- keys ---

    def key(self, name: str) -> str:
        return f"{self.book}/{name}"

    @property
    def book_key(self) -> str:
        return self.key("book.json")

    @property
    def sections_key(self) -> str:
        return self.key("sections.json")

    def section_key(self, section_id: str) -> str:
        return self.key(f"sections/{section_id}.json")

    @property
    def runs_prefix(self) -> str:
        return self.key("runs/")

    def run_key(self, record: RunRecord) -> str:
        return f"{self.runs_prefix}{record.run_id}-{record.stage}.json"

    # --- generic ---

    def _read(self, key: str, model: type[M]) -> M | None:
        blob = self.blobs.get(key)
        return model.model_validate_json(blob.data) if blob else None

    def _write(self, key: str, value: JsonModel) -> None:
        self.blobs.put(key, canonical_json(value.to_doc()).encode())

    # --- book.json ---

    def read_book(self) -> BookState | None:
        return self._read(self.book_key, BookState)

    def write_book(self, state: BookState) -> None:
        self._write(self.book_key, state)

    # --- sections.json ---

    def read_section_map(self) -> list[SectionMapEntry]:
        m = self._read(self.sections_key, SectionMap)
        return m.sections if m else []

    def write_section_map(self, sections: list[SectionMapEntry]) -> None:
        self._write(self.sections_key, SectionMap(sections=sections))

    def section_ids(self) -> list[str]:
        return [s.id for s in self.read_section_map()]

    # --- sections/{id}.json ---

    def read_draft(self, section_id: str) -> SectionDraft | None:
        return self._read(self.section_key(section_id), SectionDraft)

    def read_draft_or_new(self, section_id: str) -> SectionDraft:
        return self.read_draft(section_id) or SectionDraft()

    def write_draft(self, section_id: str, draft: SectionDraft) -> None:
        self._write(self.section_key(section_id), draft)

    # --- runs/{runId}-{stage}.json (one object per stage run, so writers never collide) ---

    def read_runs(self) -> list[RunRecord]:
        """Every run record, oldest first (run IDs start with a UTC timestamp)."""
        records = []
        for key, _etag in self.blobs.list(self.runs_prefix):
            blob = self.blobs.get(key)
            if blob is not None:
                records.append(RunRecord.model_validate_json(blob.data))
        return sorted(records, key=lambda r: (r.started_at, r.run_id, r.stage))

    def write_run(self, record: RunRecord) -> None:
        self._write(self.run_key(record), record)

    # --- report files (scorecard.json, review.html) ---

    def write_text(self, name: str, text: str, content_type: str) -> None:
        self.blobs.put(self.key(name), text.encode(), content_type=content_type)

    def read_text(self, name: str) -> str | None:
        blob = self.blobs.get(self.key(name))
        return blob.data.decode() if blob else None

    def read_json(self, name: str) -> object | None:
        text = self.read_text(name)
        return json.loads(text) if text is not None else None
