"""Command-line entry point (contracts/cli.md).

Thin by design: each command parses flags into a request object, calls shared code, and maps the
result to an exit code. No pipeline logic lives here.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, NoReturn

import typer
from pydantic import ValidationError

from thinkbible_pipeline import __version__
from thinkbible_pipeline.exitcodes import ExitCode
from thinkbible_pipeline.requests import PromoteRequest, PublishRequest, RunRequest
from thinkbible_pipeline.sources.models import SourceManifest
from thinkbible_pipeline.stages.base import StageResult

app = typer.Typer(
    help="ThinkBible content pipeline: frozen sources -> reviewed, versioned content packs.",
    no_args_is_help=True,
)
sources_app = typer.Typer(
    help="Check, push or pull the frozen source snapshot (S3 <-> content/sources/)."
)
app.add_typer(sources_app, name="sources")

BookOpt = Annotated[str, typer.Option("--book", help="Book name (mark) or USFM code (MRK).")]


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


def _book_codes(books: str | None, all_books: bool) -> list[str] | None:
    """``--books mark,MAT`` → ["MRK", "MAT"]; ``--all`` → None (every book)."""
    from thinkbible_core.ids import UnknownBookError, resolve_book

    if all_books:
        return None
    if not books:
        _exit(ExitCode.USAGE, "pass --books MRK,... or --all")
    try:
        return [resolve_book(b.strip()).code for b in books.split(",") if b.strip()]
    except UnknownBookError as e:
        _exit(ExitCode.USAGE, f"usage error: {e}")


@app.command("import")
def import_(
    books: Annotated[str | None, typer.Option(help="Comma-separated books (MRK or mark).")] = None,
    all_books: Annotated[bool, typer.Option("--all", help="Import every book.")] = False,
    sources: Annotated[str | None, typer.Option(help="bsb,kjv,matthew-henry,...")] = None,
    api_version: Annotated[
        str | None, typer.Option(help="HelloAO API version (default: the latest).")
    ] = None,
    refresh: Annotated[
        bool, typer.Option(help="Re-fetch books already imported (default: skip them).")
    ] = False,
) -> None:
    """Fetch and normalise source text into content/sources/ (the only network fetch)."""
    from thinkbible_pipeline.config import load_aws
    from thinkbible_pipeline.sources.importer import FetchError, NotFound, import_sources

    codes = _book_codes(books, all_books)
    try:
        result = import_sources(
            books=codes,
            sources=[s.strip() for s in sources.split(",")] if sources else None,
            bucket=load_aws().sources_bucket,
            api_version=api_version,
            refresh=refresh,
            echo=typer.echo,
        )
    except (FetchError, NotFound, ValueError) as e:
        _exit(ExitCode.USAGE, f"import failed: {e}")
    typer.echo(
        f"snapshot {result.snapshot_id} (API {result.api_version}): "
        f"{len(result.written)} files written, {len(result.skipped)} already imported"
    )
    if result.absent:
        typer.echo(f"  not covered by the source: {', '.join(result.absent)}")
    if result.modules:
        typer.echo(f"  CrossWire modules: {', '.join(result.modules)}")
    typer.echo(
        "next: `thinkbible-pipeline sources check`, `thinkbible-pipeline verify`, "
        "then `thinkbible-pipeline sources push`"
    )
    _exit(ExitCode.OK)


def _manifest_or_exit() -> SourceManifest:
    from thinkbible_pipeline.sources.snapshot import MissingSource, load_manifest

    try:
        return load_manifest()
    except MissingSource:
        _exit(ExitCode.SOURCE_CHECKSUM, "content/sources/manifest.json not found: run `import`")


@sources_app.command("push")
def sources_push() -> None:
    """Upload cache files listed in the manifest but missing from S3 (write-once)."""
    import boto3

    from thinkbible_pipeline.config import load_aws
    from thinkbible_pipeline.sources.snapshot import SourceError
    from thinkbible_pipeline.sources.store import PushRefused, push

    envcfg = load_aws()
    manifest = _manifest_or_exit()
    typer.echo(f"uploading files missing from s3://{envcfg.sources_bucket} (one line per file) …")
    try:
        result = push(
            manifest,
            client=boto3.client("s3", region_name=envcfg.region),
            bucket=envcfg.sources_bucket,
            progress=typer.echo,
        )
    except (PushRefused, SourceError) as e:
        _exit(ExitCode.SOURCE_CHECKSUM, str(e))
    typer.echo(
        f"{result.uploaded} uploaded, {result.skipped} already in s3://{envcfg.sources_bucket}"
    )
    _exit(ExitCode.OK)


@sources_app.command("pull")
def sources_pull(
    books: Annotated[str | None, typer.Option(help="Comma-separated books (MRK or mark).")] = None,
) -> None:
    """Download manifest files missing from the local cache, then verify them."""
    import boto3

    from thinkbible_pipeline.config import load_aws
    from thinkbible_pipeline.sources.store import pull

    envcfg = load_aws()
    manifest = _manifest_or_exit()
    codes = _book_codes(books, all_books=books is None)
    result = pull(
        manifest,
        client=boto3.client("s3", region_name=envcfg.region),
        bucket=envcfg.sources_bucket,
        books=set(codes) if codes else None,
        progress=typer.echo,
    )
    typer.echo(f"{result.downloaded} downloaded, {result.present} already present and verified")
    for problem in result.problems:
        typer.echo(f"  {problem}", err=True)
    _exit(ExitCode.SOURCE_CHECKSUM if result.problems else ExitCode.OK)


@sources_app.command("check")
def sources_check(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="List every warning.")] = False,
) -> None:
    """Check the cached snapshot is complete and in place (versification, coverage, order)."""
    from thinkbible_pipeline.sources.check import check_sources
    from thinkbible_pipeline.sources.snapshot import SourceStore

    report = check_sources(store=SourceStore.local(), manifest=_manifest_or_exit())
    for r in report.sources:
        status = "FAIL" if r.errors else "ok"
        typer.echo(f"{r.source} [{r.origin or 'unknown origin'}]: {status}, {r.books} books")
        typer.echo(f"  {r.summary}")
        warnings = r.warnings if verbose else r.warnings[:5]
        for w in warnings:
            typer.echo(f"  warning: {w}")
        if len(r.warnings) > len(warnings):
            typer.echo(f"  … {len(r.warnings) - len(warnings)} more warnings (--verbose)")
        for e in r.errors[:20]:
            typer.echo(f"  error: {e}", err=True)
        if len(r.errors) > 20:
            typer.echo(f"  … {len(r.errors) - 20} more errors", err=True)
    if not report.ok:
        _exit(ExitCode.SOURCE_CHECKSUM, "sources check failed: fix or re-import before pushing")
    _exit(ExitCode.OK)


@app.command()
def verify(
    remote: Annotated[
        bool,
        typer.Option(
            "--remote",
            help="Check the sources bucket instead of the local cache (downloads every file).",
        ),
    ] = False,
) -> None:
    """Re-check every source file against manifest.json: the local cache, or S3 with --remote."""
    from thinkbible_pipeline.sources.snapshot import SourceStore
    from thinkbible_pipeline.sources.snapshot import verify as verify_sources

    manifest = _manifest_or_exit()
    if remote:
        import boto3

        from thinkbible_pipeline.config import load_aws

        aws = load_aws()
        store = SourceStore.s3(
            aws.sources_bucket, client=boto3.client("s3", region_name=aws.region)
        )
    else:
        store = SourceStore.local()
    if remote:
        typer.echo(f"downloading and checking every file in {store.label} …")
    problems = verify_sources(
        store=store, manifest=manifest, progress=typer.echo if remote else None
    )
    total = sum(len(e.files()) for e in manifest.sources.values())
    for p in problems:
        typer.echo(f"{p.source}/{p.book}: {p.message}", err=True)
    if problems:
        _exit(ExitCode.SOURCE_CHECKSUM, f"{len(problems)} of {total} files failed in {store.label}")
    _exit(ExitCode.OK, f"all {total} files in {store.label} match manifest.json")


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
    fresh: Annotated[bool, typer.Option(help="Regenerate sections not yet live.")] = False,
    refresh: Annotated[bool, typer.Option(help="Add questions to promoted sections.")] = False,
    cap: Annotated[float | None, typer.Option(help="Spend cap in USD (default 2x).")] = None,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the Proceed? prompt.")] = False,
    wait: Annotated[bool, typer.Option("--wait", help="Wait for the cloud run to finish.")] = False,
    local: Annotated[
        bool, typer.Option("--local", help="Run in this process (a few sections, prompt tuning).")
    ] = False,
) -> None:
    """Run one stage, several, or all of them: in AWS by default, or in-process with --local."""
    from thinkbible_pipeline.stages import expand_all

    try:
        request = RunRequest(
            book=book,
            stages=expand_all(stage),  # type: ignore[arg-type]  # comma string, split later
            sections=sections,  # type: ignore[arg-type]
            fresh=fresh,
            refresh=refresh,
            cap_usd=cap,
            auto_approve=yes,
        )
    except ValidationError as e:
        _usage(e)

    from thinkbible_pipeline import app as wiring

    if local:
        from thinkbible_pipeline.publish.draft import publish_after_run
        from thinkbible_pipeline.stages.base import run as run_stages

        deps = wiring.local_deps(request, echo=typer.echo)
        result = asyncio.run(run_stages(request, deps))
        if result.error:
            _exit(result.exit_code, result.error)
        if result.declined:
            _exit(ExitCode.OK, "not run (estimate declined)")
        _print_stages(result.stages)
        if "report" in request.stages and result.exit_code == ExitCode.OK:
            publish_after_run(deps.store, deps.sources, wiring.channels(), deps.clock(), typer.echo)
        _exit(result.exit_code)

    started = wiring.start_cloud_run(request, echo=typer.echo)
    typer.echo(started.message, err=started.exit_code != ExitCode.OK)
    if started.execution_arn is None or not wait:
        _exit(started.exit_code)

    import boto3

    from thinkbible_pipeline.config import load_aws

    sfn = boto3.client("stepfunctions", region_name=load_aws().region)
    code, output = wiring.wait_for_execution(started.execution_arn, sfn, echo=typer.echo)
    if output:
        _print_stages([StageResult.model_validate(s) for s in output.get("stages", [])])
        if output.get("publish"):
            typer.echo(str(output["publish"]))
        typer.echo(f"spent ${float(output.get('spentUsd', 0)):.3f}")
    _exit(code)


@app.command()
def excerpts(
    book: BookOpt,
    section: Annotated[str, typer.Option("--section", help="Section ID, e.g. mrk-1-1.")],
    commentator: Annotated[
        str | None, typer.Option(help="Only this commentator (e.g. jamieson-fausset-brown).")
    ] = None,
    full: Annotated[bool, typer.Option("--full", help="Print every part in full.")] = False,
) -> None:
    """Show what each commentator contributes to a section: exactly what the model is given."""
    from thinkbible_pipeline.commentary.gather import COMMENTATORS, gather
    from thinkbible_pipeline.config import load_settings
    from thinkbible_pipeline.sections.builder import build_sections
    from thinkbible_pipeline.sources.snapshot import SourceError, SourceLibrary

    try:
        request = PublishRequest(book=book)
    except ValidationError as e:
        _usage(e)
    code = request.book_info.code
    try:
        library = SourceLibrary.local()
        sections = build_sections(
            code, library.translation("bsb", code), library.commentary("matthew-henry", code)
        )
    except SourceError as e:
        _exit(ExitCode.SOURCE_CHECKSUM, str(e))
    entry = next((s for s in sections if s.id == section), None)
    if entry is None:
        _exit(
            ExitCode.USAGE,
            f"no section {section!r}; {code} has {sections[0].id} … {sections[-1].id}",
        )
    if commentator is not None and commentator not in COMMENTATORS:
        _exit(ExitCode.USAGE, f"unknown commentator {commentator!r}; expected {COMMENTATORS}")
    cap = load_settings().excerpt_cap_tokens
    typer.echo(
        f"{entry.id}: {request.book_info.name} {entry.chapter}:{entry.verse_start}-"
        f'{entry.verse_end} "{entry.title}" (cap {cap:,} tokens per commentator)'
    )
    for name in [commentator] if commentator else COMMENTATORS:
        ex = gather(entry, code, name, library, cap_tokens=cap)
        flags = (", trimmed" if ex.trimmed else "") + (
            f", follows {', '.join(ex.cross_refs)}" if ex.cross_refs else ""
        )
        typer.echo(f"\n== {name}: {ex.tokens:,} tokens, {len(ex.parts)} parts{flags}")
        for part in ex.parts:
            body = part.text if full else part.text[:300] + ("…" if len(part.text) > 300 else "")
            typer.echo(f"\n[{part.label}]\n{body}")
    _exit(ExitCode.OK)


@app.command()
def status(
    book: BookOpt,
    open_report: Annotated[
        bool, typer.Option("--open", help="Download and open the scorecard (review.html).")
    ] = False,
) -> None:
    """Book status, the latest runs with spend and counts, and the scorecard."""
    import tempfile
    import webbrowser
    from pathlib import Path

    from thinkbible_pipeline import app as wiring
    from thinkbible_pipeline.config import load_aws
    from thinkbible_pipeline.drafts.store import DraftStore
    from thinkbible_pipeline.paths import repo_paths

    try:
        request = PublishRequest(book=book)
    except ValidationError as e:
        _usage(e)
    paths = repo_paths()
    envcfg = load_aws(paths.config)
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
    """Publish the book's drafts to the draft channel. A passing run with `report` does this."""
    from thinkbible_pipeline import app as wiring
    from thinkbible_pipeline.publish.build import BuildError, build_pack
    from thinkbible_pipeline.publish.draft import problem_summary, publish_draft

    try:
        request = PublishRequest(book=book, dry_run=dry_run)
    except ValidationError as e:
        _usage(e)
    store, library = wiring.publish_store(request.book_info.slug), wiring.library()
    channels = wiring.channels()
    now = wiring.now()
    try:
        if channels is None:
            if not dry_run:
                _exit(ExitCode.USAGE, wiring.NO_CHANNELS)
            built = build_pack(store, library, previous=None, live=None, now=now)
            assert built is not None
            typer.echo(f"dry run: {request.book_info.name} builds as a valid pack")
            _exit(ExitCode.OK)
        result = publish_draft(store, library, *channels, now, dry_run=dry_run)
    except BuildError as e:
        for problem in e.problems:
            typer.echo(f"  {problem}", err=True)
        _exit(ExitCode.GATE_REFUSED, f"not published: {problem_summary(e.problems)}")
    if not result.published and not dry_run:
        _exit(ExitCode.OK, f"unchanged: {result.version} is already on the draft channel")
    verb = "would publish" if dry_run else "published"
    typer.echo(f"{verb} {request.book_info.name} {result.version} ({result.change})")
    for path, size in result.files.items():
        typer.echo(f"  draft/{path}  {size:,} bytes")
    _exit(ExitCode.OK)


