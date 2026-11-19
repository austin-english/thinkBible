"""Live content only grows (T079, US6, FR-024, FR-024a), on S3 (moto) with FakeRunner."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
import pytest
from moto import mock_aws

from thinkbible_pipeline.config import load_pricing, load_settings
from thinkbible_pipeline.drafts.live import FROZEN_MESSAGE
from thinkbible_pipeline.drafts.retire import retire
from thinkbible_pipeline.llm.runner import FakeRunner
from thinkbible_pipeline.publish.build import BuildError
from thinkbible_pipeline.publish.channel import PackChannel
from thinkbible_pipeline.publish.draft import publish_draft
from thinkbible_pipeline.publish.promote import promote
from thinkbible_pipeline.report.scorecard import Scorecard
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.stages import registry
from thinkbible_pipeline.stages.base import Deps, run
from thinkbible_pipeline.storage import S3BlobStore

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
CARD = Scorecard(book="2JN", run_id=None, generated_at="t", promotable=True)
SID = "2jn-1-1"


@pytest.fixture
def channels() -> Iterator[tuple[PackChannel, PackChannel]]:
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-west-2")
        s3.create_bucket(Bucket="packs-test",
                         CreateBucketConfiguration={"LocationConstraint": "us-west-2"})  # fmt: skip
        blobs = S3BlobStore("packs-test", client=s3)
        yield PackChannel("draft", blobs), PackChannel("live", blobs)


def go_live(book: Any, channels: tuple[PackChannel, PackChannel]) -> str:
    result = publish_draft(book.store, book.library, *channels, NOW)
    promote(book.store, book.library, *channels, CARD, NOW)
    return str(result.version)


def deps(book: Any, responses: dict[tuple[str, str], Any] | None = None) -> Deps:
    runner = FakeRunner(responses=responses or {})
    return Deps(store=book.store, settings=load_settings(), pricing=load_pricing(),
                runner_factory=lambda: runner, approve_estimate=lambda _s: True,
                stages=registry(), library=book.library)  # fmt: skip


def draft_files(book: Any) -> dict[str, bytes]:
    root = Path(book.store.blobs.root)
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("sections/*.json")}


def test_live_sections_are_skipped_by_every_content_stage(
    publish_book: Any, channels: tuple[PackChannel, PackChannel]
) -> None:
    go_live(publish_book, channels)
    before = draft_files(publish_book)
    d = deps(publish_book)
    request = RunRequest(book="2JN", stages=["summaries", "generate", "align"], fresh=True)
    result = asyncio.run(run(request, d))
    assert [(s.stage, s.done, s.live) for s in result.stages] == [
        ("summaries", 0, 2), ("generate", 0, 2), ("align", 0, 2)
    ]  # fmt: skip
    assert d.runner.calls == []  # type: ignore[attr-defined]
    assert draft_files(publish_book) == before  # byte for byte


def test_changed_live_wording_fails_check_and_cannot_publish(
    publish_book: Any, channels: tuple[PackChannel, PackChannel]
) -> None:
    go_live(publish_book, channels)
    draft = publish_book.draft(SID)
    draft.section["questions"][0]["text"] = "A quietly reworded question about the letter?"
    publish_book.write(SID, draft)
    result = asyncio.run(run(RunRequest(book="2JN", stages=["check"], fresh=True),
                             deps(publish_book)))  # fmt: skip
    assert FROZEN_MESSAGE in result.stages[0].failures[SID]
    with pytest.raises(BuildError, match="failed"):
        publish_draft(publish_book.store, publish_book.library, *channels, NOW)


def test_retire_and_replace_goes_live_as_a_minor_version(
    publish_book: Any, channels: tuple[PackChannel, PackChannel]
) -> None:
    assert go_live(publish_book, channels) == "1.0.0"
    result = retire(publish_book.store, f"{SID}-q1", replace=True,
                    text="What might the elder be guarding by tying love to truth?")  # fmt: skip
    assert result.retired == [f"{SID}-q1"] and result.replacement == f"{SID}-q2"
    assert go_live(publish_book, channels) == "1.1.0"
    pack = channels[1].study("2JN")
    assert pack is not None
    old, new = pack.sections[0].questions
    # The 1.0.0 question is still there, word for word, now retired; its replacement records it.
    assert (old.id, old.status, old.added_in, old.retired_in) == (
        f"{SID}-q1", "retired", "1.0.0", "1.1.0"
    )  # fmt: skip
    assert old.text == "What might the elder want readers to notice in part 1?"
    assert (new.id, new.status, new.added_in, new.replaces) == (
        f"{SID}-q2", "active", "1.1.0", f"{SID}-q1"
    )  # fmt: skip


def test_retiring_a_key_idea_retires_the_questions_aimed_only_at_it(publish_book: Any) -> None:
    result = retire(publish_book.store, f"{SID}-k1")
    assert result.retired == [f"{SID}-k1", f"{SID}-q1"] and result.replacement is None


def test_refresh_adds_new_questions_in_free_places_only(
    publish_book: Any, channels: tuple[PackChannel, PackChannel]
) -> None:
    # A live section with two key ideas and one question has one free place.
    draft = publish_book.draft(SID)
    second = {**draft.section["keyIdeas"][0], "id": f"{SID}-k2", "title": "Love keeps truth"}
    draft.section["keyIdeas"].append(second)
    draft.evidence[f"{SID}-k2"] = draft.evidence[f"{SID}-k1"]
    draft.ids.k = 2
    publish_book.write(SID, draft)
    go_live(publish_book, channels)
    live_before = publish_book.draft(SID).live

    new_question = {
        "text": "Why might truth matter so much to how this family loves?",
        "type": "meaning",
        "verseStart": 1,
        "verseEnd": 6,
        "targets": [f"{SID}-k2"],
    }
    grades = {
        "items": [
            {"itemId": i, "score": 4, "reason": "Fine.", "focus": "big-picture"}
            for i in (f"{SID}-k1", f"{SID}-k2", f"{SID}-q2", f"{SID}-context")
        ]
    }
    d = deps(publish_book, {("generate.questions", SID): {"questions": [new_question]},
                            ("review", SID): grades})  # fmt: skip
    request = RunRequest(book="2JN", stages=["generate", "align", "check", "review"],
                         sections=SID, refresh=True)  # fmt: skip
    result = asyncio.run(run(request, d))
    assert all(not s.failures for s in result.stages), result.stages
    after = publish_book.draft(SID)
    assert [q["id"] for q in after.section["questions"]] == [f"{SID}-q1", f"{SID}-q2"]
    assert after.section["questions"][0]["text"] == (
        "What might the elder want readers to notice in part 1?"
    )
    assert after.live == live_before  # nothing live changed
    assert go_live(publish_book, channels) == "1.1.0"  # an added question: a minor version


def test_a_live_section_graded_badly_keeps_everything_and_is_listed_as_weak(
    publish_book: Any, channels: tuple[PackChannel, PackChannel]
) -> None:
    from thinkbible_pipeline.report.scorecard import build_scorecard

    go_live(publish_book, channels)
    before = publish_book.draft(SID).section
    grades = {"items": [{"itemId": i, "score": 1, "reason": "Weak.", "failedRules": ["faithful"]}
                        for i in (f"{SID}-k1", f"{SID}-q1", f"{SID}-context")]}  # fmt: skip
    request = RunRequest(book="2JN", stages=["review"], sections=SID, fresh=True)
    result = asyncio.run(run(request, deps(publish_book, {("review", SID): grades})))
    assert not result.stages[0].failures
    after = publish_book.draft(SID)
    assert after.section == before  # no idea dropped, no question re-picked, no note removed
    entries = publish_book.store.read_section_map()
    card = build_scorecard("2JN", entries, {e.id: publish_book.draft(e.id) for e in entries},
                           [], NOW)  # fmt: skip
    assert [w.section_id for w in card.weak_live] == [f"{SID}-k1", f"{SID}-q1"]
