"""``sources push`` and ``sources pull``: the local cache ↔ the write-once sources bucket (R2).

Files are the normalised books and, for the commentaries, the CrossWire module zip they were made
from (archived so the snapshot never depends on CrossWire again). Push uploads each file with
``If-None-Match: *`` and its sha256 as object metadata, so an object is never overwritten. Pull
downloads what the cache is missing and checks every file against the manifest before writing it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from botocore.exceptions import ClientError

from thinkbible_pipeline.paths import RepoPaths, repo_paths
from thinkbible_pipeline.sources.models import BookFile, SourceManifest
from thinkbible_pipeline.sources.snapshot import (
    ChecksumMismatch,
    MissingSource,
    SourceStore,
    verified_bytes,
)
from thinkbible_pipeline.storage import LocalBlobStore

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class PushRefused(Exception):
    """An object already exists at a snapshot key with a different checksum."""


@dataclass
class PushResult:
    uploaded: int = 0
    skipped: int = 0  # already in S3 with the same checksum


@dataclass
class PullResult:
    downloaded: int = 0
    present: int = 0  # already in the cache and verified
    problems: list[str] = field(default_factory=list)


def _files(
    manifest: SourceManifest, books: set[str] | None = None
) -> list[tuple[str, str, BookFile]]:
    """(source, book or "module", file) for every manifest file; ``books`` limits to those."""
    return [
        (source, book, bf)
        for source, entry in sorted(manifest.sources.items())
        for book, bf in entry.files()
        if books is None or book in books
    ]


def _content_type(bf: BookFile) -> str:
    return "application/zip" if bf.file.endswith(".zip") else "application/json"


def _client(client: S3Client | None) -> S3Client:
    if client is not None:
        return client
    import boto3

    return boto3.client("s3")


def push(
    manifest: SourceManifest,
    *,
    paths: RepoPaths | None = None,
    client: S3Client | None = None,
    bucket: str | None = None,
) -> PushResult:
    """Upload every cached manifest file that isn't in S3 yet. Refuses on a checksum clash."""
    s3 = _client(client)
    bucket = bucket or manifest.bucket
    local = SourceStore.local(paths)
    result = PushResult()
    for _source, _book, bf in _files(manifest):
        data = verified_bytes(bf, local)  # never upload a file that doesn't match the manifest
        try:
            s3.put_object(
                Bucket=bucket,
                Key=bf.s3_key,
                Body=data,
                ContentType=_content_type(bf),
                Metadata={"sha256": bf.sha256},
                IfNoneMatch="*",
            )
            result.uploaded += 1
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") not in {"PreconditionFailed", "412"}:
                raise
            head = s3.head_object(Bucket=bucket, Key=bf.s3_key)
            existing = head.get("Metadata", {}).get("sha256")
            if existing != bf.sha256:
                raise PushRefused(
                    f"s3://{bucket}/{bf.s3_key} already exists with sha256 {existing}, not "
                    f"{bf.sha256}. Snapshot objects are write-once: re-import under a new "
                    "snapshot ID instead."
                ) from e
            result.skipped += 1
    return result


def pull(
    manifest: SourceManifest,
    *,
    paths: RepoPaths | None = None,
    client: S3Client | None = None,
    bucket: str | None = None,
    books: set[str] | None = None,
) -> PullResult:
    """Download manifest files missing from (or wrong in) the cache, verifying each one."""
    paths = paths or repo_paths()
    s3_store = SourceStore.s3(bucket or manifest.bucket, client=_client(client))
    local = SourceStore.local(paths)
    cache = LocalBlobStore(paths.sources)
    result = PullResult()
    for source, book, bf in _files(manifest, books):
        try:
            verified_bytes(bf, local)
            result.present += 1
            continue
        except (MissingSource, ChecksumMismatch):
            pass
        try:
            data = verified_bytes(bf, s3_store)
        except (MissingSource, ChecksumMismatch) as e:
            result.problems.append(f"{source}/{book}: {e}")
            continue
        cache.put(bf.file, data)
        result.downloaded += 1
    return result
