"""Load ``pipeline/config/{settings,pricing}.toml`` and ``envs/{env}.toml`` as dataclasses."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast

from thinkbible_pipeline.paths import repo_paths

Effort = Literal["low", "medium", "high", "xhigh", "max"]
EFFORTS: tuple[Effort, ...] = ("low", "medium", "high", "xhigh", "max")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class StageSettings:
    model: str
    effort: Effort
    prompt: str
    default_cost_usd: float


@dataclass(frozen=True)
class PromptSettings:
    shared_context: str
    question_guide: str


@dataclass(frozen=True)
class Settings:
    region: str
    concurrency: int
    excerpt_cap_tokens: int
    review_flag_threshold: int
    max_tokens: int
    invalid_output_retries: int
    refusal_fallback_model: str
    prompts: PromptSettings
    stages: Mapping[str, StageSettings]

    def stage(self, name: str) -> StageSettings:
        try:
            return self.stages[name]
        except KeyError:
            raise ConfigError(f"no [stages.{name}] in settings.toml") from None


@dataclass(frozen=True)
class ModelPrice:
    """USD per million tokens."""

    input: float
    output: float
    cache_read: float
    cache_write_5m: float
    cache_write_1h: float


def bare_model_id(model: str) -> str:
    """Strip region and provider prefixes: ``us.anthropic.claude-x`` → ``claude-x``."""
    for prefix in ("us.", "eu.", "apac.", "global."):
        if model.startswith(prefix):
            model = model[len(prefix) :]
            break
    return model.removeprefix("anthropic.")


@dataclass(frozen=True)
class Pricing:
    models: Mapping[str, ModelPrice]

    def for_model(self, model: str) -> ModelPrice:
        try:
            return self.models[bare_model_id(model)]
        except KeyError:
            raise ConfigError(f"no price for model {model!r} in pricing.toml") from None


@dataclass(frozen=True)
class EnvConfig:
    name: str
    region: str
    sources_bucket: str
    packs_bucket: str
    distribution_id: str
    cdn_base_url: str
    # From `terraform output` once infra/modules/pipeline is applied (empty until then).
    drafts_bucket: str
    ledger_table: str
    state_machine_arn: str


def _read(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"missing config file {path}") from None


def _config_dir(config_dir: Path | None) -> Path:
    return config_dir if config_dir is not None else repo_paths().config


def load_settings(config_dir: Path | None = None) -> Settings:
    raw = _read(_config_dir(config_dir) / "settings.toml")
    stages: dict[str, StageSettings] = {}
    for name, s in raw.get("stages", {}).items():
        if s["effort"] not in EFFORTS:
            raise ConfigError(f"stages.{name}.effort must be one of {EFFORTS}")
        stages[name] = StageSettings(
            model=str(s["model"]),
            effort=cast(Effort, s["effort"]),
            prompt=str(s["prompt"]),
            default_cost_usd=float(s["default_cost_usd"]),
        )
    prompts = raw["prompts"]
    return Settings(
        region=str(raw["region"]),
        concurrency=int(raw["concurrency"]),
        excerpt_cap_tokens=int(raw["excerpt_cap_tokens"]),
        review_flag_threshold=int(raw["review_flag_threshold"]),
        max_tokens=int(raw["max_tokens"]),
        invalid_output_retries=int(raw["invalid_output_retries"]),
        refusal_fallback_model=str(raw["refusal_fallback_model"]),
        prompts=PromptSettings(
            shared_context=str(prompts["shared_context"]),
            question_guide=str(prompts["question_guide"]),
        ),
        stages=MappingProxyType(stages),
    )


def load_pricing(config_dir: Path | None = None) -> Pricing:
    raw = _read(_config_dir(config_dir) / "pricing.toml")
    models = {
        model: ModelPrice(
            input=float(p["input"]),
            output=float(p["output"]),
            cache_read=float(p["cache_read"]),
            cache_write_5m=float(p["cache_write_5m"]),
            cache_write_1h=float(p["cache_write_1h"]),
        )
        for model, p in raw.get("models", {}).items()
    }
    return Pricing(models=MappingProxyType(models))


def load_env(name: str, config_dir: Path | None = None) -> EnvConfig:
    raw = _read(_config_dir(config_dir) / "envs" / f"{name}.toml")
    return EnvConfig(
        name=name,
        region=str(raw.get("region", "us-west-2")),
        sources_bucket=str(raw["sources_bucket"]),
        packs_bucket=str(raw["packs_bucket"]),
        distribution_id=str(raw.get("distribution_id", "")),
        cdn_base_url=str(raw.get("cdn_base_url", "")),
        drafts_bucket=str(raw.get("drafts_bucket", "")),
        ledger_table=str(raw.get("ledger_table", "")),
        state_machine_arn=str(raw.get("state_machine_arn", "")),
    )
