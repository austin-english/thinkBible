"""``sources push`` and ``sources pull``: the local cache ↔ the write-once sources bucket (R2).

Files are the normalised books and, for the commentaries, the CrossWire module zip they were made
from (archived so the snapshot never depends on CrossWire again). Push uploads each file with
``If-None-Match: *`` and its sha256 as object metadata, so an object is never overwritten. Pull
downloads what the cache is missing and checks every file against the manifest before writing it.
"""

from __future__ import annotations

from collections.abc import Callable
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


Progress = Callable[[str], None]


def size_label(n: int) -> str:
    return f"{n / 1e6:.1f} MB" if n >= 1_000_000 else f"{max(1, round(n / 1e3))} KB"


def log_line(i: int, total: int, action: str, bf: BookFile) -> str:
    """One file's line in a transfer log: ``[ 12/333] uploaded      bsb/MRK.json  (0.2 MB)``."""
    width = len(str(total))
    return f"  [{i:>{width}}/{total}] {action:<15} {bf.file}  ({size_label(bf.bytes)})"


def _client(client: S3Client | None) -> S3Client:
    if client is not None:
        return client
    import boto3

    return boto3.client("s3")


def _remote_sha256(s3: S3Client, bucket: str, key: str) -> str | None:
    """The sha256 recorded on an existing object ("" if it has none), or None if it's missing."""
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise
    return str(head.get("Metadata", {}).get("sha256", ""))


def _check_existing(bucket: str, bf: BookFile, existing: str | None) -> None:
    """An object is already at ``bf``'s key: it must be this exact file (write-once)."""
    if existing != bf.sha256:
        raise PushRefused(
            f"s3://{bucket}/{bf.s3_key} already exists with sha256 {existing}, not "
            f"{bf.sha256}. Snapshot objects are write-once: re-import under a new "
            "snapshot ID instead."
        )


def push(
    manifest: SourceManifest,
    *,
    paths: RepoPaths | None = None,
    client: S3Client | None = None,
    bucket: str | None = None,
    progress: Progress | None = None,
) -> PushResult:
    """Upload every cached manifest file that isn't in S3 yet. Refuses on a checksum clash.
    ``progress`` gets one line per file."""
    s3 = _client(client)
    bucket = bucket or manifest.bucket
    local = SourceStore.local(paths)
    result = PushResult()
    files = _files(manifest)
    for i, (_source, _book, bf) in enumerate(files, 1):
        # Ask first: a conditional PUT only fails after the whole file has been sent, so checking
        # with HEAD keeps a re-run from re-uploading the snapshot just to be told it's there.
        existing = _remote_sha256(s3, bucket, bf.s3_key)
        if existing is not None:
            _check_existing(bucket, bf, existing)
            result.skipped += 1
            if progress is not None:
                progress(log_line(i, len(files), "already there", bf))
            continue
        data = verified_bytes(bf, local)  # never upload a file that doesn't match the manifest
        try:
            s3.put_object(
                Bucket=bucket,
                Key=bf.s3_key,
                Body=data,
                ContentType=_content_type(bf),
                Metadata={"sha256": bf.sha256},
                IfNoneMatch="*",  # still write-once if something uploaded it meanwhile
            )
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") not in {"PreconditionFailed", "412"}:
                raise
            _check_existing(bucket, bf, _remote_sha256(s3, bucket, bf.s3_key))
            result.skipped += 1
            if progress is not None:
                progress(log_line(i, len(files), "already there", bf))
            continue
        result.uploaded += 1
        if progress is not None:
            progress(log_line(i, len(files), "uploaded", bf))
    return result


def pull(
    manifest: SourceManifest,
    *,
    paths: RepoPaths | None = None,
    client: S3Client | None = None,
    bucket: str | None = None,
    books: set[str] | None = None,
    progress: Progress | None = None,
) -> PullResult:
    """Download manifest files missing from (or wrong in) the cache, verifying each one.
    ``progress`` gets one line per file."""
    paths = paths or repo_paths()
    s3_store = SourceStore.s3(bucket or manifest.bucket, client=_client(client))
    local = SourceStore.local(paths)
    cache = LocalBlobStore(paths.sources)
    result = PullResult()
    files = _files(manifest, books)

    def log(i: int, action: str, bf: BookFile) -> None:
        if progress is not None:
            progress(log_line(i, len(files), action, bf))

    for i, (source, book, bf) in enumerate(files, 1):
        try:
            verified_bytes(bf, local)
            result.present += 1
            log(i, "already present", bf)
            continue
        except (MissingSource, ChecksumMismatch):
            pass
        try:
            data = verified_bytes(bf, s3_store)
        except (MissingSource, ChecksumMismatch) as e:
            result.problems.append(f"{source}/{book}: {e}")
            log(i, "FAILED", bf)
            continue
        cache.put(bf.file, data)
        result.downloaded += 1
        log(i, "downloaded", bf)
    return result
