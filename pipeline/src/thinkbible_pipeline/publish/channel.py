"""The draft and live channels of the packs bucket, behind CloudFront (T072, cdn-layout.md, R14).

Each channel is a prefix, ``draft/`` or ``live/``, with the same layout under it:

    v1/index.json                                  the latest version of every book
    v1/books/{book}/{version}/study.json
    v1/books/{book}/{version}/verses/{tr}.json

Paths in ``index.json`` are relative to the channel (``v1/books/mrk/1.0.0/study.json``), so the
same files serve either channel. Files are written before the index that points to them, and the
index is the only path invalidated in CloudFront. Live files are never overwritten (written with
If-None-Match) and are cached for a year; draft files may be replaced and are cached for 5 minutes.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

from thinkbible_core.ids import resolve_book
from thinkbible_core.models.index import IndexBook, PackIndex
from thinkbible_core.models.pack import StudyPack
from thinkbible_pipeline.jsonio import compact_canonical, sha256_hex
from thinkbible_pipeline.storage import BlobStore

ChannelName = Literal["draft", "live"]
INDEX_CACHE = "public, max-age=300"
FILE_CACHE: dict[ChannelName, str] = {
    "draft": "public, max-age=300",
    "live": "public, max-age=31536000, immutable",
}
INDEX_PATH = "v1/index.json"


class ChannelError(Exception):
    """A channel's files don't match its index (a missing file or a wrong sha256)."""


def book_folder(code: str, version: str) -> str:
    return f"v1/books/{resolve_book(code).slug}/{version}"


def with_book(index: PackIndex | None, entry: IndexBook, now: datetime) -> PackIndex:
    """``index`` with ``entry`` replacing that book's entry, books in canonical order."""
    books = [b for b in (index.books if index else []) if b.book.id != entry.book.id]
    books.append(entry)
    books.sort(key=lambda b: resolve_book(b.book.id).order)
    return PackIndex(format_version=1, generated_at=now, books=books)


class PackChannel:
    def __init__(
        self,
        name: ChannelName,
        blobs: BlobStore,
        invalidate: Callable[[str], None] | None = None,
    ) -> None:
        self.name = name
        self.blobs = blobs
        self.invalidate = invalidate

    def key(self, path: str) -> str:
        return f"{self.name}/{path}"

    def read(self, path: str) -> bytes | None:
        blob = self.blobs.get(self.key(path))
        return blob.data if blob is not None else None

    def put(self, path: str, data: bytes) -> None:
        self.blobs.put(
            self.key(path),
            data,
            cache_control=FILE_CACHE[self.name],
            if_none_match=self.name == "live",
        )

    def read_index(self) -> PackIndex | None:
        data = self.read(INDEX_PATH)
        return PackIndex.model_validate_json(data) if data is not None else None

    def write_index(self, index: PackIndex) -> None:
        data = (compact_canonical(index.to_doc()) + "\n").encode()
        self.blobs.put(self.key(INDEX_PATH), data, cache_control=INDEX_CACHE)
        if self.invalidate is not None:
            self.invalidate(f"/{self.key(INDEX_PATH)}")

    def entry(self, code: str) -> IndexBook | None:
        index = self.read_index()
        return next((b for b in index.books if b.book.id == code), None) if index else None

    def verified(self, path: str, sha256: str) -> bytes:
        data = self.read(path)
        if data is None:
            raise ChannelError(f"{self.name}/{path} is listed in the index but missing")
        if sha256_hex(data) != sha256:
            raise ChannelError(f"{self.name}/{path} doesn't match its sha256 in the index")
        return data

    def study(self, code: str) -> StudyPack | None:
        """The book's current pack on this channel, checked against the index."""
        entry = self.entry(code)
        if entry is None:
            return None
        data = self.verified(entry.study.path, entry.study.sha256)
        return StudyPack.model_validate_json(data)


def cloudfront_invalidator(distribution_id: str) -> Callable[[str], None] | None:
    """Invalidate one path in the CDN; None until the distribution exists (aws.toml)."""
    if not distribution_id:
        return None
    import boto3

    client = boto3.client("cloudfront")

    def invalidate(path: str) -> None:
        client.create_invalidation(
            DistributionId=distribution_id,
            InvalidationBatch={
                "Paths": {"Quantity": 1, "Items": [path]},
                "CallerReference": f"{path}-{time.time_ns()}",
            },
        )

    return invalidate


def pack_channels(
    bucket: str, distribution_id: str, *, client: Any = None
) -> tuple[PackChannel, PackChannel] | None:
    """The (draft, live) channels, or None until the packs bucket and CDN exist."""
    if not (bucket and distribution_id):
        return None
    from thinkbible_pipeline.storage import S3BlobStore

    blobs = S3BlobStore(bucket, client=client)
    invalidate = cloudfront_invalidator(distribution_id)
    return PackChannel("draft", blobs, invalidate), PackChannel("live", blobs, invalidate)
