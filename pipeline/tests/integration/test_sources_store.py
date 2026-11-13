"""sources push / pull against S3 (T032): write-once uploads, byte-identical restores."""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import boto3
import pytest
from moto import mock_aws

from thinkbible_pipeline.jsonio import sha256_hex
from thinkbible_pipeline.paths import RepoPaths
from thinkbible_pipeline.sources.models import BookFile, ModuleFile, SourceEntry, SourceManifest
from thinkbible_pipeline.sources.store import PushRefused, pull, push

BUCKET = "sources-test"


def book_file(source: str, book: str, data: bytes) -> BookFile:
    return BookFile(
        file=f"{source}/{book}.json",
        s3_key=f"snapshots/2026-11-12/{source}/{book}.json",
        sha256=sha256_hex(data),
        bytes=len(data),
        retrieved_at="2026-11-12",
        snapshot_id="2026-11-12",
    )


@pytest.fixture
def s3() -> Iterator[Any]:
    with mock_aws():
        client = boto3.client("s3", region_name="us-west-2")
        client.create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "us-west-2"}
        )
        yield client


def cache(tmp_path: Path, files: dict[str, bytes]) -> tuple[RepoPaths, SourceManifest]:
    paths = RepoPaths(tmp_path)
    entries: dict[str, SourceEntry] = {}
    for rel, data in files.items():
        source, name = rel.split("/")
        book = name.removesuffix(".json")
        (paths.sources / source).mkdir(parents=True, exist_ok=True)
        (paths.sources / rel).write_bytes(data)
        entry = entries.setdefault(
            source, SourceEntry(kind="translation", api_id=source, name=source, license="PD")
        )
        entry.books[book] = book_file(source, book, data)
    return paths, SourceManifest(bucket=BUCKET, api_version="V1.16.0", sources=entries)


def test_push_uploads_once_with_checksum_metadata(tmp_path: Path, s3: Any) -> None:
    paths, manifest = cache(tmp_path, {"bsb/MRK.json": b'{"a":1}', "kjv/MRK.json": b'{"b":2}'})
    first = push(manifest, paths=paths, client=s3)
    assert (first.uploaded, first.skipped) == (2, 0)
    head = s3.head_object(Bucket=BUCKET, Key="snapshots/2026-11-12/bsb/MRK.json")
    assert head["Metadata"]["sha256"] == sha256_hex(b'{"a":1}')
    again = push(manifest, paths=paths, client=s3)
    assert (again.uploaded, again.skipped) == (0, 2)  # re-pushing is a no-op


def test_push_refuses_a_different_file_at_the_same_key(tmp_path: Path, s3: Any) -> None:
    paths, manifest = cache(tmp_path, {"bsb/MRK.json": b'{"a":1}'})
    push(manifest, paths=paths, client=s3)
    paths2, manifest2 = cache(tmp_path / "other", {"bsb/MRK.json": b'{"a":2}'})
    with pytest.raises(PushRefused, match=re.escape("snapshots/2026-11-12/bsb/MRK.json")):
        push(manifest2, paths=paths2, client=s3)
    obj = s3.get_object(Bucket=BUCKET, Key="snapshots/2026-11-12/bsb/MRK.json")
    assert obj["Body"].read() == b'{"a":1}'  # write-once: the original is untouched


def test_pull_restores_byte_identical_files(tmp_path: Path, s3: Any) -> None:
    files = {"bsb/MRK.json": b'{"a":1}', "bsb/GEN.json": b'{"g":1}', "kjv/MRK.json": b'{"b":2}'}
    paths, manifest = cache(tmp_path, files)
    push(manifest, paths=paths, client=s3)
    for rel in files:
        (paths.sources / rel).unlink()
    result = pull(manifest, paths=paths, client=s3, books={"MRK"})
    assert result.downloaded == 2 and result.problems == []
    assert (paths.sources / "bsb/MRK.json").read_bytes() == b'{"a":1}'
    assert not (paths.sources / "bsb/GEN.json").exists()  # not requested
    again = pull(manifest, paths=paths, client=s3)
    assert (again.downloaded, again.present) == (1, 2)


def test_module_zips_are_pushed_and_pulled_with_the_books(tmp_path: Path, s3: Any) -> None:
    paths, manifest = cache(tmp_path, {"adam-clarke/MRK.json": b'{"c":1}'})
    zip_bytes = b"PK\x03\x04 module"
    rel = "adam-clarke/_module/Clarke-2.0.zip"
    (paths.sources / rel).parent.mkdir(parents=True)
    (paths.sources / rel).write_bytes(zip_bytes)
    bf = book_file("adam-clarke", "MRK", zip_bytes)
    manifest.sources["adam-clarke"].module = ModuleFile(
        **{**bf.model_dump(), "file": rel, "s3_key": f"snapshots/2026-11-12/{rel}"},
        name="Clarke",
        version="2.0",
        url="https://example.invalid/Clarke.zip",
    )
    assert push(manifest, paths=paths, client=s3).uploaded == 2
    head = s3.head_object(Bucket=BUCKET, Key=f"snapshots/2026-11-12/{rel}")
    assert head["ContentType"] == "application/zip"
    (paths.sources / rel).unlink()
    assert pull(manifest, paths=paths, client=s3).downloaded == 1
    assert (paths.sources / rel).read_bytes() == zip_bytes
