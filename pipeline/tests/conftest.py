"""Shared fixtures for the pipeline tests."""

from __future__ import annotations

import io
import struct
import zipfile
import zlib
from collections.abc import Callable

import pytest

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
) -> bytes:
    """A small SWORD commentary module zip, laid out like CrossWire's (one block per testament).

    ``entries`` maps index keys to raw OSIS text; ``links`` makes a key point at another key's
    note (how a module stores one note for a range of verses). ``drop_entries`` truncates the
    index to test the versification check.
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
