"""Promote a book's draft version to the live channel (T069, R14, FR-024).

``promote --book B`` copies the exact files of the book's current draft version (same bytes, same
sha256) to ``live/``, then rewrites ``live/v1/index.json`` and invalidates it. It refuses (exit 5)
when:
- the scorecard, recomputed now from the drafts, isn't promotable: failed or ungraded sections,
  pass rates under the thresholds, or no current grader calibration at or above the bar;
- the drafts changed since the draft version was published (publish again first);
- that version is already live;
- the live publish check fails against the current live pack (``publish_check.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from thinkbible_core.ids import resolve_book
from thinkbible_pipeline.config import Settings
from thinkbible_pipeline.drafts.models import BookRef, BookState
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.gate.calibration import CalibrationSet
from thinkbible_pipeline.llm.prompts import system_prompt, version_tag
from thinkbible_pipeline.publish.build import BuildError, build_pack
from thinkbible_pipeline.publish.channel import PackChannel, with_book
from thinkbible_pipeline.publish.publish_check import publish_check
from thinkbible_pipeline.report.scorecard import Scorecard, build_scorecard
from thinkbible_pipeline.sources.snapshot import SourceLibrary


class PromoteRefused(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass
class PromoteResult:
    version: str
    previous: str | None  # the live version it replaced
    files: dict[str, int] = field(default_factory=dict)  # path → bytes


def current_scorecard(
    store: DraftStore, settings: Settings, calibration: CalibrationSet, now: datetime
) -> Scorecard:
    """The scorecard as the ``report`` stage would write it now, from the current drafts."""
    sections = store.read_section_map()
    drafts = {s.id: d for s in sections if (d := store.read_draft(s.id)) is not None}
    review = system_prompt("review", settings)
    return build_scorecard(
        resolve_book(store.book).code,
        sections,
        drafts,
        store.read_runs(),
        now,
        settings=settings,
        calibration=calibration,
        grader=(version_tag(review.versions), settings.stage("review").model),
    )


def promote(
    store: DraftStore,
    library: SourceLibrary,
    draft: PackChannel,
    live: PackChannel,
    card: Scorecard,
    now: datetime,
) -> PromoteResult:
    info = resolve_book(store.book)
    problems = list(card.blockers) if not card.promotable else []
    entry = draft.entry(info.code)
    if entry is None:
        raise PromoteRefused([*problems, f"{info.name} isn't on the draft channel; publish it"])
    new = draft.study(info.code)
    assert new is not None
    try:
        if build_pack(store, library, previous=new, live=live.study(info.code), now=now):
            problems.append(
                f"the drafts changed since {entry.latest} was published; run `publish` first"
            )
    except BuildError as e:
        problems += e.problems
    live_entry = live.entry(info.code)
    if live_entry is not None and live_entry.latest == entry.latest:
        problems.append(f"{info.name} {entry.latest} is already live")
    elif live_entry is not None:
        previous = live.study(info.code)
        assert previous is not None
        problems += publish_check(previous, new)
    if problems:
        raise PromoteRefused(problems)

    refs = [entry.study, *entry.verses.values()]
    copied = {}
    for ref in sorted(refs, key=lambda r: r.path.endswith("study.json")):  # study file last
        data = draft.verified(ref.path, ref.sha256)
        live.put(ref.path, data)
        copied[ref.path] = len(data)
    live.write_index(with_book(live.read_index(), entry, now))
    state = store.read_book() or BookState(
        book=BookRef(id=info.code, name=info.name), status="published-draft"
    )
    state.last_promoted = entry.latest
    state.status = "promoted"
    store.write_book(state)
    return PromoteResult(
        version=entry.latest,
        previous=live_entry.latest if live_entry is not None else None,
        files=copied,
    )
