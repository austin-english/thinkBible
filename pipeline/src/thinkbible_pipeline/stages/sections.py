"""The ``sections`` stage: write the book's section map (research R5, FR-004). No model calls.

The map is rebuilt from the BSB headings and Henry's divisions on every run, and written only when
it changed. Once the book has been promoted to the live channel its sections are frozen (FR-024):
a different map is reported and not written.
"""

from __future__ import annotations

from thinkbible_pipeline.drafts.models import BookRef, BookState, SectionMapEntry
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.sections.builder import build_sections
from thinkbible_pipeline.stages.base import BookStage, Deps


class SectionsStage(BookStage):
    name = "sections"

    def _build(self, request: RunRequest, deps: Deps) -> list[SectionMapEntry]:
        code = request.book_info.code
        return build_sections(
            code,
            deps.sources.translation("bsb", code),
            deps.sources.commentary("matthew-henry", code),
        )

    def planned_section_ids(self, request: RunRequest, deps: Deps) -> list[str]:
        state = deps.store.read_book()
        if state is not None and state.last_promoted:
            return deps.store.section_ids()
        return [s.id for s in self._build(request, deps)]

    async def run_book(self, request: RunRequest, deps: Deps) -> None:
        info = request.book_info
        store = deps.store
        built = self._build(request, deps)
        existing = store.read_section_map()
        state = store.read_book() or BookState(
            book=BookRef(id=info.code, name=info.name), status="sectioned"
        )
        if built == existing:
            deps.echo(f"sections: unchanged ({len(built)} sections)")
            if store.read_book() is None:
                store.write_book(state)
            return
        if state.last_promoted:
            deps.echo(
                f"sections: {info.name} is live, so its sections are frozen (FR-024); "
                "the rebuilt map differs and was not written"
            )
            return
        store.write_section_map(built)
        state.status = "sectioned"
        store.write_book(state)
        provisional = sum(s.title_source == "split" for s in built)
        deps.echo(
            f"sections: wrote {len(built)} sections"
            + (f" ({provisional} with a provisional '(cont.)' title)" if provisional else "")
        )
