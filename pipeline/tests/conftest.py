"""Shared fixtures for the pipeline tests."""

from __future__ import annotations

import io
import struct
import zipfile
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from thinkbible_pipeline.jsonio import canonical_json, sha256_hex, write_json
from thinkbible_pipeline.paths import RepoPaths
from thinkbible_pipeline.sources.models import BookFile, SourceEntry, SourceManifest
from thinkbible_pipeline.sources.snapshot import SourceLibrary, SourceStore
from thinkbible_pipeline.sources.sword import _POSITIONS, TESTAMENTS, _expected_entries

Key = tuple[str, int, int]  # (book, chapter, verse); chapter 0 = book intro, verse 0 = chapter
SwordZip = Callable[..., bytes]


def build_sword_module(
    entries: dict[Key, str],
    *,
    name: str = "TEST",
    version: str = "1.0",
    driver: str = "zCom4",
    links: dict[Key, Key] | None = None,
    extra_conf: str = "",
    drop_entries: int = 0,
    orphans: dict[Key, str] | None = None,
) -> bytes:
    """A small SWORD commentary module zip, laid out like CrossWire's (one block per testament).

    ``entries`` maps index keys to raw OSIS text; ``links`` makes a key point at another key's
    note (how a module stores one note for a range of verses). ``drop_entries`` truncates the
    index to test the versification check. ``orphans`` puts text right after a key's note in the
    block without indexing it (how CrossWire's JFB loses notes, research R2a).
    """
    fmt, size = {"zCom": ("<IIH", 10), "zCom4": ("<III", 12)}[driver]
    links = links or {}
    data_path = f"modules/comments/zcom/{name.lower()}"
    files: dict[str, bytes] = {}
    for testament in TESTAMENTS:
        block = bytearray()
        where: dict[Key, tuple[int, int]] = {}
        for key, text in entries.items():
            if _POSITIONS[key][0] == testament:
                raw = text.encode("utf-8")
                where[key] = (len(block), len(raw))
                block += raw
                block += (orphans or {}).get(key, "").encode("utf-8")
        for key, target in links.items():
            if _POSITIONS[key][0] == testament:
                where[key] = where[target]
        index = bytearray(size * _expected_entries(testament))
        for key, (offset, length) in where.items():
            struct.pack_into(fmt, index, _POSITIONS[key][1] * size, 0, offset, length)
        if drop_entries:
            index = index[: -size * drop_entries]
        compressed = zlib.compress(bytes(block))
        files[f"{testament}.bzs"] = struct.pack("<III", 0, len(compressed), len(block))
        files[f"{testament}.bzv"] = bytes(index)
        files[f"{testament}.bzz"] = compressed
    conf = (
        f"[{name}]\nDataPath=./{data_path}/\nModDrv={driver}\nSourceType=OSIS\n"
        f"CompressType=ZIP\nBlockType=BOOK\nVersification=KJV\nVersion={version}\n"
        f"Description=Test commentary\nDistributionLicense=Public Domain\n{extra_conf}"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr(f"mods.d/{name.lower()}.conf", conf)
        for fname, data in files.items():
            zf.writestr(f"{data_path}/{fname}", data)
    return out.getvalue()


@pytest.fixture
def sword_zip() -> SwordZip:
    return build_sword_module


MakeLibrary = Callable[[dict[tuple[str, str], dict[str, Any]]], SourceLibrary]


@pytest.fixture
def make_library(tmp_path: Path) -> MakeLibrary:
    """A tiny verified snapshot: {(source, BOOK): normalised book doc} → a ``SourceLibrary``.

    Sources named ``bsb`` or ``kjv`` are translations; the rest are commentaries.
    """

    def make(books: dict[tuple[str, str], dict[str, Any]]) -> SourceLibrary:
        paths = RepoPaths(tmp_path)
        entries: dict[str, SourceEntry] = {}
        for (source, code), doc in books.items():
            data = canonical_json(doc).encode()
            rel = f"{source}/{code}.json"
            (paths.sources / source).mkdir(parents=True, exist_ok=True)
            (paths.sources / rel).write_bytes(data)
            kind = "translation" if source in ("bsb", "kjv") else "commentary"
            entry = entries.setdefault(
                source, SourceEntry(kind=kind, api_id=source, name=source, license="PD")
            )
            entry.books[code] = BookFile(
                file=rel,
                s3_key=f"snapshots/t/{rel}",
                sha256=sha256_hex(data),
                bytes=len(data),
                retrieved_at="t",
                snapshot_id="t",
            )
        manifest = SourceManifest(bucket="b", api_version="V1", sources=entries)
        write_json(paths.manifest, manifest.to_doc())
        return SourceLibrary(SourceStore.local(paths), manifest)

    return make


# --- a complete, publishable book for the publish tests (US3) ---

PUBLISH_SECTIONS = (
    ("2jn-1-1", 1, 6, "Walking in Truth"),
    ("2jn-1-7", 7, 13, "Beware of Deceivers"),
)


def section_doc(sid: str, start: int, end: int, title: str, ideas: int = 1) -> dict[str, Any]:
    """A section as a draft holds it after review: published fields, no versions yet."""
    key_ideas = [
        {"id": f"{sid}-k{n}", "kind": "key", "title": f"Point {n} of {title}",
         "body": f"Why point {n} matters.", "sources": ["matthew-henry"],
         "quotes": [{"commentator": "matthew-henry", "text": f"Henry's words on point {n}."}],
         "agreed": False, "verseStart": start, "verseEnd": end, "status": "active"}
        for n in range(1, ideas + 1)
    ]  # fmt: skip
    questions = [
        {"id": f"{sid}-q{n}", "type": "meaning", "verseStart": start, "verseEnd": end,
         "text": f"What might the elder want readers to notice in part {n}?",
         "targets": [f"{sid}-k{n}"], "status": "active"}
        for n in range(1, ideas + 1)
    ]  # fmt: skip
    return {
        "id": sid, "ref": f"2 John 1:{start}-{end}", "chapter": 1, "verseStart": start,
        "verseEnd": end, "title": title, "noPrompt": False,
        "context": "The elder writes to a chosen lady and her children.", "viewsDiffer": None,
        "manuscriptNotes": [], "keyIdeas": key_ideas, "questions": questions,
    }  # fmt: skip


@dataclass
class PublishBook:
    store: Any  # DraftStore
    library: SourceLibrary

    def draft(self, sid: str) -> Any:
        return self.store.read_draft_or_new(sid)

    def write(self, sid: str, draft: Any) -> None:
        self.store.write_draft(sid, draft)


@pytest.fixture
def publish_book(make_library: MakeLibrary, tmp_path: Path) -> PublishBook:
    """2 John in two graded sections, with a snapshot whose manifest carries full provenance."""
    from thinkbible_pipeline.drafts.models import (
        Evidence,
        SectionDraft,
        SectionMapEntry,
        StageRecord,
    )
    from thinkbible_pipeline.drafts.store import DraftStore
    from thinkbible_pipeline.storage import LocalBlobStore

    def translation(tr: str) -> dict[str, Any]:
        items: list[dict[str, Any]] = [{"type": "heading", "text": "Greeting"}]
        for v in range(1, 14):
            if tr == "bsb" and v == 7:
                items.append({"type": "break", "paragraph": True})
            item: dict[str, Any] = {"type": "verse", "number": v, "text": f"{tr} verse {v}."}
            if v == 3:
                item["lines"] = [{"text": "Grace, mercy,", "indent": 1},
                                 {"text": "and peace", "indent": 6}]  # fmt: skip
            items.append(item)
        return {"book": "2JN", "chapters": [{"number": 1, "items": items}]}

    lib = make_library({
        ("bsb", "2JN"): translation("bsb"),
        ("kjv", "2JN"): translation("kjv"),
        ("matthew-henry", "2JN"): {"book": "2JN", "chapters": [{"number": 1, "items": [
            {"verse": 1, "verseEnd": 13, "text": "Henry's note on the letter."}]}]},
    })  # fmt: skip
    for source_id, entry in lib.manifest.sources.items():
        entry.upstream_sha256 = "a" * 64
        entry.origin = f"test:{source_id}"
        entry.license_url = "https://example.org/license"
        entry.name = {"bsb": "Berean Standard Bible", "kjv": "King James Version"}.get(
            source_id, "Matthew Henry's Commentary"
        )
        for book in entry.books.values():
            book.retrieved_at = "2026-11-13T16:21:13+00:00"
    store = DraftStore("2jn", LocalBlobStore(tmp_path / "drafts"))
    store.write_section_map([
        SectionMapEntry(id=sid, chapter=1, verse_start=a, verse_end=b, title=t,
                        title_source="bsb-heading")
        for sid, a, b, t in PUBLISH_SECTIONS
    ])  # fmt: skip
    for sid, a, b, t in PUBLISH_SECTIONS:
        draft = SectionDraft(section=section_doc(sid, a, b, t))
        # As a real draft has: the ID counters, and each idea's evidence quote.
        draft.ids.k = draft.ids.q = 1
        draft.evidence = {f"{sid}-k1": [Evidence(commentator="matthew-henry", quote="On point 1.")]}
        for stage, version, model in (
            ("generate", "_shared/context@v1+extract@v15+question-guide@v4+questions@v15",
             "claude-sonnet-5-5"),
            ("review", "_shared/context@v1+review@v11", "claude-opus-5-5"),
        ):  # fmt: skip
            draft.stages[stage] = StageRecord(
                prompt_version=version, model=model, input_hash="h",
                completed_at="2026-11-18T00:00:00+00:00", cost_usd=0.1, status="done",
            )  # fmt: skip
        store.write_draft(sid, draft)
    return PublishBook(store=store, library=lib)
