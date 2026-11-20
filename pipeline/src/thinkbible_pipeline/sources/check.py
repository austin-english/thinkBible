"""``sources check``: is the imported text complete and in the right place? (research R2a)

``verify`` proves files are unchanged since import; this proves they were right to begin with.
It reads every cached book and checks it against the KJV versification:

- **Errors** (exit 2): a translation missing a book, chapter or verse number out of range,
  duplicate or empty verses; a commentary note on a verse that doesn't exist, or notes out of
  order or overlapping.
- **Warnings**: a commentary missing a book or chapter, undecodable characters.
- **Summary**: verses per translation (with the verses it omits), and per commentary the share of
  verses with a note of their own, characters and references.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from thinkbible_core.ids import BOOKS
from thinkbible_pipeline.sources.models import (
    NormalizedCommentaryBook,
    NormalizedTranslationBook,
    SourceManifest,
    SubtitleItem,
    VerseItem,
)
from thinkbible_pipeline.sources.snapshot import SourceError, SourceStore, load_book
from thinkbible_pipeline.sources.versification import KJV_VERSES


@dataclass
class SourceReport:
    source: str
    kind: str
    origin: str | None
    books: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class CheckReport:
    sources: list[SourceReport]

    @property
    def ok(self) -> bool:
        return not any(r.errors for r in self.sources)


def _check_translation(book: NormalizedTranslationBook, r: SourceReport, stats: dict[str, int],
                       omitted: list[str]) -> None:  # fmt: skip
    code = book.book
    expected = KJV_VERSES[code]
    numbers = [c.number for c in book.chapters]
    if numbers != list(range(1, len(expected) + 1)):
        r.errors.append(f"{code}: chapters {numbers[:5]}…, expected 1 to {len(expected)}")
    for ch in book.chapters:
        if not 1 <= ch.number <= len(expected):
            continue
        verses = [i for i in ch.items if isinstance(i, VerseItem)]
        nums = [v.number for v in verses]
        stats["verses"] += len(nums)
        stats["titles"] += sum(isinstance(i, SubtitleItem) for i in ch.items)
        if len(nums) != len(set(nums)):
            r.errors.append(f"{code} {ch.number}: duplicate verse numbers")
        beyond = [n for n in nums if n > expected[ch.number - 1]]
        if beyond:
            r.errors.append(f"{code} {ch.number}: verses {beyond} beyond the KJV's last verse")
        r.errors.extend(f"{code} {ch.number}:{v.number}: empty" for v in verses if not v.text)
        omitted.extend(
            f"{code} {ch.number}:{n}"
            for n in sorted(set(range(1, expected[ch.number - 1] + 1)) - set(nums))
        )


def _check_commentary(book: NormalizedCommentaryBook, r: SourceReport,
                      stats: dict[str, int]) -> None:  # fmt: skip
    code = book.book
    expected = KJV_VERSES[code]
    present = {c.number for c in book.chapters}
    missing = sorted(set(range(1, len(expected) + 1)) - present)
    if missing:
        r.warnings.append(f"{code}: no notes on chapters {missing}")
    texts = [book.introduction] if book.introduction else []
    for ch in book.chapters:
        if not 1 <= ch.number <= len(expected):
            r.errors.append(f"{code} {ch.number}: chapter out of range")
            continue
        last = expected[ch.number - 1]
        stats["verses"] += last
        if ch.introduction:
            texts.append(ch.introduction)
        end_prev = 0
        for item in ch.items:
            end = item.verse_end or item.verse
            if end < item.verse or end > last:
                r.errors.append(f"{code} {ch.number}:{item.verse}-{end}: outside 1 to {last}")
                continue
            if item.verse <= end_prev:
                r.errors.append(f"{code} {ch.number}:{item.verse}: out of order or overlapping")
            stats["covered"] += end - item.verse + 1
            stats["notes"] += 1
            end_prev = end
            texts.append(item)
    for t in texts:
        stats["chars"] += len(t.text)
        stats["refs"] += len(t.refs)
        if "�" in t.text:
            stats["bad_chars"] += 1


def check_sources(*, store: SourceStore, manifest: SourceManifest) -> CheckReport:
    reports: list[SourceReport] = []
    for source, entry in sorted(manifest.sources.items()):
        r = SourceReport(source=source, kind=entry.kind, origin=entry.origin)
        stats = dict.fromkeys(
            ("verses", "titles", "covered", "notes", "chars", "refs", "bad_chars"), 0
        )
        omitted: list[str] = []
        for info in BOOKS:
            if info.code not in entry.books:
                (r.errors if entry.kind == "translation" else r.warnings).append(
                    f"{info.code}: not in the snapshot"
                )
                continue
            try:
                book = load_book(source, info.code, store=store, manifest=manifest)
            except SourceError as e:
                r.errors.append(f"{info.code}: {e}")
                continue
            r.books += 1
            if isinstance(book, NormalizedTranslationBook):
                _check_translation(book, r, stats, omitted)
            else:
                _check_commentary(book, r, stats)
        if entry.kind == "translation":
            r.summary = f"{stats['verses']:,} verses, {stats['titles']} psalm titles"
            if omitted:
                shown = ", ".join(omitted[:20]) + (" …" if len(omitted) > 20 else "")
                r.summary += f"; omits {len(omitted)}: {shown}"
        else:
            share = stats["covered"] / stats["verses"] if stats["verses"] else 0.0
            r.summary = (
                f"{stats['notes']:,} notes covering {share:.0%} of verses, "
                f"{stats['chars'] / 1e6:.1f}M characters, {stats['refs']:,} references"
            )
            if stats["bad_chars"]:
                r.warnings.append(f"{stats['bad_chars']} notes contain undecodable characters")
        reports.append(r)
    return CheckReport(reports)
