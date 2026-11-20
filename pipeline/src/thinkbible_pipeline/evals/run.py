"""``eval``: is a candidate prompt set at least as good as the current one? (T083, FR-029)

A **candidate** is a settings overlay in ``pipeline/evals/candidates/{name}.toml`` that names only
what it changes (a stage's prompt version, the question guide, a setting). A **sample** is a fixed
list of sections in ``pipeline/evals/{name}.json``.

1. **Current arm**: the sample's drafts as they are, when they were generated and graded with the
   current settings (free). Otherwise, or with ``fresh_current``, it is generated again like the
   candidate.
2. **Candidate arm**, ``repeats`` times: ``generate``, ``align`` and ``check`` with the candidate's
   settings, then ``review`` with the **current** settings, so every arm is graded by the same
   calibrated grader. A candidate may not change the ``review`` stage; a grader change is
   checked with ``calibrate``.
3. Each arm runs in its own scratch store (``LocalBlobStore``), seeded with the section map and
   the summaries the writer reads. The real drafts are only read, never written.

The comparison (``evals/report.py``) uses the gate's measures of what readers get, and a candidate
is adopted only if it does at least as well on each (FR-029). Never run in CI: it costs money.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from thinkbible_pipeline.config import Settings, load_settings
from thinkbible_pipeline.drafts.models import SectionDraft
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.llm.prompts import system_prompt, version_tag
from thinkbible_pipeline.paths import repo_paths
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.stages.base import Deps, RunResult, run
from thinkbible_pipeline.storage import LocalBlobStore

WRITER_STAGES = ["generate", "align", "check"]
GRADER_STAGES = ["review"]


class EvalError(Exception):
    pass


@dataclass(frozen=True)
class Sample:
    name: str
    book: str
    sections: list[str]


@dataclass
class Arm:
    """One set of drafts for the sample: the current settings, or one run of the candidate."""

    label: str
    drafts: dict[str, SectionDraft]
    cost_usd: float = 0.0
    failures: dict[str, str] = field(default_factory=dict)


def evals_dir() -> Path:
    return repo_paths().calibration.parent  # pipeline/evals/


def load_sample(name: str, root: Path | None = None) -> Sample:
    path = (root or evals_dir()) / f"{name}.json"
    if not path.is_file():
        raise EvalError(f"no sample {name!r} at {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Sample(name=name, book=str(raw["book"]), sections=[str(s) for s in raw["sections"]])


def load_candidate(name: str, root: Path | None = None) -> dict[str, Any]:
    path = (root or evals_dir()) / "candidates" / f"{name}.toml"
    if not path.is_file():
        raise EvalError(f"no candidate {name!r} at {path}")
    overlay = tomllib.loads(path.read_text(encoding="utf-8"))
    if "review" in overlay.get("stages", {}):
        raise EvalError(
            f"candidate {name!r} changes the review stage: eval grades every arm with the current "
            "grader, so check a grader change with `calibrate` instead"
        )
    return overlay


def writer_version(settings: Settings) -> str:
    from thinkbible_pipeline.stages.generate import GenerateStage

    deps_like = _settings_only(settings)
    return GenerateStage().prompt_version(deps_like)


def grader_version(settings: Settings) -> str:
    return version_tag(system_prompt("review", settings).versions)


def _settings_only(settings: Settings) -> Any:
    """Enough of ``Deps`` for a stage's ``prompt_version`` (it only reads the settings)."""

    @dataclass
    class _D:
        settings: Settings

    return _D(settings)


def current_arm(
    real: DraftStore, sample: Sample, settings: Settings
) -> tuple[Arm | None, list[str]]:
    """The sample's existing drafts, if all were written and graded with ``settings``."""
    want_writer, want_grader = writer_version(settings), grader_version(settings)
    drafts: dict[str, SectionDraft] = {}
    stale: list[str] = []
    for sid in sample.sections:
        draft = real.read_draft(sid)
        gen = draft.stages.get("generate") if draft else None
        rev = draft.stages.get("review") if draft else None
        if (
            draft is None
            or gen is None
            or gen.prompt_version != want_writer
            or rev is None
            or rev.prompt_version != want_grader
        ):
            stale.append(sid)
        else:
            drafts[sid] = draft
    return (Arm("current", drafts) if not stale else None), stale


