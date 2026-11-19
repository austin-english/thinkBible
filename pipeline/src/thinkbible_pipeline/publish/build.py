"""Build a book's study pack and verse files from its drafts (T070, R13, R14, data-model §1).

What goes in:
- **Sections**: every entry of the section map, in order, from its draft. Every section must be
  generated, graded and not failed, and its draft must be for the section's current verses (a
  changed section map means generating again). Dropped items never reach a draft's ``section``, so
  they are never published.
- **The book introduction**: from the first section's draft, when it has one.
- **Verse files**: one per translation (BSB first, the default), from the frozen snapshot, with
  paragraph starts, poetry lines (indent at most 4), psalm titles (a chapter's ``title``, T088)
  and the verses of the KJV versification the translation omits. Editorial headings are left out.
- **Provenance**: every translation and commentary used, with its license and checksums (FR-023),
  and the prompt versions and models each stage used (FR-013).

**Versions** (R13): the first publish is ``1.0.0``. Against the book's previous draft pack, items
added or retired bump the minor version; any other change (wording of notes, verse text, the
introduction, provenance) bumps the patch; no change publishes nothing. The new version is bumped
from the higher of the previous draft and live versions, so versions only increase. An item's
``addedIn`` is the version it reached the live channel with, or the new version if it never has.

Everything is validated before anything is written: the Pydantic contract models, the JSON
Schemas, and the cross-field rules (``thinkbible_core.rules``), including that the sections cover
every verse of both translations and that every verse placeholder resolves.
"""

from __future__ import annotations

import copy
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

from pydantic import ValidationError

from thinkbible_core.ids import resolve_book
from thinkbible_core.models.pack import Book, Build, Source, StudyPack, TranslationRef
from thinkbible_core.models.section import BookIntroduction, KeyIdea, Question, Section
from thinkbible_core.models.verses import (
    Chapter,
    OmittedVerse,
    PoetryLine,
    TranslationInfo,
    VerseEntry,
    VerseText,
)
from thinkbible_core.rules import cross_field_violations
from thinkbible_core.schema import validate
from thinkbible_pipeline.commentary.gather import COMMENTATORS
from thinkbible_pipeline.drafts.models import SectionDraft, SectionMapEntry
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.jsonio import compact_canonical, sha256_hex
from thinkbible_pipeline.sources.models import (
    BreakItem,
    HeadingItem,
    SourceEntry,
    SubtitleItem,
    VerseItem,
)
from thinkbible_pipeline.sources.snapshot import SourceLibrary
from thinkbible_pipeline.sources.versification import KJV_VERSES

FORMAT_VERSION: Literal[1] = 1
TRANSLATIONS: tuple[str, ...] = ("bsb", "kjv")  # the first is the app's default
SHORT_NAMES = {
    "bsb": "BSB",
    "kjv": "KJV",
    "matthew-henry": "Henry",
    "jamieson-fausset-brown": "JFB",
    "adam-clarke": "Clarke",
}
MAX_INDENT = 4  # verses.schema.json poetry line indent
_PLACEHOLDER_VERSION = "0.0.0"  # items' versions while the content is compared
_QUESTION_GUIDE = re.compile(r"question-guide@(v\d+)")

Change = Literal["first", "minor", "patch"]


class BuildError(Exception):
    """The drafts can't make a valid pack; ``problems`` says why, one line each."""

    def __init__(self, problems: list[str]) -> None:
        shown = "; ".join(problems[:5])
        more = f" (and {len(problems) - 5} more)" if len(problems) > 5 else ""
        super().__init__(shown + more)
        self.problems = problems


@dataclass
class BuiltPack:
    version: str
    change: Change
    study: StudyPack
    verses: dict[str, VerseText]
    # The bytes of each file, by its path inside the version's folder: study.json, verses/bsb.json
    files: dict[str, bytes] = field(default_factory=dict)


def encode(doc: Any) -> bytes:
    """A published file's bytes: sorted keys, no whitespace (the CDN compresses them)."""
    return (compact_canonical(doc) + "\n").encode()


def parse_version(version: str) -> tuple[int, int, int]:
    major, minor, patch = (int(p) for p in version.split("."))
    return major, minor, patch


def next_version(base: str | None, change: Change) -> str:
    if base is None or change == "first":
        return "1.0.0"
    major, minor, patch = parse_version(base)
    return f"{major}.{minor + 1}.0" if change == "minor" else f"{major}.{minor}.{patch + 1}"


def _highest(*versions: str | None) -> str | None:
    known = [v for v in versions if v is not None]
    return max(known, key=parse_version) if known else None


# --- sections ---


def _section_problem(entry: SectionMapEntry, draft: SectionDraft | None) -> str | None:
    if draft is None or "generate" not in draft.stages:
        return f"{entry.id}: not generated"
    if draft.failed:
        return f"{entry.id}: failed ({draft.failed})"
    review = draft.stages.get("review")
    if review is None or review.status != "done":
        return f"{entry.id}: not graded"
    s = draft.section
    drafted = (s.get("chapter"), s.get("verseStart"), s.get("verseEnd"))
    if drafted != (entry.chapter, entry.verse_start, entry.verse_end):
        return (
            f"{entry.id}: the draft is for {drafted[0]}:{drafted[1]}-{drafted[2]}, but the section "
            f"map says {entry.chapter}:{entry.verse_start}-{entry.verse_end}; generate it again"
        )
    return None


