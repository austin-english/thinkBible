"""The ``summaries`` stage (T053): one line on each section, from the passage alone (Haiku).

``generate`` gives the model the previous section's summary, so it knows what came just before
without the cost of the previous section's text.
"""

from __future__ import annotations

from typing import Any

from thinkbible_pipeline.drafts.models import SectionDraft, SectionMapEntry
from thinkbible_pipeline.jsonio import sha256_hex
from thinkbible_pipeline.llm.outputs import SummaryOut
from thinkbible_pipeline.llm.prompts import system_prompt, version_tag
from thinkbible_pipeline.sections.passage import passage_text
from thinkbible_pipeline.stages.base import Deps, SectionResult, SectionStage


def section_entry(section_id: str, deps: Deps) -> SectionMapEntry:
    entry = next((s for s in deps.store.read_section_map() if s.id == section_id), None)
    if entry is None:
        raise LookupError(f"{section_id} is not in sections.json: run the sections stage")
    return entry


def reference(book_name: str, entry: SectionMapEntry) -> str:
    return f"{book_name} {entry.chapter}:{entry.verse_start}-{entry.verse_end}"


class SummariesStage(SectionStage):
    name = "summaries"

    def prompt_version(self, deps: Deps) -> str:
        return version_tag(system_prompt(self.name, deps.settings).versions)

    def model(self, deps: Deps) -> str:
        return deps.settings.stage(self.name).model

    def inputs(self, section_id: str, draft: SectionDraft, deps: Deps) -> Any:
        entry = section_entry(section_id, deps)
        book = deps.store.book.upper()
        return {
            "section": entry.to_doc(),
            "passage": sha256_hex(passage_text(deps.sources, "bsb", book, entry).encode()),
        }

    async def execute(
        self, section_id: str, inputs: Any, draft: SectionDraft, deps: Deps
    ) -> SectionResult:
        from thinkbible_core.ids import resolve_book

        entry = section_entry(section_id, deps)
        book = resolve_book(deps.store.book)
        user = (
            f'Section {section_id}: {reference(book.name, entry)}, "{entry.title}"\n\n'
            f'<passage translation="BSB">\n'
            f"{passage_text(deps.sources, 'bsb', book.code, entry)}\n</passage>"
        )
        out, usage = await deps.runner.parse(
            self.name,
            system_prompt(self.name, deps.settings).blocks,
            user,
            SummaryOut,
            section_id=section_id,
        )
        draft.summary = out.summary.strip()
        return SectionResult(usages=[usage])
