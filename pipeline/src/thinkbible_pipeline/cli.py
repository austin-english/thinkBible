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
from thinkbible_pipeline.requests import ApproveRequest, PublishRequest, RunRequest

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


@app.command()
def run(
    book: BookOpt,
    stage: Annotated[str, typer.Option("--stage", help="A stage, a comma list, or all.")],
    sections: Annotated[str | None, typer.Option(help="Comma-separated section IDs.")] = None,
    fresh: Annotated[bool, typer.Option(help="Regenerate unpublished sections.")] = False,
    refresh: Annotated[bool, typer.Option(help="Add questions to published sections.")] = False,
    cap: Annotated[float | None, typer.Option(help="Spend cap in USD (default 2x).")] = None,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the Proceed? prompt.")] = False,
    env: EnvOpt = "dev",
) -> None:
    """Run one stage, several, or all of them."""
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

    from thinkbible_pipeline.app import local_deps
    from thinkbible_pipeline.stages.base import run as run_stages

    result = asyncio.run(run_stages(request, local_deps(request, echo=typer.echo)))
    if result.error:
        _exit(result.exit_code, result.error)
    for s in result.stages:
        line = f"{s.stage}: {s.done} done, {s.skipped} skipped, {s.failed} failed"
        if s.spent_usd:
            line += f", ${s.spent_usd:.3f}"
        if s.declined:
            line = f"{s.stage}: not run (estimate declined)"
        elif s.stopped_by == "cap":
            line += f"; stopped: cap reached ({s.not_started} not started)"
        typer.echo(line)
    _exit(result.exit_code)


@app.command()
def status(book: BookOpt) -> None:
    """Book status, per-stage counts, spend so far, and what is left."""
    _not_implemented("status")


@app.command()
def approve(book: BookOpt) -> None:
    """Gate before publishing: no failing checks, flags listed, typed confirmation."""
    try:
        ApproveRequest(book=book)
    except ValidationError as e:
        _usage(e)
    _not_implemented("approve")


@app.command()
def publish(
    book: BookOpt,
    env: EnvOpt = "dev",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Build and upload the approved pack, then update the index."""
    try:
        PublishRequest(book=book, env=env, dry_run=dry_run)  # type: ignore[arg-type]
    except ValidationError as e:
        _usage(e)
    _not_implemented("publish")


@app.command("eval")
def eval_(
    sample: Annotated[str, typer.Option(help="Sample set, e.g. mark-sample.")],
    candidate: Annotated[str, typer.Option(help="Candidate prompt set.")],
    yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    """Compare a candidate prompt set with the current one on a fixed sample."""
    _not_implemented("eval")
