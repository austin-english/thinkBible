"""Shared fixtures for the pipeline tests."""

from __future__ import annotations

import io
import struct
import zipfile
import zlib
from collections.abc import Callable
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
