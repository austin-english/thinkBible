"""Publishing to the draft channel and promoting to live, on S3 (moto) (T065, T068, R14)."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import boto3
import pytest
from moto import mock_aws

from thinkbible_pipeline.jsonio import sha256_hex
from thinkbible_pipeline.publish.build import BuildError
from thinkbible_pipeline.publish.channel import PackChannel
from thinkbible_pipeline.publish.draft import publish_draft
from thinkbible_pipeline.publish.promote import PromoteRefused, promote
from thinkbible_pipeline.report.scorecard import Scorecard
from thinkbible_pipeline.storage import S3BlobStore

BUCKET = "packs-test"
NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
FOLDER = "v1/books/2jn/1.0.0"
PROMOTABLE = Scorecard(book="2JN", run_id=None, generated_at="t", promotable=True)


@dataclass
class Packs:
    s3: Any
    draft: PackChannel
    live: PackChannel
    invalidated: list[str] = field(default_factory=list)

    def cache_control(self, key: str) -> str:
        return str(self.s3.head_object(Bucket=BUCKET, Key=key)["CacheControl"])

    def objects(self) -> list[str]:
        resp = self.s3.list_objects_v2(Bucket=BUCKET)
        return sorted(o["Key"] for o in resp.get("Contents", []))


@pytest.fixture
def packs() -> Iterator[Packs]:
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-west-2")
        s3.create_bucket(Bucket=BUCKET,
                         CreateBucketConfiguration={"LocationConstraint": "us-west-2"})  # fmt: skip
        blobs = S3BlobStore(BUCKET, client=s3)
        out = Packs(s3, PackChannel("draft", blobs), PackChannel("live", blobs))
        out.draft.invalidate = out.invalidated.append
        out.live.invalidate = out.invalidated.append
        yield out


def publish(book: Any, packs: Packs, **kw: Any) -> Any:
    return publish_draft(book.store, book.library, packs.draft, packs.live, NOW, **kw)


def do_promote(book: Any, packs: Packs, card: Scorecard = PROMOTABLE) -> Any:
    return promote(book.store, book.library, packs.draft, packs.live, card, NOW)


def test_a_complete_book_publishes_to_the_draft_channel(publish_book: Any, packs: Packs) -> None:
    result = publish(publish_book, packs)
    assert result.published and result.version == "1.0.0"
    assert packs.objects() == [
        "draft/v1/books/2jn/1.0.0/study.json",
        "draft/v1/books/2jn/1.0.0/verses/bsb.json",
        "draft/v1/books/2jn/1.0.0/verses/kjv.json",
        "draft/v1/index.json",
    ]
    for key in packs.objects():
        assert packs.cache_control(key) == "public, max-age=300"
    index = packs.draft.read_index()
    assert index is not None and index.books[0].latest == "1.0.0"
    study = index.books[0].study
    assert study.path == f"{FOLDER}/study.json"
    assert study.sha256 == sha256_hex(packs.draft.read(study.path) or b"")
    assert packs.invalidated == ["/draft/v1/index.json"]
    state = publish_book.store.read_book()
    assert state.status == "published-draft" and state.draft_version == "1.0.0"
    # Publishing again with nothing changed writes nothing.
    again = publish(publish_book, packs)
    assert not again.published and again.version == "1.0.0"


def test_a_dry_run_writes_nothing(publish_book: Any, packs: Packs) -> None:
    result = publish(publish_book, packs, dry_run=True)
    assert result.version == "1.0.0" and not result.published and packs.objects() == []


def test_a_book_with_a_failed_section_publishes_nothing(publish_book: Any, packs: Packs) -> None:
    draft = publish_book.draft("2jn-1-7")
    draft.failed = "review: no usable question"
    publish_book.write("2jn-1-7", draft)
    with pytest.raises(BuildError):
        publish(publish_book, packs)
    assert packs.objects() == []


def test_promote_copies_the_draft_files_byte_for_byte(publish_book: Any, packs: Packs) -> None:
    publish(publish_book, packs)
    result = do_promote(publish_book, packs)
    assert result.version == "1.0.0" and result.previous is None
    for name in ("study.json", "verses/bsb.json", "verses/kjv.json"):
        path = f"{FOLDER}/{name}"
        assert packs.live.read(path) == packs.draft.read(path)
        assert packs.cache_control(f"live/{path}") == "public, max-age=31536000, immutable"
    assert packs.cache_control("live/v1/index.json") == "public, max-age=300"
    live_index = packs.live.read_index()
    assert live_index is not None and live_index.books[0].latest == "1.0.0"
    assert packs.invalidated[-1] == "/live/v1/index.json"
    assert publish_book.store.read_book().last_promoted == "1.0.0"
    with pytest.raises(PromoteRefused, match="already live"):
        do_promote(publish_book, packs)


def test_promote_refuses_an_unpromotable_book(publish_book: Any, packs: Packs) -> None:
    publish(publish_book, packs)
    blockers = ["question pass rate 0.75 < 0.80", "no grader calibration for the grader"]
    card = Scorecard(book="2JN", run_id=None, generated_at="t", promotable=False, blockers=blockers)
    with pytest.raises(PromoteRefused) as err:
        do_promote(publish_book, packs, card)
    assert err.value.problems[:2] == card.blockers
    assert not any(k.startswith("live/") for k in packs.objects())


def test_promote_refuses_drafts_changed_since_publishing(publish_book: Any, packs: Packs) -> None:
    publish(publish_book, packs)
    draft = publish_book.draft("2jn-1-7")
    draft.section["context"] = "Changed after publishing."
    publish_book.write("2jn-1-7", draft)
    with pytest.raises(PromoteRefused, match=r"changed since 1\.0\.0 was published"):
        do_promote(publish_book, packs)


def test_a_second_promotion_runs_the_publish_check(publish_book: Any, packs: Packs) -> None:
    publish(publish_book, packs)
    do_promote(publish_book, packs)
    # Rewording a live question and republishing reaches the draft channel, but not live.
    draft = publish_book.draft("2jn-1-1")
    draft.section["questions"][0]["text"] = "A reworded question about the letter?"
    publish_book.write("2jn-1-1", draft)
    assert publish(publish_book, packs).version == "1.0.1"
    with pytest.raises(PromoteRefused, match="2jn-1-1-q1: its published wording changed"):
        do_promote(publish_book, packs)
    # Adding a question instead is additive: 1.1.0 goes live, and 1.0.0 stays where it was.
    draft.section["questions"][0]["text"] = "What might the elder want readers to notice in part 1?"
    draft.section["questions"].append(
        {**draft.section["questions"][0], "id": "2jn-1-1-q2", "text": "Why might love need truth?"}
    )
    draft.section["keyIdeas"].append({**draft.section["keyIdeas"][0], "id": "2jn-1-1-k2"})
    draft.section["questions"][1]["targets"] = ["2jn-1-1-k2"]
    publish_book.write("2jn-1-1", draft)
    assert publish(publish_book, packs).version == "1.1.0"
    result = do_promote(publish_book, packs)
    assert (result.version, result.previous) == ("1.1.0", "1.0.0")
    assert "live/v1/books/2jn/1.0.0/study.json" in packs.objects()
    live = packs.live.study("2JN")
    assert live is not None
    added = {q.id: q.added_in for q in live.sections[0].questions}
    assert added == {"2jn-1-1-q1": "1.0.0", "2jn-1-1-q2": "1.1.0"}
