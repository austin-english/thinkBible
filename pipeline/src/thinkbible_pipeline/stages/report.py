"""The ``report`` stage (T055, R17): ``scorecard.json`` and ``review.html`` for the whole book.

Runs at the end of every run (``all``), with no model calls. It reads every section draft and the
latest run's records, writes the scorecard and the review page to the drafts store, and moves the
book's status along the data-model state machine (``generated``, or ``failed`` when a section
failed). ``status --book B --open`` opens the page.
"""

from __future__ import annotations

from thinkbible_core.ids import resolve_book
from thinkbible_pipeline.drafts.models import BookRef, BookState
from thinkbible_pipeline.jsonio import canonical_json
from thinkbible_pipeline.report.render import render_review
from thinkbible_pipeline.report.scorecard import build_scorecard
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.stages.base import BookStage, Deps


class ReportStage(BookStage):
    name = "report"

    async def run_book(self, request: RunRequest, deps: Deps) -> None:
        store = deps.store
        info = resolve_book(store.book)
        sections = store.read_section_map()
        drafts = {s.id: d for s in sections if (d := store.read_draft(s.id)) is not None}
        card = build_scorecard(info.code, sections, drafts, store.read_runs(), deps.clock())
        store.write_text("scorecard.json", canonical_json(card.to_doc()), "application/json")
        html = render_review(card, sections, drafts, deps.sources)
        store.write_text("review.html", html, "text/html; charset=utf-8")

        state = store.read_book() or BookState(
            book=BookRef(id=info.code, name=info.name), status="sectioned"
        )
        if state.status in ("sectioned", "generating", "generated", "failed") and sections:
            if card.failed_sections:
                state.status = "failed"
            elif not card.not_generated:
                state.status = "generated"
            store.write_book(state)
        deps.echo(
            f"report: {card.ideas.passed} key ideas and {card.questions.passed} questions kept, "
            f"{len(card.failed_sections)} failed, {len(card.not_generated)} not generated; "
            "review.html written"
        )
