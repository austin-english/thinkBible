"""The five Lambda handlers, driven the way the state machine drives them (moto + FakeRunner).

``simulate`` mirrors infra/modules/pipeline/state_machine.asl.json.tftpl: StartRun, then for
each stage PlanStage → RunSection per section → FinishStage, then FinishRun, with every payload
passed through JSON as Step Functions would.
"""

import asyncio
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
import pytest
from moto import mock_aws
from pydantic import BaseModel

from thinkbible_pipeline.cloud import handlers
from thinkbible_pipeline.cloud.ledger import DynamoLedger
from thinkbible_pipeline.config import load_pricing, load_settings
from thinkbible_pipeline.drafts.models import SectionDraft, SectionMapEntry
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.jsonio import sha256_hex
from thinkbible_pipeline.llm.runner import FakeRunner, Throttled, Usage
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.sources.models import BookFile, SourceEntry, SourceManifest
from thinkbible_pipeline.sources.snapshot import SourceError, SourceStore, verify
from thinkbible_pipeline.stages.base import Deps, SectionResult, SectionStage, run
from thinkbible_pipeline.storage import LocalBlobStore, S3BlobStore

IDS = ["mrk-1-1", "mrk-1-9", "mrk-1-12"]
TABLE = "thinkbible-pipeline-runs-test"
SOURCE_BYTES = b'{"book":"MRK","chapters":[]}'


class Summary(BaseModel):
    summary: str


class SummaryStage(SectionStage):
    def __init__(self, name: str) -> None:
        self.name = name

    def prompt_version(self, deps: Deps) -> str:
        return "v1"

    def model(self, deps: Deps) -> str | None:
        return deps.settings.stage(self.name).model

    def inputs(self, section_id: str, draft: SectionDraft, deps: Deps) -> Any:
        return {"section": section_id, "previous": draft.summary if self.name == "align" else None}

    async def execute(
        self, section_id: str, inputs: Any, draft: SectionDraft, deps: Deps
    ) -> SectionResult:
        out, usage = await deps.runner.parse(self.name, [], "x", Summary, section_id=section_id)
        if self.name == "summaries":
            draft.summary = out.summary
        return SectionResult(usages=[usage])


def manifest(sha: str) -> SourceManifest:
    bf = BookFile(
        file="bsb/MRK.json",
        s3_key="snapshots/2026-11-12/bsb/MRK.json",
        sha256=sha,
        bytes=len(SOURCE_BYTES),
        retrieved_at="2026-11-12",
        snapshot_id="2026-11-12",
    )
    entry = SourceEntry(
        kind="translation", api_id="BSB", name="BSB", license="PD", books={"MRK": bf}
    )
    return SourceManifest(bucket="sources-test", api_version="V1", sources={"bsb": entry})


@dataclass
class Cloud:
    s3: Any
    ddb: Any
    runner: FakeRunner
    manifest: SourceManifest

    def deps(self, request: RunRequest) -> Deps:
        sources = SourceStore.s3("sources-test", client=self.s3)

        def preflight() -> None:
            problems = verify(store=sources, manifest=self.manifest, books={"MRK"})
            if problems:
                raise SourceError(problems[0].message)

        return Deps(
            store=DraftStore("mrk", S3BlobStore("drafts-test", "drafts/", client=self.s3)),
            settings=load_settings(),
            pricing=load_pricing(),
            runner_factory=lambda: self.runner,
            approve_estimate=lambda _s: True,
            stages={"summaries": SummaryStage("summaries"), "align": SummaryStage("align")},
            ledger=DynamoLedger(TABLE, client=self.ddb),
            preflight=preflight,
            code_version="test",
        )


@pytest.fixture
def cloud(monkeypatch: pytest.MonkeyPatch) -> Iterator[Cloud]:
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-west-2")
        for bucket in ("drafts-test", "sources-test"):
            s3.create_bucket(
                Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": "us-west-2"}
            )
        s3.put_object(
            Bucket="sources-test", Key="snapshots/2026-11-12/bsb/MRK.json", Body=SOURCE_BYTES
        )
        ddb = boto3.client("dynamodb", region_name="us-west-2")
        ddb.create_table(
            TableName=TABLE,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": "runId", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "runId", "KeyType": "HASH"}],
        )
        runner = FakeRunner(
            responses={(st, s): {"summary": s} for st in ("summaries", "align") for s in IDS}
        )
        c = Cloud(s3, ddb, runner, manifest(sha256_hex(SOURCE_BYTES)))
        store = DraftStore("mrk", S3BlobStore("drafts-test", "drafts/", client=s3))
        store.write_section_map(
            [
                SectionMapEntry(
                    id=sid, chapter=1, verse_start=v, verse_end=v, title="t", title_source="split"
                )
                for sid, v in zip(IDS, (1, 9, 12), strict=True)
            ]
        )
        monkeypatch.setattr(handlers, "DEPS_FACTORY", c.deps)
        yield c