def _set_versions(
    doc: dict[str, Any], added: dict[str, str], version: str, retired: dict[str, str] | None = None
) -> dict[str, Any]:
    """A section doc whose items carry ``addedIn``, and ``retiredIn`` when retired: the version they
    went live (or were retired) with on the live channel, else this one."""
    out = copy.deepcopy(doc)
    for kind in ("keyIdeas", "questions"):
        for item in out.get(kind, []):
            item["addedIn"] = added.get(item["id"], version)
            if item.get("status") == "retired":
                item["retiredIn"] = (retired or {}).get(item["id"], version)
    return out


def _sections(
    docs: list[dict[str, Any]],
    added: dict[str, str],
    version: str,
    retired: dict[str, str] | None = None,
) -> tuple[list[Section], list[str]]:
    sections: list[Section] = []
    problems: list[str] = []
    for doc in docs:
        try:
            sections.append(Section.model_validate(_set_versions(doc, added, version, retired)))
        except ValidationError as e:
            for err in e.errors():
                where = ".".join(str(p) for p in err["loc"])
                problems.append(f"{doc.get('id')}: {where}: {err['msg']}")
    return sections, problems


def _content(sections: list[Section]) -> list[dict[str, Any]]:
    """Sections as compared between versions: without the items' version fields."""
    out = []
    for s in sections:
        doc = s.to_doc()
        for kind in ("keyIdeas", "questions"):
            for item in doc.get(kind, []):
                item.pop("addedIn", None)
                item.pop("retiredIn", None)
        out.append(doc)
    return out


def section_items(section: Section) -> list[KeyIdea | Question]:
    return [*section.key_ideas, *section.questions]


def _items(sections: list[Section]) -> set[tuple[str, str]]:
    return {(i.id, i.status) for s in sections for i in section_items(s)}


def _added_in(live: StudyPack | None) -> dict[str, str]:
    if live is None:
        return {}
    return {i.id: i.added_in for s in live.sections for i in section_items(s)}


def _retired_in(live: StudyPack | None) -> dict[str, str]:
    if live is None:
        return {}
    return {i.id: i.retired_in for s in live.sections for i in section_items(s) if i.retired_in}


# --- provenance ---


def _license_url(entry: SourceEntry) -> str | None:
    if entry.license_url:
        return entry.license_url
    if (entry.origin or "").startswith("crosswire:"):
        return f"https://www.crosswire.org/sword/modules/ModInfo.jsp?modName={entry.api_id}"
    return None


def _sources(library: SourceLibrary, code: str) -> tuple[list[Source], list[str]]:
    sources: list[Source] = []
    problems: list[str] = []
    for source_id in (*TRANSLATIONS, *COMMENTATORS):
        entry = library.manifest.sources.get(source_id)
        book = entry.books.get(code) if entry is not None else None
        if entry is None or book is None:
            if source_id in TRANSLATIONS:
                problems.append(f"the snapshot has no {source_id} text of {code}")
            continue
        url = _license_url(entry)
        if url is None or entry.upstream_sha256 is None:
            problems.append(
                f"manifest.json lacks the license URL or upstream sha256 of {source_id}"
            )
            continue
        sources.append(
            Source(
                id=source_id,
                kind=entry.kind,
                name=entry.name,
                short_name=SHORT_NAMES.get(source_id, entry.api_id),
                tradition=entry.tradition,
                license=entry.license,
                license_url=url,
                origin=entry.origin or entry.api_id,
                api_version=library.manifest.api_version if entry.kind == "translation" else None,
                retrieved_at=date.fromisoformat(book.retrieved_at[:10]),
                upstream_sha256=entry.upstream_sha256,
                snapshot_sha256=book.sha256,
            )
        )
    return sources, problems


def _build_info(drafts: list[SectionDraft]) -> Build:
    prompts: dict[str, set[str]] = defaultdict(set)
    models: dict[str, set[str]] = defaultdict(set)
    for d in drafts:
        for stage, record in d.stages.items():
            prompts[stage].add(record.prompt_version)
            if record.model:
                models[stage].add(record.model)
    guides = sorted(
        {m.group(1) for v in prompts.get("generate", ()) for m in _QUESTION_GUIDE.finditer(v)}
    )
    return Build(
        prompt_versions={k: ", ".join(sorted(v)) for k, v in sorted(prompts.items())},
        question_guide_version=", ".join(guides) or "none",
        models={k: ", ".join(sorted(v)) for k, v in sorted(models.items())},
    )


# --- verse files ---


