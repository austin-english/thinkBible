"""Read the frozen snapshot, checking every file against the manifest (FR-002).

Files come from a ``SourceStore``: the local cache ``content/sources/`` (``import``, ``--local``)
or the sources bucket (Lambdas). The manifest itself is always the committed one, read from the
repo, or from the Lambda bundle, which carries a copy (research R19).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from thinkbible_pipeline.jsonio import read_json, sha256_hex
from thinkbible_pipeline.paths import RepoPaths, repo_paths
from thinkbible_pipeline.storage import BlobStore, LocalBlobStore, S3BlobStore

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
from thinkbible_pipeline.sources.models import (
    BookFile,
    NormalizedCommentaryBook,
    NormalizedTranslationBook,
    SourceManifest,
)


class SourceError(Exception):
    """Base for snapshot problems. The CLI maps these to exit code 2."""


class ChecksumMismatch(SourceError):
    def __init__(self, path: str, expected: str, actual: str) -> None:
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


@dataclass(frozen=True)
class SourceStore:
    """Where source files are read from. The local cache keys files by ``file``; the sources
    bucket keys them by ``s3Key`` (data-model §3)."""

    blobs: BlobStore
    by_s3_key: bool
    label: str

    @classmethod
    def local(cls, paths: RepoPaths | None = None) -> SourceStore:
        root = (paths or repo_paths()).sources
        return cls(LocalBlobStore(root), by_s3_key=False, label=str(root))

    @classmethod
    def s3(cls, bucket: str, client: S3Client | None = None) -> SourceStore:
        return cls(S3BlobStore(bucket, client=client), by_s3_key=True, label=f"s3://{bucket}")

    def key(self, bf: BookFile) -> str:
        return bf.s3_key if self.by_s3_key else bf.file


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


def verified_bytes(bf: BookFile, store: SourceStore) -> bytes:
    """Read one source file and check its sha256 against the manifest entry."""
    key = store.key(bf)
    blob = store.blobs.get(key)
    if blob is None:
        raise MissingSource(f"{key} in {store.label}")
    actual = sha256_hex(blob.data)
    if actual != bf.sha256:
        raise ChecksumMismatch(f"{store.label}/{key}", bf.sha256, actual)
    return blob.data


def load_book(
    source: str,
    book: str,
    *,
    store: SourceStore,
    manifest: SourceManifest,
) -> NormalizedTranslationBook | NormalizedCommentaryBook:
    """Return the parsed book after its checksum passes. ``book`` is a USFM code (``MRK``)."""
    kind = manifest.sources[source].kind if source in manifest.sources else None
    data = verified_bytes(_book_file(manifest, source, book), store)
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
    store: SourceStore,
    manifest: SourceManifest,
    books: set[str] | None = None,
) -> list[VerifyProblem]:
    """Check every file in the manifest (or only ``books``), including archived module zips.
    Returns problems, not raises."""
    problems: list[VerifyProblem] = []
    for source, entry in sorted(manifest.sources.items()):
        for book, bf in entry.files():
            if books is not None and book not in books:
                continue
            try:
                verified_bytes(bf, store)
            except SourceError as e:
                problems.append(VerifyProblem(source, book, str(e)))
    return problems
