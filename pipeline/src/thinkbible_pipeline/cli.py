"""Command-line entry point (contracts/cli.md).

Thin by design: each command parses flags into a request object, calls shared code, and maps the
result to an exit code. No pipeline logic lives here.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError

from thinkbible_pipeline import __version__
from thinkbible_pipeline.exitcodes import ExitCode
from thinkbible_pipeline.requests import PromoteRequest, PublishRequest, RunRequest
from thinkbible_pipeline.stages.base import StageResult

app = typer.Typer(
    help="ThinkBible content pipeline: frozen sources -> reviewed, versioned content packs.",
    no_args_is_help=True,
)
sources_app = typer.Typer(help="Push or pull the frozen source snapshot (S3 <-> content/sources/).")
app.add_typer(sources_app, name="sources")

BookOpt = Annotated[str, typer.Option("--book", help="Book name (mark) or USFM code (MRK).")]
EnvOpt = Annotated[str, typer.Option("--env", help="dev or prod.")]


def _exit(code: ExitCode, message: str | None = None) -> NoReturn:
    if message:
        typer.echo(message, err=code != ExitCode.OK)
    raise typer.Exit(int(code))


def _not_implemented(command: str) -> NoReturn:
    _exit(ExitCode.USAGE, f"{command}: not implemented yet")


def _usage(e: ValidationError) -> NoReturn:
    msgs = "; ".join(str(err["msg"]) for err in e.errors())
    _exit(ExitCode.USAGE, f"usage error: {msgs}")


@app.callback()
def main() -> None:
    """ThinkBible content pipeline."""


@app.command()
def version() -> None:
    """Print the pipeline version."""
    typer.echo(__version__)


@app.command("import")
def import_(
    books: Annotated[str | None, typer.Option(help="Comma-separated USFM codes.")] = None,
    all_books: Annotated[bool, typer.Option("--all", help="Import every book.")] = False,
    sources: Annotated[str | None, typer.Option(help="bsb,kjv,matthew-henry,...")] = None,
) -> None:
    """Fetch and normalise source text into content/sources/ (the only network fetch)."""
    _not_implemented("import")


@sources_app.command("push")
def sources_push() -> None:
    """Upload cache files listed in the manifest but missing from S3 (write-once)."""
    _not_implemented("sources push")


@sources_app.command("pull")
def sources_pull(
    books: Annotated[str | None, typer.Option(help="Comma-separated USFM codes.")] = None,
) -> None:
    """Download manifest files missing from the local cache, then verify them."""
    _not_implemented("sources pull")


@app.command()
def verify() -> None:
    """Re-check every cached source file against manifest.json."""
    _not_implemented("verify")


def _print_stages(stages: list[StageResult]) -> None:
    for s in stages:
        line = f"{s.stage}: {s.done} done, {s.skipped} skipped, {s.failed} failed"
        if s.spent_usd:
            line += f", ${s.spent_usd:.3f}"
        if s.stopped_by == "cap":
            line += f"; stopped: cap reached ({s.not_started} not started)"
        typer.echo(line)


@app.command()
def run(
    book: BookOpt,
    stage: Annotated[str, typer.Option("--stage", help="A stage, a comma list, or all.")],
    sections: Annotated[str | None, typer.Option(help="Comma-separated section IDs.")] = None,
    fresh: Annotated[bool, typer.Option(help="Regenerate sections not yet in production.")] = False,
    refresh: Annotated[bool, typer.Option(help="Add questions to promoted sections.")] = False,
    cap: Annotated[float | None, typer.Option(help="Spend cap in USD (default 2x).")] = None,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the Proceed? prompt.")] = False,
    wait: Annotated[bool, typer.Option("--wait", help="Wait for the cloud run to finish.")] = False,
    local: Annotated[
        bool, typer.Option("--local", help="Run in this process (a few sections, prompt tuning).")
    ] = False,
    env: EnvOpt = "dev",
) -> None:
    """Run one stage, several, or all of them: in AWS by default, or in-process with --local."""
    try:
        request = RunRequest(
            book=book,
            stages=stage,  # type: ignore[arg-type]  # comma string, split by the validator
            sections=sections,  # type: ignore[arg-type]
            fresh=fresh,
            refresh=refresh,
            cap_usd=cap,
            auto_approve=yes,
            env=env,  # type: ignore[arg-type]
        )
    except ValidationError as e:
        _usage(e)

    from thinkbible_pipeline import app as wiring

    if local:
        from thinkbible_pipeline.stages.base import run as run_stages

        result = asyncio.run(run_stages(request, wiring.local_deps(request, echo=typer.echo)))
        if result.error:
            _exit(result.exit_code, result.error)
        if result.declined:
            _exit(ExitCode.OK, "not run (estimate declined)")
        _print_stages(result.stages)
        _exit(result.exit_code)

    started = wiring.start_cloud_run(request, echo=typer.echo)
    typer.echo(started.message, err=started.exit_code != ExitCode.OK)
    if started.execution_arn is None or not wait:
        _exit(started.exit_code)

    import boto3

    from thinkbible_pipeline.config import load_env

    sfn = boto3.client("stepfunctions", region_name=load_env(request.env).region)
    code, output = wiring.wait_for_execution(started.execution_arn, sfn, echo=typer.echo)
    if output:
        _print_stages([StageResult.model_validate(s) for s in output.get("stages", [])])
        typer.echo(f"spent ${float(output.get('spentUsd', 0)):.3f}")
    _exit(code)


@app.command()
def status(
    book: BookOpt,
    open_report: Annotated[
        bool, typer.Option("--open", help="Download and open the scorecard (review.html).")
    ] = False,
    env: EnvOpt = "dev",
) -> None:
    """Book status, the latest runs with spend and counts, and the scorecard."""
    import tempfile
    import webbrowser
    from pathlib import Path

    from thinkbible_pipeline import app as wiring
    from thinkbible_pipeline.config import load_env
    from thinkbible_pipeline.drafts.store import DraftStore
    from thinkbible_pipeline.paths import repo_paths

    try:
        request = PublishRequest(book=book)
    except ValidationError as e:
        _usage(e)
    paths = repo_paths()
    envcfg = load_env(env, paths.config)
    store = DraftStore(request.book_info.slug, wiring.draft_blobs(envcfg, paths))
    state = store.read_book()
    typer.echo(f"{request.book_info.name}: {state.status if state else 'not started'}")
    sections = store.section_ids()
    typer.echo(f"  {len(sections)} sections")

    runs = store.read_runs()
    run_ids = list(dict.fromkeys(r.run_id for r in reversed(runs)))[:5]
    for rid in run_ids:
        records = [r for r in runs if r.run_id == rid]
        spent = sum(r.spent_usd for r in records)
        stages = ", ".join(
            f"{r.stage} {r.sections.done}/{r.sections.failed}/{r.sections.skipped}" for r in records
        )
        stop = " (stopped: cap)" if any(r.stopped_by == "cap" for r in records) else ""
        typer.echo(f"  run {rid}: ${spent:.3f}{stop}  [done/failed/skipped] {stages}")
    if not run_ids:
        typer.echo("  no runs yet")

    if envcfg.ledger_table and run_ids:
        from thinkbible_pipeline.cloud.ledger import DynamoLedger

        ledger = DynamoLedger(envcfg.ledger_table).get(run_ids[0])
        if ledger is not None:
            cap = f"${ledger.cap_usd:.2f}" if ledger.cap_usd is not None else "none"
            typer.echo(f"  latest run: {ledger.status}, ${ledger.spent_usd:.3f} of cap {cap}")

    report = store.read_text("review.html")
    if report is None:
        typer.echo("  no scorecard yet (run the report stage)")
    elif open_report:
        out = Path(tempfile.gettempdir()) / f"thinkbible-{request.book_info.slug}-review.html"
        out.write_text(report, encoding="utf-8")
        webbrowser.open(out.as_uri())
        typer.echo(f"  opened {out}")
    _exit(ExitCode.OK)


@app.command()
def publish(
    book: BookOpt,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Publish the book's drafts to dev. A passing run that includes `report` does this itself."""
    try:
        PublishRequest(book=book, dry_run=dry_run)
    except ValidationError as e:
        _usage(e)
    _not_implemented("publish")


@app.command()
def promote(book: BookOpt) -> None:
    """Copy the book's current dev version, byte for byte, to production (gated)."""
    try:
        PromoteRequest(book=book)
    except ValidationError as e:
        _usage(e)
    _not_implemented("promote")


@app.command()
def calibrate(
    label: Annotated[
        bool, typer.Option("--label", help="Grade calibration items yourself.")
    ] = False,
    book: Annotated[str | None, typer.Option("--book")] = None,
) -> None:
    """Calibrate the quality gate's grader against your own grades (R16)."""
    _not_implemented("calibrate")


@app.command("eval")
def eval_(
    sample: Annotated[str, typer.Option(help="Sample set, e.g. mark-sample.")],
    candidate: Annotated[str, typer.Option(help="Candidate prompt set.")],
    yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    """Compare a candidate prompt set with the current one on a fixed sample."""
    _not_implemented("eval")
