"""Read the frozen snapshot from the local cache, checking every file against the manifest."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from thinkbible_pipeline.jsonio import read_json, sha256_hex
from thinkbible_pipeline.paths import RepoPaths, repo_paths
from thinkbible_pipeline.sources.models import (
    BookFile,
    NormalizedCommentaryBook,
    NormalizedTranslationBook,
    SourceManifest,
)


class SourceError(Exception):
    """Base for snapshot problems. The CLI maps these to exit code 2."""


class ChecksumMismatch(SourceError):
    def __init__(self, path: Path, expected: str, actual: str) -> None:
        super().__init__(
            f"{path}: sha256 {actual} does not match manifest {expected}. "
            "Nothing was generated. Restore the file with `thinkbible-pipeline sources pull`."
        )
        self.path = path


class MissingSource(SourceError):
    def __init__(self, what: str) -> None:
        super().__init__(
            f"{what} is not in the local cache: run `thinkbible-pipeline sources pull`"
        )


class UnknownSource(SourceError):
    pass


def load_manifest(paths: RepoPaths | None = None) -> SourceManifest:
    p = (paths or repo_paths()).manifest
    if not p.is_file():
        raise MissingSource(str(p))
    return SourceManifest.model_validate(read_json(p))


def _book_file(manifest: SourceManifest, source: str, book: str) -> BookFile:
    entry = manifest.sources.get(source)
    if entry is None:
        raise UnknownSource(f"source {source!r} is not in manifest.json")
    bf = entry.books.get(book)
    if bf is None:
        raise UnknownSource(f"book {book} of {source!r} is not in manifest.json")
    return bf


def verified_bytes(bf: BookFile, paths: RepoPaths | None = None) -> bytes:
    """Read one cache file and check its sha256 against the manifest entry."""
    path = (paths or repo_paths()).sources / bf.file
    if not path.is_file():
        raise MissingSource(bf.file)
    data = path.read_bytes()
    actual = sha256_hex(data)
    if actual != bf.sha256:
        raise ChecksumMismatch(path, bf.sha256, actual)
    return data


def load_book(
    source: str,
    book: str,
    *,
    paths: RepoPaths | None = None,
    manifest: SourceManifest | None = None,
) -> NormalizedTranslationBook | NormalizedCommentaryBook:
    """Return the parsed book after its checksum passes. ``book`` is a USFM code (``MRK``)."""
    paths = paths or repo_paths()
    manifest = manifest or load_manifest(paths)
    kind = manifest.sources[source].kind if source in manifest.sources else None
    data = verified_bytes(_book_file(manifest, source, book), paths)
    if kind == "translation":
        return NormalizedTranslationBook.model_validate_json(data)
    return NormalizedCommentaryBook.model_validate_json(data)


@dataclass(frozen=True)
class VerifyProblem:
    source: str
    book: str
    message: str


def verify(
    *,
    paths: RepoPaths | None = None,
    manifest: SourceManifest | None = None,
    books: set[str] | None = None,
) -> list[VerifyProblem]:
    """Check every cached file in the manifest (or only ``books``). Returns problems, not raises."""
    paths = paths or repo_paths()
    manifest = manifest or load_manifest(paths)
    problems: list[VerifyProblem] = []
    for source, entry in sorted(manifest.sources.items()):
        for book, bf in sorted(entry.books.items()):
            if books is not None and book not in books:
                continue
            try:
                verified_bytes(bf, paths)
            except SourceError as e:
                problems.append(VerifyProblem(source, book, str(e)))
    return problems
