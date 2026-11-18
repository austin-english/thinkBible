"""Terraform must allow exactly the models, key and concurrency the pipeline settings use.

The Lambda role may invoke only `bedrock_models` (the models of the `bedrock` profile) and read
only the API key parameter the default settings name; a mismatch fails in the cloud with
AccessDenied. Step Functions runs `max_concurrency` sections at once: keep it at `concurrency`.
"""

import re
from pathlib import Path

from thinkbible_pipeline.config import load_settings

MAIN_TF = Path(__file__).resolve().parents[3] / "infra" / "main.tf"


def test_terraform_matches_settings() -> None:
    settings = load_settings()
    bedrock = load_settings(profile="bedrock")
    text = MAIN_TF.read_text(encoding="utf-8")
    block = re.search(r"bedrock_models\s*=\s*\[(.*?)\]", text, re.S)
    assert block, "infra/main.tf: no bedrock_models list"
    allowed = set(re.findall(r'"([^"]+)"', block.group(1)))
    used = {s.model for s in bedrock.stages.values()} | {bedrock.refusal_fallback_model}
    assert used == allowed, f"the bedrock profile uses {sorted(used)}, IAM allows {sorted(allowed)}"
    concurrency = re.search(r"max_concurrency\s*=\s*(\d+)", text)
    assert concurrency and int(concurrency.group(1)) == settings.concurrency
    key = re.search(r'anthropic_api_key_parameter\s*=\s*"([^"]+)"', text)
    assert key and key.group(1) == settings.api_key_parameter
