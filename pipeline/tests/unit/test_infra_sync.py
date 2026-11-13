"""Terraform must allow exactly the models and concurrency the pipeline settings use.

The Lambda role may invoke only `bedrock_models`, so a model added to settings.toml but not to
infra/main.tf would fail in the cloud with AccessDenied.
"""

import re
from pathlib import Path

from thinkbible_pipeline.config import load_settings

MAIN_TF = Path(__file__).resolve().parents[3] / "infra" / "main.tf"


def test_terraform_matches_settings() -> None:
    settings = load_settings()
    text = MAIN_TF.read_text(encoding="utf-8")
    block = re.search(r"bedrock_models\s*=\s*\[(.*?)\]", text, re.S)
    assert block, "infra/main.tf: no bedrock_models list"
    allowed = set(re.findall(r'"([^"]+)"', block.group(1)))
    used = {s.model for s in settings.stages.values()} | {settings.refusal_fallback_model}
    assert used == allowed, f"settings use {sorted(used)}, IAM allows {sorted(allowed)}"
    concurrency = re.search(r"max_concurrency\s*=\s*(\d+)", text)
    assert concurrency and int(concurrency.group(1)) == settings.concurrency