def verse_text(
    library: SourceLibrary, translation: str, code: str, book_name: str, version: str
) -> VerseText:
    """One translation's text of the book, in the verses.schema.json shape."""
    source = library.translation(translation, code)
    entry = library.manifest.sources[translation]
    by_number = {c.number: c for c in source.chapters}
    chapters: list[Chapter] = []
    omitted: list[OmittedVerse] = []
    for number, verse_count in enumerate(KJV_VERSES[code], start=1):
        verses: list[VerseEntry] = []
        titles: list[str] = []  # a psalm's title (the translation's own text, not a heading)
        paragraph = True  # a chapter starts a paragraph
        chapter = by_number.get(number)
        for item in chapter.items if chapter else []:
            if isinstance(item, SubtitleItem):
                if not verses and item.text.strip():
                    titles.append(item.text.strip())
                paragraph = True
            elif isinstance(item, HeadingItem):
                paragraph = True
            elif isinstance(item, BreakItem):
                paragraph = paragraph or item.paragraph
            elif isinstance(item, VerseItem) and item.text.strip():
                lines = (
                    [
                        PoetryLine(text=ln.text, indent=min(ln.indent, MAX_INDENT))
                        for ln in item.lines
                    ]
                    if item.lines
                    else None
                )
                verses.append(
                    VerseEntry(
                        number=item.number,
                        text=item.text,
                        paragraph_start=True if paragraph else None,
                        lines=lines,
                    )
                )
                paragraph = False
        present = {v.number for v in verses}
        omitted += [
            OmittedVerse(chapter=number, verse=v)
            for v in range(1, verse_count + 1)
            if v not in present
        ]
        if verses:
            chapters.append(Chapter(number=number, title=" ".join(titles) or None, verses=verses))
    return VerseText(
        format_version=FORMAT_VERSION,
        book=Book(id=code, name=book_name),
        translation=TranslationInfo(
            id=translation, name=entry.name, abbreviation=SHORT_NAMES.get(translation, translation)
        ),
        pack_version=version,
        chapters=chapters,
        omitted_verses=omitted,
    )


# --- the pack ---


def build_pack(
    store: DraftStore,
    library: SourceLibrary,
    *,
    previous: StudyPack | None,
    live: StudyPack | None,
    now: datetime,
) -> BuiltPack | None:
    """The book's next pack, or None when nothing changed since ``previous`` (the draft channel's).

    ``live`` is the live channel's current pack, for the items' ``addedIn``. Raises ``BuildError``.
    """
    info = resolve_book(store.book)
    code = info.code
    entries = store.read_section_map()
    if not entries:
        raise BuildError([f"{code} has no section map; run the sections stage"])
    drafts = {e.id: store.read_draft(e.id) for e in entries}
    problems = [p for e in entries if (p := _section_problem(e, drafts[e.id])) is not None]
    sources, source_problems = _sources(library, code)
    problems += source_problems
    if problems:
        raise BuildError(problems)
    ready = [d for d in drafts.values() if d is not None]
    docs = [
        {**copy.deepcopy(d.section), "title": e.title} for e, d in zip(entries, ready, strict=True)
    ]
    first = ready[0].book_intro
    introduction = (
        BookIntroduction.model_validate(first.introduction)
        if first is not None and first.introduction
        else None
    )

    # Compare the content with the previous draft pack to choose the version.
    sections, problems = _sections(docs, {}, _PLACEHOLDER_VERSION)
    if problems:
        raise BuildError(problems)
    if previous is None:
        change: Change | None = "first"
    elif _items(sections) != _items(previous.sections):
        change = "minor"
    elif (
        _content(sections) != _content(previous.sections)
        or introduction != previous.introduction
        or sources != previous.sources
    ):
        change = "patch"
    else:
        change = None
    if change is None:
        return None
    base = _highest(
        previous.pack_version if previous else None, live.pack_version if live else None
    )
    # With nothing on the draft channel but a live version, the new draft is the next minor.
    version = next_version(base, "minor" if change == "first" and base else change)

    sections, problems = _sections(docs, _added_in(live), version, _retired_in(live))
    verses = {tr: verse_text(library, tr, code, info.name, version) for tr in TRANSLATIONS}
    files = {f"verses/{tr}.json": encode(v.to_doc()) for tr, v in verses.items()}
    study = StudyPack(
        format_version=FORMAT_VERSION,
        book=Book(id=code, name=info.name),
        introduction=introduction,
        pack_version=version,
        published_at=now,
        translations=[
            TranslationRef(
                id=tr,
                name=verses[tr].translation.name,
                abbreviation=verses[tr].translation.abbreviation,
                path=f"verses/{tr}.json",
                sha256=sha256_hex(files[f"verses/{tr}.json"]),
            )
            for tr in TRANSLATIONS
        ],
        sources=sources,
        build=_build_info(ready),
        sections=sections,
    )
    violations = cross_field_violations(study, verses)
    problems += [f"rule {v.rule}: {v.item_id}: {v.message}" for v in violations]
    study_doc = study.to_doc()
    problems += [f"study-pack schema: {p}" for p in validate(study_doc, "study-pack")]
    for tr, v in verses.items():
        problems += [f"verses/{tr} schema: {p}" for p in validate(v.to_doc(), "verses")]
    if problems:
        raise BuildError(problems)
    files["study.json"] = encode(study_doc)
    return BuiltPack(version=version, change=change, study=study, verses=verses, files=files)
