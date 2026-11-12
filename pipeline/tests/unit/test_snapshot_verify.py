"""Every source read is checked against the manifest (T031, FR-002)."""

from pathlib import Path

import pytest

from thinkbible_pipeline.jsonio import canonical_json, sha256_hex
from thinkbible_pipeline.paths import RepoPaths
from thinkbible_pipeline.sources.models import (
    BookFile,
    NormalizedTranslationBook,
    SourceEntry,
    SourceManifest,
)
from thinkbible_pipeline.sources.snapshot import (
    ChecksumMismatch,
    MissingSource,
    SourceStore,
    load_book,
    verify,
)

BOOK = {
    "book": "MRK",
    "chapters": [{"number": 1, "items": [{"type": "verse", "number": 1, "text": "The beginning"}]}],
}


def setup(tmp_path: Path) -> tuple[SourceStore, SourceManifest, Path]:
    data = canonical_json(BOOK).encode()
    path = tmp_path / "content" / "sources" / "bsb" / "MRK.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    bf = BookFile(
        file="bsb/MRK.json",
        s3_key="snapshots/2026-11-12/bsb/MRK.json",
        sha256=sha256_hex(data),
        bytes=len(data),
        retrieved_at="2026-11-12",
        snapshot_id="2026-11-12",
    )
    manifest = SourceManifest(
        bucket="b",
        api_version="V1.16.0",
        sources={
            "bsb": SourceEntry(
                kind="translation", api_id="BSB", name="BSB", license="PD", books={"MRK": bf}
            )
        },
    )
    return SourceStore.local(RepoPaths(tmp_path)), manifest, path


def test_load_book_returns_the_parsed_book(tmp_path: Path) -> None:
    store, manifest, _ = setup(tmp_path)
    book = load_book("bsb", "MRK", store=store, manifest=manifest)
    assert isinstance(book, NormalizedTranslationBook)
    assert book.chapters[0].verses()[0].text == "The beginning"
    assert verify(store=store, manifest=manifest) == []


def test_one_byte_change_raises(tmp_path: Path) -> None:
    store, manifest, path = setup(tmp_path)
    data = bytearray(path.read_bytes())
    data[-3] ^= 0x01
    path.write_bytes(bytes(data))
    with pytest.raises(ChecksumMismatch, match="does not match manifest"):
        load_book("bsb", "MRK", store=store, manifest=manifest)
    problems = verify(store=store, manifest=manifest)
    assert [(p.source, p.book) for p in problems] == [("bsb", "MRK")]


def test_missing_file_says_to_pull(tmp_path: Path) -> None:
    store, manifest, path = setup(tmp_path)
    path.unlink()
    with pytest.raises(MissingSource, match="sources pull"):
        load_book("bsb", "MRK", store=store, manifest=manifest)


def test_verify_can_limit_to_books(tmp_path: Path) -> None:
    store, manifest, path = setup(tmp_path)
    path.unlink()
    assert verify(store=store, manifest=manifest, books={"GEN"}) == []
    assert len(verify(store=store, manifest=manifest, books={"MRK"})) == 1
