"""Versioned prompt files (``pipeline/prompts/``) assembled into system blocks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from anthropic.types.beta import BetaTextBlockParam

from thinkbible_pipeline.config import Settings
from thinkbible_pipeline.paths import repo_paths

SHARED_CONTEXT = "_shared/context"
QUESTION_GUIDE = "question-guide"


class PromptNotFound(FileNotFoundError):
    pass


@dataclass(frozen=True)
class SystemPrompt:
    blocks: list[BetaTextBlockParam]
    # Recorded with every run and stage record, e.g. {"generate": "v1", "_shared/context": "v1"}.
    versions: dict[str, str] = field(default_factory=dict)


def load_prompt(name: str, version: str, prompts_dir: Path | None = None) -> str:
    """Read ``{prompts_dir}/{name}/{version}.md``.

    ``_shared/context`` is special: version v1 reads ``_shared/context-v1.md``.
    """
    root = prompts_dir or repo_paths().prompts
    if name == SHARED_CONTEXT:
        path = root / "_shared" / f"context-{version}.md"
    else:
        path = root / name / f"{version}.md"
    if not path.is_file():
        raise PromptNotFound(f"prompt {name} {version} not found at {path}")
    return path.read_text(encoding="utf-8").strip()


def system_prompt(
    stage: str,
    settings: Settings,
    *,
    with_question_guide: bool = False,
    prompts_dir: Path | None = None,
) -> SystemPrompt:
    """Shared context first, then the stage prompt, then (optionally) the question guide.

    All three are stable across sections, so the runner caches them as one prefix.
    """
    shared_v = settings.prompts.shared_context
    stage_v = settings.stage(stage).prompt
    parts = [
        load_prompt(SHARED_CONTEXT, shared_v, prompts_dir),
        load_prompt(stage, stage_v, prompts_dir),
    ]
    versions = {SHARED_CONTEXT: shared_v, stage: stage_v}
    if with_question_guide:
        guide_v = settings.prompts.question_guide
        parts.append(load_prompt(QUESTION_GUIDE, guide_v, prompts_dir))
        versions[QUESTION_GUIDE] = guide_v
    blocks: list[BetaTextBlockParam] = [{"type": "text", "text": p} for p in parts]
    return SystemPrompt(blocks=blocks, versions=versions)


def version_tag(versions: dict[str, str]) -> str:
    """One string for the stage record, e.g. ``_shared/context@v1+generate@v1``."""
    return "+".join(f"{k}@{v}" for k, v in sorted(versions.items()))
