"""Composition root for the CLI: build dependencies, start cloud runs, wait for them.

Lambdas build their own dependencies in ``cloud/handlers.py``; both call the same steps in
``stages/base.py``.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from thinkbible_pipeline.config import AwsConfig, load_aws, load_pricing, load_settings
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.exitcodes import ExitCode
from thinkbible_pipeline.llm.budget import EstimateSummary, confirm
from thinkbible_pipeline.llm.runner import BedrockRunner, ModelRunner
from thinkbible_pipeline.paths import RepoPaths, repo_paths
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.sources.snapshot import SourceError, SourceStore, load_manifest, verify
from thinkbible_pipeline.stages import registry
from thinkbible_pipeline.stages.base import (
    Deps,
    UnknownSections,
    UnknownStage,
    estimate_run,
    new_run_id,
)
from thinkbible_pipeline.storage import BlobStore, LocalBlobStore, S3BlobStore

if TYPE_CHECKING:
    from mypy_boto3_stepfunctions import SFNClient


def git_head(paths: RepoPaths) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(paths.root), "rev-parse", "--short=12", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip()


def draft_blobs(env: AwsConfig, paths: RepoPaths) -> BlobStore:
    """The S3 drafts bucket once the pipeline is deployed; ``content/drafts/`` before that."""
    if env.drafts_bucket:
        return S3BlobStore(env.drafts_bucket, "drafts/")
    return LocalBlobStore(paths.drafts_root)


def source_preflight(book_code: str, paths: RepoPaths) -> Callable[[], None]:
    def check() -> None:
        problems = verify(
            store=SourceStore.local(paths), manifest=load_manifest(paths), books={book_code}
        )
        if problems:
            raise SourceError("\n".join(f"{p.source}/{p.book}: {p.message}" for p in problems))

    return check


def local_deps(
    request: RunRequest,
    *,
    echo: Callable[[str], None] = print,
    ask: Callable[[str], str] = input,
    paths: RepoPaths | None = None,
    env: AwsConfig | None = None,
) -> Deps:
    """Dependencies for ``run --local`` and for the CLI's estimate before a cloud run."""
    paths = paths or repo_paths()
    env = env or load_aws(paths.config)
    settings = load_settings(paths.config)

    def approve(summary: EstimateSummary) -> bool:
        return confirm(summary, yes=request.auto_approve, echo=echo, ask=ask)

    def runner() -> ModelRunner:
        return BedrockRunner(settings)

    return Deps(
        store=DraftStore(request.book_info.slug, draft_blobs(env, paths)),
        settings=settings,
        pricing=load_pricing(paths.config),
        runner_factory=runner,
        approve_estimate=approve,
        stages=registry(),
        preflight=source_preflight(request.book_info.code, paths),
        echo=echo,
        code_version=git_head(paths),
    )


# --- cloud runs ---


@dataclass(frozen=True)
class CloudStart:
    exit_code: ExitCode
    message: str
    run_id: str | None = None
    execution_arn: str | None = None


def console_url(execution_arn: str, region: str) -> str:
    return (
        f"https://{region}.console.aws.amazon.com/states/home?region={region}"
        f"#/v2/executions/details/{execution_arn}"
    )


def start_cloud_run(
    request: RunRequest,
    *,
    echo: Callable[[str], None] = print,
    ask: Callable[[str], str] = input,
    paths: RepoPaths | None = None,
    env: AwsConfig | None = None,
    sfn: SFNClient | None = None,
) -> CloudStart:
    """Estimate from the S3 drafts, confirm, then start the Step Functions execution (R7)."""
    paths = paths or repo_paths()
    env = env or load_aws(paths.config)
    if not (env.state_machine_arn and env.drafts_bucket):
        return CloudStart(
            ExitCode.USAGE,
            "the pipeline isn't deployed yet (state_machine_arn / drafts_bucket are empty in "
            "pipeline/config/aws.toml): apply infra/ and copy `terraform output`, or use --local",
        )
    deps = local_deps(request, echo=echo, ask=ask, paths=paths, env=env)
    try:
        _plans, summary = estimate_run(request, deps)
    except (UnknownStage, UnknownSections) as e:
        return CloudStart(ExitCode.USAGE, str(e))
    if summary.calls_model and not deps.approve_estimate(summary):
        return CloudStart(ExitCode.OK, "not started (estimate declined)")

    run_id = new_run_id(deps.clock())
    # Every key is present, even when null: the state machine selects "$.capUsd" by path.
    payload: dict[str, Any] = {
        "runId": run_id,
        "request": request.model_dump(mode="json", by_alias=True),
        "capUsd": summary.cap_usd,
    }
    if sfn is None:
        import boto3

        sfn = boto3.client("stepfunctions", region_name=env.region)
    resp = sfn.start_execution(
        stateMachineArn=env.state_machine_arn,
        name=f"{request.book_info.slug}-{run_id}",
        input=json.dumps(payload),
    )
    arn = resp["executionArn"]
    return CloudStart(
        ExitCode.OK,
        f"started run {run_id}\n  {console_url(arn, env.region)}",
        run_id=run_id,
        execution_arn=arn,
    )


def wait_for_execution(
    execution_arn: str,
    sfn: SFNClient,
    *,
    echo: Callable[[str], None] = print,
    poll_seconds: float = 15.0,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[ExitCode, dict[str, Any] | None]:
    """Poll until the execution ends. Returns its exit code and output (``RunOutput``)."""
    while True:
        desc = sfn.describe_execution(executionArn=execution_arn)
        status = desc["status"]
        if status == "RUNNING":
            sleep(poll_seconds)
            continue
        if status == "SUCCEEDED":
            output: dict[str, Any] = json.loads(desc.get("output") or "{}")
            return ExitCode(int(output.get("exitCode", 0))), output
        error = desc.get("error", "")
        echo(f"execution {status}: {error} {desc.get('cause', '')}".strip())
        if error == "SourceChecksum":
            return ExitCode.SOURCE_CHECKSUM, None
        return ExitCode.SECTIONS_FAILED, None