@app.command()
def promote(book: BookOpt) -> None:
    """Copy the book's current draft version, byte for byte, to the live channel (gated)."""
    from thinkbible_pipeline import app as wiring
    from thinkbible_pipeline.publish.promote import PromoteRefused, current_scorecard
    from thinkbible_pipeline.publish.promote import promote as promote_book

    try:
        request = PromoteRequest(book=book)
    except ValidationError as e:
        _usage(e)
    channels = wiring.channels()
    if channels is None:
        _exit(ExitCode.USAGE, wiring.NO_CHANNELS)
    store, now = wiring.publish_store(request.book_info.slug), wiring.now()
    card = current_scorecard(store, wiring.settings(), wiring.calibration(), now)
    try:
        result = promote_book(store, wiring.library(), *channels, card, now)
    except PromoteRefused as e:
        for problem in e.problems:
            typer.echo(f"  {problem}", err=True)
        _exit(ExitCode.GATE_REFUSED, f"not promoted: {len(e.problems)} problem(s)")
    was = f" (replacing {result.previous})" if result.previous else ""
    _exit(ExitCode.OK, f"promoted {request.book_info.name} {result.version} to live{was}")


@app.command()
def calibrate(
    label: Annotated[
        bool, typer.Option("--label", help="Grade calibration items yourself.")
    ] = False,
    book: Annotated[str, typer.Option("--book", help="Book whose drafts to label from.")] = "mark",
    yes: Annotated[bool, typer.Option("--yes", help="Skip the Proceed? prompt.")] = False,
) -> None:
    """Calibrate the quality gate's grader against your own grades (R16).

    With --label: show items from the drafts one at a time and record your pass/fail, until the
    set has enough (gate.min_calibration_items). Without it: run the grader on the set and record
    how often it agrees with you, for the current grader prompt and model.
    """
    from datetime import UTC, datetime

    from thinkbible_pipeline import app as wiring
    from thinkbible_pipeline.gate.calibration import (
        label_items,
        load_calibration,
        run_calibration,
        save_calibration,
    )
    from thinkbible_pipeline.llm.prompts import system_prompt, version_tag
    from thinkbible_pipeline.paths import repo_paths
    from thinkbible_pipeline.sections.passage import passage_text
    from thinkbible_pipeline.stages.review import grade_items

    try:
        request = RunRequest(book=book, stages=["review"])
    except ValidationError as e:
        _usage(e)
    deps = wiring.local_deps(request, echo=typer.echo)
    path = repo_paths().calibration
    calibration = load_calibration(path)
    entries = {e.id: e for e in deps.store.read_section_map()}
    code = request.book_info.code

    if label:
        drafts = {sid: d for sid in entries if (d := deps.store.read_draft(sid)) and d.section}
        if not drafts:
            _exit(ExitCode.USAGE, f"no generated sections for {code} yet: run generate first")
        passages = {sid: passage_text(deps.sources, "bsb", code, entries[sid]) for sid in drafts}
        target = deps.settings.gate.min_calibration_items
        n = label_items(
            calibration, drafts, passages, target=target,
            save=lambda c: save_calibration(path, c), echo=typer.echo, ask=input,
        )  # fmt: skip
        typer.echo(f"labelled {n} this time; the set has {len(calibration.items)} of {target}")
        typer.echo("next: `thinkbible-pipeline calibrate` to measure the grader's agreement")
        _exit(ExitCode.OK)

    if not calibration.items:
        _exit(ExitCode.USAGE, "the calibration set is empty: run `calibrate --label` first")
    tests = [c for c in calibration.items if c.role == "test"]
    if not tests:
        _exit(ExitCode.USAGE, "the calibration set has no held-out (test) items to measure")
    sections = sorted({c.section_id for c in tests})
    cost = len(sections) * deps.settings.stage("review").default_cost_usd
    examples = len(calibration.items) - len(tests)
    typer.echo(f"calibrate: grade {len(tests)} held-out items in {len(sections)} sections, "
               f"about ${cost:.2f} ({examples} more are examples in the grader's "
               "prompt)")  # fmt: skip
    if not yes and not typer.confirm("Proceed?", default=False):
        _exit(ExitCode.OK, "not run")

    async def grade(sid: str, items: list[dict[str, Any]]) -> dict[str, int]:
        if sid not in entries:
            typer.echo(f"  {sid} is no longer in sections.json; its items are skipped", err=True)
            return {}
        draft = deps.store.read_draft_or_new(sid)
        # The ideas the grader can see: the draft's, the labelled ones, and those the labelled
        # questions aim at (kept with each item, so a regenerated section still grades).
        known: dict[str, dict[str, Any]] = {i["id"]: i for i in draft.section.get("keyIdeas", [])}
        for c in calibration.items:
            if c.section_id != sid:
                continue
            if c.kind == "keyIdea":
                known[c.item_id] = c.item
            for idea in c.target_ideas:
                known.setdefault(idea["id"], idea)
        section = {"keyIdeas": list(known.values())}
        grades, _usage = await grade_items(entries[sid], section, list(items), deps)
        return {i: g.score for i, g in grades.items()}

    review = system_prompt("review", deps.settings)
    version, model = version_tag(review.versions), deps.settings.stage("review").model
    result = asyncio.run(
        run_calibration(
            calibration, grade, threshold=deps.settings.review_flag_threshold,
            prompt_version=version, model=model,
            now=datetime.now(UTC).isoformat(timespec="seconds"),
        )
    )  # fmt: skip
    save_calibration(path, calibration)
    gate = deps.settings.gate
    ok = result.agreement >= gate.min_agreement and result.items >= gate.min_calibration_items
    typer.echo(f"grader agreement {result.agreement:.0%} on {result.items} items "
               f"(needs {gate.min_agreement:.0%} on {gate.min_calibration_items})")  # fmt: skip
    for item_id in result.disagreements:
        typer.echo(f"  disagrees on {item_id}")
    typer.echo(
        "commit pipeline/evals/calibration.json"
        if ok
        else "below the bar: adjust prompts/review (a new version) and run `calibrate` again"
    )
    _exit(ExitCode.OK)


@app.command("eval")
def eval_(
    sample: Annotated[str, typer.Option(help="Sample set, e.g. mark-sample.")],
    candidate: Annotated[str, typer.Option(help="Candidate prompt set.")],
    yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    """Compare a candidate prompt set with the current one on a fixed sample."""
    _not_implemented("eval")
