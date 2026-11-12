"""Terraform must allow exactly the models and concurrency the pipeline settings use.

The Lambda role may invoke only `bedrock_models`, so a model added to settings.toml but not to
infra/envs/*/main.tf would fail in the cloud with AccessDenied.
"""

import re
from pathlib import Path

import pytest

from thinkbible_pipeline.config import load_settings

ENVS = Path(__file__).resolve().parents[3] / "infra" / "envs"


@pytest.mark.parametrize("env_dir", sorted(p for p in ENVS.iterdir() if (p / "main.tf").is_file()))
def test_terraform_matches_settings(env_dir: Path) -> None:
    settings = load_settings()
    text = (env_dir / "main.tf").read_text(encoding="utf-8")
    block = re.search(r"bedrock_models\s*=\s*\[(.*?)\]", text, re.S)
    assert block, f"{env_dir.name}: no bedrock_models list"
    allowed = set(re.findall(r'"([^"]+)"', block.group(1)))
    used = {s.model for s in settings.stages.values()} | {settings.refusal_fallback_model}
    assert used == allowed, (
        f"{env_dir.name}: settings use {sorted(used)}, IAM allows {sorted(allowed)}"
    )
    concurrency = re.search(r"max_concurrency\s*=\s*(\d+)", text)
    assert concurrency and int(concurrency.group(1)) == settings.concurrency
