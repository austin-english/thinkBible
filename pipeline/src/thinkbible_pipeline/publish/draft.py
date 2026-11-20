"""Publish a book to the draft channel (T072, R14).

A run that includes ``report`` and leaves no section failed ends here, and so does
``publish --book B``. The pack is built from the drafts (``build.py``), its files are written
under ``draft/v1/books/{book}/{version}/``, and then ``draft/v1/index.json`` is rewritten and
invalidated. A book with any section not generated, not graded or failed is not published: a pack
covers every verse of its book. The draft channel skips the live publish check, so a book can be
regenerated and republished freely before it first goes live.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from thinkbible_core.ids import resolve_book
from thinkbible_core.models.index import FileRef, IndexBook
from thinkbible_core.models.pack import Book
from thinkbible_pipeline.drafts.models import BookRef, BookState
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.jsonio import sha256_hex
from thinkbible_pipeline.publish.build import BuildError, BuiltPack, build_pack
from thinkbible_pipeline.publish.channel import PackChannel, book_folder, with_book
from thinkbible_pipeline.sources.snapshot import SourceLibrary


@dataclass
class PublishResult:
    version: str | None  # the version now on the draft channel (None: nothing published yet)
    published: bool  # False when nothing changed, or on a dry run
    change: str | None = None  # first, minor or patch
    files: dict[str, int] = field(default_factory=dict)  # path → bytes


def index_entry(code: str, version: str, files: dict[str, bytes]) -> IndexBook:
    folder = book_folder(code, version)

    def ref(name: str) -> FileRef:
        data = files[name]
        return FileRef(path=f"{folder}/{name}", sha256=sha256_hex(data), bytes=len(data))

    verses = {
        name.removeprefix("verses/").removesuffix(".json"): ref(name)
        for name in files
        if name.startswith("verses/")
    }
    info = resolve_book(code)
    return IndexBook(
        book=Book(id=info.code, name=info.name),
        latest=version,
        study=ref("study.json"),
        verses=verses,
    )


def publish_draft(
    store: DraftStore,
    library: SourceLibrary,
    draft: PackChannel,
    live: PackChannel,
    now: datetime,
    *,
    dry_run: bool = False,
) -> PublishResult:
    """Build the book's pack and put it on the draft channel. Raises ``BuildError``."""
    info = resolve_book(store.book)
    previous = draft.study(info.code)
    built: BuiltPack | None = build_pack(
        store, library, previous=previous, live=live.study(info.code), now=now
    )
    if built is None:
        return PublishResult(version=previous.pack_version if previous else None, published=False)
    sizes = {f"{book_folder(info.code, built.version)}/{n}": len(d) for n, d in built.files.items()}
    if dry_run:
        return PublishResult(built.version, published=False, change=built.change, files=sizes)
    folder = book_folder(info.code, built.version)
    for name, data in sorted(built.files.items(), key=lambda kv: kv[0] == "study.json"):
        draft.put(f"{folder}/{name}", data)  # verse files first, the study file last
    draft.write_index(
        with_book(draft.read_index(), index_entry(info.code, built.version, built.files), now)
    )
    state = store.read_book() or BookState(
        book=BookRef(id=info.code, name=info.name), status="gated"
    )
    state.draft_version = built.version
    state.status = "published-draft"
    store.write_book(state)
    return PublishResult(built.version, published=True, change=built.change, files=sizes)


def problem_summary(problems: list[str]) -> str:
    """A short reason a book can't be published yet: counts for incomplete sections."""
    counts = {
        label: sum(1 for p in problems if p.endswith(suffix) or f": {suffix}" in p)
        for label, suffix in (("not generated", "not generated"), ("not graded", "not graded"))
    }
    failed = sum(1 for p in problems if ": failed (" in p)
    parts = [f"{n} sections {label}" for label, n in counts.items() if n]
    if failed:
        parts.append(f"{failed} sections failed")
    other = [
        p
        for p in problems
        if not (p.endswith(("not generated", "not graded")) or ": failed (" in p)
    ]
    return "; ".join(parts + other[:3]) + (
        f" (and {len(other) - 3} more)" if len(other) > 3 else ""
    )


def publish_after_run(
    store: DraftStore,
    library: SourceLibrary | None,
    channels: tuple[PackChannel, PackChannel] | None,
    now: datetime,
    echo: Callable[[str], None],
) -> str:
    """The end of a run with ``report`` and no failed section (R14): publish if the book is whole.

    Never fails the run: a book that isn't complete yet, or a channel that isn't set up, is
    reported and left for later. Returns the line it echoed.
    """
    if channels is None:
        line = "publish: skipped (no packs bucket or CDN in the configuration yet)"
    elif library is None:
        line = "publish: skipped (no source snapshot for the verse files)"
    else:
        try:
            result = publish_draft(store, library, *channels, now)
        except BuildError as e:
            line = f"publish: not published ({problem_summary(e.problems)})"
        else:
            line = (
                f"publish: {result.version} on the draft channel ({result.change})"
                if result.published
                else f"publish: unchanged ({result.version} is on the draft channel)"
            )
    echo(line)
    return line