def _json(value: Any) -> Any:
    return json.loads(json.dumps(value))


def simulate(stages: list[str], cap_usd: float | None = None, run_id: str = "run-1") -> Any:
    request = RunRequest(book="mark", stages=stages)
    event: dict[str, Any] = {
        "runId": run_id,
        "request": request.model_dump(mode="json", by_alias=True),
        "capUsd": cap_usd,
    }
    start = _json(handlers.start_run(_json(event)))
    stage_results = []
    for stage in start["request"]["stages"]:
        # ItemSelector of the Stages map.
        stage_input = {
            "runId": start["runId"],
            "request": start["request"],
            "capUsd": start["capUsd"],
            "stage": stage,
        }
        plan = _json(handlers.plan_stage_handler(stage_input))
        outcomes = [
            _json(
                handlers.run_section(
                    {
                        "runId": plan["runId"],
                        "request": plan["request"],
                        "capUsd": plan["capUsd"],
                        "stage": plan["stage"],
                        "sectionId": sid,
                    }
                )
            )
            for sid in plan["sectionIds"]
        ]
        stage_results.append(_json(handlers.finish_stage_handler({**plan, "outcomes": outcomes})))
    # The Stages map's ResultPath ($.stageResults) is added to StartRun's output.
    return _json(handlers.finish_run({**start, "stageResults": stage_results}))


def test_full_run_matches_local_run(cloud: Cloud, tmp_path: Path) -> None:
    out = simulate(["summaries", "align"])
    assert out["exitCode"] == 0 and out["status"] == "succeeded"
    assert [(s["stage"], s["done"]) for s in out["stages"]] == [("summaries", 3), ("align", 3)]
    assert out["publishable"] is False  # no report stage in this run

    cloud_store = DraftStore("mrk", S3BlobStore("drafts-test", "drafts/", client=cloud.s3))
    records = cloud_store.read_runs()
    assert {(r.run_id, r.stage, r.code_version) for r in records} == {
        ("run-1", "summaries", "test"),
        ("run-1", "align", "test"),
    }

    # The same stages run locally produce the same drafts (apart from timestamps).
    local_store = DraftStore("mrk", LocalBlobStore(tmp_path))
    local_store.write_section_map(cloud_store.read_section_map())
    deps = cloud.deps(RunRequest(book="mark", stages=["summaries"]))
    deps.store = local_store
    asyncio.run(run(RunRequest(book="mark", stages=["summaries", "align"]), deps))
    for sid in IDS:
        c, loc = cloud_store.read_draft(sid), local_store.read_draft(sid)
        assert c is not None and loc is not None
        assert c.summary == loc.summary == sid
        assert {k: (v.status, v.input_hash) for k, v in c.stages.items()} == {
            k: (v.status, v.input_hash) for k, v in loc.stages.items()
        }

    # A second run skips everything (SC-005).
    again = simulate(["summaries", "align"], run_id="run-2")
    assert [(s["done"], s["skipped"]) for s in again["stages"]] == [(0, 3), (0, 3)]


def test_cap_stops_new_sections_and_later_stages(cloud: Cloud) -> None:
    cloud.runner.usage = Usage(model="anthropic.claude-haiku-5-5", output_tokens=1_000_000)
    out = simulate(["summaries", "align"], cap_usd=0.6)  # each section costs $0.50
    assert out["exitCode"] == 4 and out["status"] == "stopped-cap"
    summaries, align = out["stages"]
    assert (summaries["done"], summaries["notStarted"], summaries["stoppedBy"]) == (2, 1, "cap")
    assert align["stoppedBy"] == "cap" and align["done"] == 0
    state = DynamoLedger(TABLE, client=cloud.ddb).get("run-1")
    assert state is not None and state.spent_usd == pytest.approx(1.0)


def test_failed_section_is_recorded_and_others_continue(cloud: Cloud) -> None:
    from thinkbible_pipeline.llm.runner import ModelError

    cloud.runner.responses[("summaries", "mrk-1-9")] = ModelError("boom")
    out = simulate(["summaries"])
    assert out["exitCode"] == 3
    assert out["stages"][0]["failures"] == {"mrk-1-9": "boom"}


def test_throttling_escapes_for_a_step_functions_retry(cloud: Cloud) -> None:
    cloud.runner.responses[("summaries", "mrk-1-1")] = Throttled("429")
    with pytest.raises(Throttled):
        simulate(["summaries"])


def test_source_checksum_mismatch_fails_start_run(cloud: Cloud) -> None:
    cloud.manifest = manifest("0" * 64)
    with pytest.raises(handlers.SourceChecksumError):
        simulate(["summaries"])
