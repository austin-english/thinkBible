"""The CLI's cloud path: refuse before deploy, estimate + start an execution, map its result."""

import dataclasses
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import boto3
import pytest
from moto import mock_aws
from pydantic import BaseModel

from thinkbible_pipeline import app
from thinkbible_pipeline.config import load_aws, load_settings
from thinkbible_pipeline.drafts.models import SectionDraft, SectionMapEntry
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.exitcodes import ExitCode
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.stages.base import Deps, SectionResult, SectionStage
from thinkbible_pipeline.storage import S3BlobStore


class Out(BaseModel):
    summary: str


class Stage(SectionStage):
    name = "summaries"

    def prompt_version(self, deps: Deps) -> str:
        return "v1"

    def model(self, deps: Deps) -> str | None:
        return deps.settings.stage(self.name).model

    def inputs(self, section_id: str, draft: SectionDraft, deps: Deps) -> Any:
        return {"s": section_id}

    async def execute(
        self, section_id: str, inputs: Any, draft: SectionDraft, deps: Deps
    ) -> SectionResult:
        raise AssertionError("the CLI only estimates; the cloud runs sections")


@pytest.fixture
def aws(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Any, str]]:
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-west-2")
        s3.create_bucket(
            Bucket="drafts-test", CreateBucketConfiguration={"LocationConstraint": "us-west-2"}
        )
        sfn = boto3.client("stepfunctions", region_name="us-west-2")
        arn = sfn.create_state_machine(
            name="thinkbible-pipeline-test",
            definition=json.dumps({"StartAt": "A", "States": {"A": {"Type": "Succeed"}}}),
            roleArn="arn:aws:iam::123456789012:role/sfn",
        )["stateMachineArn"]
        DraftStore("mrk", S3BlobStore("drafts-test", "drafts/", client=s3)).write_section_map(
            [
                SectionMapEntry(
                    id="mrk-1-1",
                    chapter=1,
                    verse_start=1,
                    verse_end=8,
                    title="t",
                    title_source="bsb-heading",
                )
            ]
        )
        monkeypatch.setattr(app, "registry", lambda: {"summaries": Stage()})
        yield sfn, arn


def test_refuses_before_deploy() -> None:
    env = dataclasses.replace(load_aws(), state_machine_arn="", drafts_bucket="")
    started = app.start_cloud_run(RunRequest(book="mark", stages=["summaries"]), env=env)
    assert started.exit_code == ExitCode.USAGE
    assert "--local" in started.message and started.execution_arn is None


def test_estimates_then_starts_an_execution(aws: tuple[Any, str]) -> None:
    sfn, arn = aws
    env = dataclasses.replace(load_aws(), state_machine_arn=arn, drafts_bucket="drafts-test")
    lines: list[str] = []
    started = app.start_cloud_run(
        RunRequest(book="mark", stages=["summaries"]),
        env=env,
        sfn=sfn,
        echo=lines.append,
        ask=lambda _p: "y",
    )
    assert started.exit_code == ExitCode.OK and started.execution_arn
    assert lines[0].startswith("summaries: 1 sections to process")
    desc = sfn.describe_execution(executionArn=started.execution_arn)
    payload = json.loads(desc["input"])
    assert payload["runId"] == started.run_id
    assert payload["request"]["stages"] == ["summaries"]
    default = load_settings().stage("summaries").default_cost_usd
    assert payload["capUsd"] == pytest.approx(2 * default)  # 2x the default estimate
    assert "us-west-2.console.aws.amazon.com/states" in started.message


def test_declined_estimate_starts_nothing(aws: tuple[Any, str]) -> None:
    sfn, arn = aws
    env = dataclasses.replace(load_aws(), state_machine_arn=arn, drafts_bucket="drafts-test")
    started = app.start_cloud_run(
        RunRequest(book="mark", stages=["summaries"]),
        env=env,
        sfn=sfn,
        ask=lambda _p: "n",
        echo=lambda _l: None,
    )
    assert started.execution_arn is None
    assert sfn.list_executions(stateMachineArn=arn)["executions"] == []


class FakeSfn:
    def __init__(self, *responses: dict[str, Any]) -> None:
        self.responses = list(responses)

    def describe_execution(self, executionArn: str) -> dict[str, Any]:
        return self.responses.pop(0)


def test_wait_maps_execution_results() -> None:
    running = {"status": "RUNNING"}
    ok = {"status": "SUCCEEDED", "output": json.dumps({"exitCode": 3, "stages": []})}
    code, output = app.wait_for_execution(
        "arn",
        FakeSfn(running, ok),
        sleep=lambda _s: None,
        echo=lambda _l: None,  # type: ignore[arg-type]
    )
    assert code == ExitCode.SECTIONS_FAILED and output == {"exitCode": 3, "stages": []}
    failed = {"status": "FAILED", "error": "SourceChecksum", "cause": "bsb/MRK.json"}
    code, output = app.wait_for_execution(
        "arn",
        FakeSfn(failed),
        sleep=lambda _s: None,
        echo=lambda _l: None,  # type: ignore[arg-type]
    )
    assert code == ExitCode.SOURCE_CHECKSUM and output is None


def test_local_drafts_until_deployed(tmp_path: Path) -> None:
    from thinkbible_pipeline.paths import RepoPaths
    from thinkbible_pipeline.storage import LocalBlobStore

    env = dataclasses.replace(load_aws(), drafts_bucket="")
    assert isinstance(app.draft_blobs(env, RepoPaths(tmp_path)), LocalBlobStore)
    env = dataclasses.replace(env, drafts_bucket="drafts-test")
    assert isinstance(app.draft_blobs(env, RepoPaths(tmp_path)), S3BlobStore)
