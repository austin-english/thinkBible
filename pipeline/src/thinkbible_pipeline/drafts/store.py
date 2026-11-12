"""Read and write a book's drafts in ``content/drafts/{book}/`` as canonical JSON."""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, TypeAdapter

from thinkbible_pipeline.drafts.models import (
    Approval,
    BookState,
    RunRecord,
    SectionDraft,
    SectionMap,
    SectionMapEntry,
)
from thinkbible_pipeline.jsonio import JsonModel, read_json, write_json
from thinkbible_pipeline.paths import RepoPaths, repo_paths

M = TypeVar("M", bound=BaseModel)
_RUNS = TypeAdapter(list[RunRecord])


class DraftStore:
    def __init__(self, book_slug: str, paths: RepoPaths | None = None) -> None:
        self.book = book_slug
        self.dir: Path = (paths or repo_paths()).drafts(book_slug)

    # --- paths ---

    @property
    def book_path(self) -> Path:
        return self.dir / "book.json"

    @property
    def sections_path(self) -> Path:
        return self.dir / "sections.json"

    def section_path(self, section_id: str) -> Path:
        return self.dir / "sections" / f"{section_id}.json"

    def generated_path(self, section_id: str) -> Path:
        return self.dir / ".generated" / f"{section_id}.json"

    @property
    def runs_path(self) -> Path:
        return self.dir / "runs.json"

    @property
    def approval_path(self) -> Path:
        return self.dir / "approval.json"

    # --- generic ---

    @staticmethod
    def _read(path: Path, model: type[M]) -> M | None:
        return model.model_validate(read_json(path)) if path.is_file() else None

    @staticmethod
    def _write(path: Path, value: JsonModel) -> None:
        write_json(path, value.to_doc())

    # --- book.json ---

    def read_book(self) -> BookState | None:
        return self._read(self.book_path, BookState)

    def write_book(self, state: BookState) -> None:
        self._write(self.book_path, state)

    # --- sections.json ---

    def read_section_map(self) -> list[SectionMapEntry]:
        m = self._read(self.sections_path, SectionMap)
        return m.sections if m else []

    def write_section_map(self, sections: list[SectionMapEntry]) -> None:
        self._write(self.sections_path, SectionMap(sections=sections))

    def section_ids(self) -> list[str]:
        return [s.id for s in self.read_section_map()]

    # --- sections/{id}.json and .generated/{id}.json ---

    def read_draft(self, section_id: str) -> SectionDraft | None:
        return self._read(self.section_path(section_id), SectionDraft)

    def read_draft_or_new(self, section_id: str) -> SectionDraft:
        return self.read_draft(section_id) or SectionDraft()

    def write_draft(self, section_id: str, draft: SectionDraft) -> None:
        self._write(self.section_path(section_id), draft)

    def read_generated(self, section_id: str) -> SectionDraft | None:
        return self._read(self.generated_path(section_id), SectionDraft)

    def write_generated(self, section_id: str, draft: SectionDraft) -> None:
        self._write(self.generated_path(section_id), draft)

    # --- runs.json (append-only) ---

    def read_runs(self) -> list[RunRecord]:
        if not self.runs_path.is_file():
            return []
        return _RUNS.validate_python(read_json(self.runs_path))

    def append_run(self, record: RunRecord) -> None:
        runs = [r.to_doc() for r in self.read_runs()]
        runs.append(record.to_doc())
        write_json(self.runs_path, runs)

    # --- approval.json ---

    def read_approval(self) -> Approval | None:
        return self._read(self.approval_path, Approval)

    def write_approval(self, approval: Approval) -> None:
        self._write(self.approval_path, approval)