def scratch_store(real: DraftStore, sample: Sample, root: Path) -> DraftStore:
    """An empty store with the real section map and the summaries the writer reads."""
    store = DraftStore(real.book, LocalBlobStore(root))
    entries = real.read_section_map()
    store.write_section_map(entries)
    ids = [e.id for e in entries]
    wanted = {ids[ids.index(s) - 1] for s in sample.sections if s in ids and ids.index(s) > 0}
    for sid in wanted:
        draft = real.read_draft(sid)
        if draft is not None and draft.summary:
            store.write_draft(sid, SectionDraft(summary=draft.summary))
    return store


async def generate_arm(
    label: str,
    real: DraftStore,
    sample: Sample,
    root: Path,
    *,
    writer: Settings,
    grader: Settings,
    deps_for: Callable[[DraftStore, Settings], Deps],
) -> Arm:
    """One fresh run of the sample: written with ``writer``, graded with ``grader``."""
    store = scratch_store(real, sample, root)
    results: list[RunResult] = []
    for stages, settings in ((WRITER_STAGES, writer), (GRADER_STAGES, grader)):
        request = RunRequest(book=sample.book, stages=stages, sections=sample.sections,
                             fresh=True, auto_approve=True, publish=False)  # fmt: skip
        results.append(await run(request, deps_for(store, settings)))
    drafts = {sid: d for sid in sample.sections if (d := store.read_draft(sid)) is not None}
    arm = Arm(label, drafts)
    for result in results:
        for stage in result.stages:
            arm.cost_usd += stage.spent_usd
            arm.failures.update({sid: f"{stage.stage}: {e}" for sid, e in stage.failures.items()})
        if result.error:
            arm.failures["run"] = result.error
    return arm


def candidate_settings(overlay: dict[str, Any]) -> Settings:
    return load_settings(overlay=overlay)


def cost_per_section(settings: Settings) -> float:
    """The estimate for one sample section in one generated arm."""
    return sum(
        settings.stages[s].default_cost_usd
        for s in WRITER_STAGES + GRADER_STAGES
        if s in settings.stages
    )


@dataclass
class EvalPlan:
    """What ``eval`` will generate, and about what it costs, before anything runs."""

    sample: Sample
    current: Arm | None  # reused as-is (free), or None when it must be generated
    stale: list[str]  # sections whose drafts don't match the current settings
    labels: list[str]  # the arms to generate, in order
    cost_usd: float


def plan_eval(
    real: DraftStore,
    sample: Sample,
    current: Settings,
    candidate: Settings,
    *,
    repeats: int = 1,
    fresh_current: bool = False,
) -> EvalPlan:
    if repeats < 1:
        raise EvalError("--repeats must be at least 1")
    arm, stale = (
        (None, list(sample.sections)) if fresh_current else current_arm(real, sample, current)
    )
    labels = ([] if arm else ["current"]) + [
        "candidate" if repeats == 1 else f"candidate {i}" for i in range(1, repeats + 1)
    ]
    n = len(sample.sections)
    cost = (0 if arm else n * cost_per_section(current)) + repeats * n * cost_per_section(candidate)
    return EvalPlan(sample, arm, stale, labels, cost)


async def run_eval(
    plan: EvalPlan,
    real: DraftStore,
    root: Path,
    *,
    current: Settings,
    candidate: Settings,
    deps_for: Callable[[DraftStore, Settings], Deps],
    echo: Callable[[str], None] = lambda _m: None,
) -> tuple[Arm, list[Arm]]:
    """The current arm and the candidate's runs. Arms run one after another, each in its own
    folder under ``root``, so a stop part-way leaves the finished ones to look at."""
    arms: dict[str, Arm] = {}
    for label in plan.labels:
        echo(f"eval: {label} ({len(plan.sample.sections)} sections)")
        writer = current if label == "current" else candidate
        folder = root / label.replace(" ", "-")
        arms[label] = await generate_arm(label, real, plan.sample, folder, writer=writer,
                                         grader=current, deps_for=deps_for)  # fmt: skip
    base = plan.current or arms.pop("current")
    return base, list(arms.values())
