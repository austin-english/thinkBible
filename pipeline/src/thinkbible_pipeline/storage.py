"""Blob storage behind one interface: a local folder (tests, ``--local`` before deploy) or S3.

Drafts and source files are read and written through a ``BlobStore``, so the same code runs in a
Lambda against S3 and on a laptop against a folder (research R8).
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class PreconditionFailed(Exception):
    """A conditional write lost: the object changed (``if_match``) or already exists."""


@dataclass(frozen=True)
class Blob:
    data: bytes
    etag: str


class BlobStore(Protocol):
    def get(self, key: str) -> Blob | None: ...

    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/json",
        if_match: str | None = None,
        if_none_match: bool = False,
    ) -> str:
        """Write ``data`` and return the new ETag. Raises ``PreconditionFailed``."""
        ...

    def list(self, prefix: str = "") -> list[tuple[str, str]]:
        """``(key, etag)`` for every object under ``prefix``, sorted by key."""
        ...


def _etag(data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


class LocalBlobStore:
    """A folder on disk. ETags are content hashes, so conditional writes behave like S3's."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError(f"key escapes the store root: {key!r}")
        return path

    def get(self, key: str) -> Blob | None:
        path = self._path(key)
        if not path.is_file():
            return None
        data = path.read_bytes()
        return Blob(data, _etag(data))

    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/json",
        if_match: str | None = None,
        if_none_match: bool = False,
    ) -> str:
        path = self._path(key)
        current = self.get(key)
        if if_none_match and current is not None:
            raise PreconditionFailed(f"{key} already exists")
        if if_match is not None and (current is None or current.etag != if_match):
            raise PreconditionFailed(f"{key} changed since it was read")
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return _etag(data)

    def _walk(self, base: Path) -> Iterator[Path]:
        if base.is_file():
            yield base
        elif base.is_dir():
            for p in base.rglob("*"):
                if p.is_file() and not p.name.endswith(".tmp"):
                    yield p

    def list(self, prefix: str = "") -> list[tuple[str, str]]:
        if not self.root.is_dir():
            return []
        out: list[tuple[str, str]] = []
        for p in self._walk(self.root):
            key = p.relative_to(self.root).as_posix()
            if key.startswith(prefix):
                out.append((key, _etag(p.read_bytes())))
        return sorted(out)


class S3BlobStore:
    """An S3 bucket, optionally under a key prefix. Conditional writes use If-(None-)Match."""

    def __init__(self, bucket: str, prefix: str = "", client: S3Client | None = None) -> None:
        if client is None:
            import boto3

            client = boto3.client("s3")
        self.bucket = bucket
        self.prefix = prefix
        self._s3 = client

    def get(self, key: str) -> Blob | None:
        try:
            obj = self._s3.get_object(Bucket=self.bucket, Key=self.prefix + key)
        except self._s3.exceptions.NoSuchKey:
            return None
        return Blob(obj["Body"].read(), obj["ETag"].strip('"'))

    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/json",
        if_match: str | None = None,
        if_none_match: bool = False,
    ) -> str:
        from botocore.exceptions import ClientError

        kwargs: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": self.prefix + key,
            "Body": data,
            "ContentType": content_type,
        }
        if if_match is not None:
            kwargs["IfMatch"] = f'"{if_match}"'
        if if_none_match:
            kwargs["IfNoneMatch"] = "*"
        try:
            resp = self._s3.put_object(**kwargs)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in {"PreconditionFailed", "ConditionalRequestConflict", "412"}:
                raise PreconditionFailed(f"{key}: {code}") from e
            raise
        return resp["ETag"].strip('"')

    def list(self, prefix: str = "") -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix + prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"][len(self.prefix) :]
                out.append((key, obj["ETag"].strip('"')))
        return sorted(out)
