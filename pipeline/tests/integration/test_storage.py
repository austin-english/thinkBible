"""BlobStore: the local folder and S3 behave the same, conditional writes included."""

from collections.abc import Iterator
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from thinkbible_pipeline.storage import BlobStore, LocalBlobStore, PreconditionFailed, S3BlobStore


@pytest.fixture(params=["local", "s3"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[BlobStore]:
    if request.param == "local":
        yield LocalBlobStore(tmp_path / "blobs")
        return
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-west-2")
        s3.create_bucket(
            Bucket="drafts-test", CreateBucketConfiguration={"LocationConstraint": "us-west-2"}
        )
        yield S3BlobStore("drafts-test", "drafts/", client=s3)


def test_put_get_list(store: BlobStore) -> None:
    assert store.get("mrk/book.json") is None
    etag = store.put("mrk/book.json", b'{"a":1}')
    blob = store.get("mrk/book.json")
    assert blob is not None and blob.data == b'{"a":1}' and blob.etag == etag
    store.put("mrk/sections/mrk-1-1.json", b"{}")
    store.put("jhn/book.json", b"{}")
    assert [k for k, _ in store.list("mrk/")] == ["mrk/book.json", "mrk/sections/mrk-1-1.json"]


def test_if_none_match_refuses_existing(store: BlobStore) -> None:
    store.put("k.json", b"1", if_none_match=True)
    with pytest.raises(PreconditionFailed):
        store.put("k.json", b"2", if_none_match=True)


def test_if_match_refuses_changed(store: BlobStore) -> None:
    first = store.put("k.json", b"1")
    second = store.put("k.json", b"2", if_match=first)
    with pytest.raises(PreconditionFailed):
        store.put("k.json", b"3", if_match=first)  # stale etag
    store.put("k.json", b"3", if_match=second)


def test_local_keys_cannot_escape_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        LocalBlobStore(tmp_path / "blobs").put("../outside.json", b"x")
