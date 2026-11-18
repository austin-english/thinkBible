"""Load ``pipeline/config/{settings,pricing,aws}.toml`` as dataclasses."""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast

from thinkbible_pipeline.paths import repo_paths

Effort = Literal["low", "medium", "high", "xhigh", "max"]
EFFORTS: tuple[Effort, ...] = ("low", "medium", "high", "xhigh", "max")
Thinking = Literal["adaptive", "none"]
Endpoint = Literal["runtime", "mantle", "anthropic"]
ENDPOINTS: tuple[Endpoint, ...] = ("runtime", "mantle", "anthropic")
# Picks a [profiles.NAME] overlay in settings.toml, e.g. THINKBIBLE_PROFILE=anthropic.
PROFILE_ENV = "THINKBIBLE_PROFILE"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class StageSettings:
    model: str
    prompt: str
    default_cost_usd: float
    thinking: Thinking = "none"
    effort: Effort | None = None  # None: send no effort (models such as Haiku 4.5 reject it)
    # The account's Bedrock requests-per-minute quota for this stage's model. The runner paces
    # requests to stay under it; stages sharing a model share the budget. None: no pacing.
    requests_per_minute: int | None = None


@dataclass(frozen=True)
class PromptSettings:
    shared_context: str
    question_guide: str


@dataclass(frozen=True)
class GateSettings:
    """When a graded book may be promoted (R16, constitution v1.2.0)."""

    min_idea_pass_rate: float = 0.90
    min_question_pass_rate: float = 0.80
    min_agreement: float = 0.85  # the grader's agreement with the owner's calibration grades
    min_calibration_items: int = 30


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
    # bedrock-runtime, bedrock-mantle, or the Claude API directly ("anthropic")
    endpoint: Endpoint = "runtime"
    # For the "anthropic" endpoint: the SSM Parameter Store SecureString holding the API key
    # (ANTHROPIC_API_KEY in the environment wins). The key itself is never stored in the repo.
    api_key_parameter: str | None = None
    profile: str | None = None  # the [profiles.NAME] overlay in use, if any
    gate: GateSettings = GateSettings()
    # A throttled request (429/503/529) is retried this many times with backoff, then fails.
    throttle_retries: int = 5

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


_VERSION_SUFFIX = re.compile(r"(-\d{8})?(-v\d+(:\d+)?)?$")


def bare_model_id(model: str) -> str:
    """The model's price key: strip region and provider prefixes and Bedrock's version suffix.

    ``us.anthropic.claude-haiku-4-5-20251001-v1:0`` → ``claude-haiku-4-5``;
    ``anthropic.claude-opus-4-6-v1`` → ``claude-opus-4-6``; ``claude-sonnet-5-5`` unchanged.
    """
    for prefix in ("us.", "eu.", "apac.", "global."):
        if model.startswith(prefix):
            model = model[len(prefix) :]
            break
    return _VERSION_SUFFIX.sub("", model.removeprefix("anthropic."))


@dataclass(frozen=True)
class Pricing:
    models: Mapping[str, ModelPrice]

    def for_model(self, model: str) -> ModelPrice:
        try:
            return self.models[bare_model_id(model)]
        except KeyError:
            raise ConfigError(f"no price for model {model!r} in pricing.toml") from None


@dataclass(frozen=True)
class AwsConfig:
    """``pipeline/config/aws.toml``: the one AWS environment (``terraform output`` in infra/)."""

    region: str
    sources_bucket: str
    # The pipeline (empty until infra/ is applied; `run --local` then keeps drafts locally).
    drafts_bucket: str
    ledger_table: str
    state_machine_arn: str
    # Published packs: one bucket with draft/ and live/ channels, one CDN (US3).
    packs_bucket: str
    distribution_id: str
    cdn_base_url: str


def _read(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"missing config file {path}") from None


def _config_dir(config_dir: Path | None) -> Path:
    return config_dir if config_dir is not None else repo_paths().config


def _apply_profile(raw: dict[str, Any], profile: str) -> dict[str, Any]:
    """``raw`` with ``[profiles.<profile>]`` laid over it: top-level keys replace, and each
    ``[profiles.<profile>.stages.<name>]`` table updates that stage's keys."""
    profiles = raw.get("profiles", {})
    if profile not in profiles:
        raise ConfigError(f"no [profiles.{profile}] in settings.toml (known: {sorted(profiles)})")
    overlay = profiles[profile]
    merged = {k: v for k, v in raw.items() if k != "profiles"}
    for key, value in overlay.items():
        if key == "stages":
            stages = {name: dict(s) for name, s in raw.get("stages", {}).items()}
            for name, changes in value.items():
                stages.setdefault(name, {}).update(changes)
            merged["stages"] = stages
        else:
            merged[key] = value
    return merged


def load_settings(config_dir: Path | None = None, profile: str | None = None) -> Settings:
    """``settings.toml``, with the ``[profiles.<profile>]`` overlay if one is named (the
    ``profile`` argument, else the ``THINKBIBLE_PROFILE`` environment variable)."""
    raw = _read(_config_dir(config_dir) / "settings.toml")
    profile = profile or os.environ.get(PROFILE_ENV) or None
    if profile:
        raw = _apply_profile(raw, profile)
    stages: dict[str, StageSettings] = {}
    for name, s in raw.get("stages", {}).items():
        effort = s.get("effort")
        if effort is not None and effort not in EFFORTS:
            raise ConfigError(f"stages.{name}.effort must be one of {EFFORTS}")
        thinking = s.get("thinking", "none")
        if thinking not in ("adaptive", "none"):
            raise ConfigError(f"stages.{name}.thinking must be adaptive or none")
        stages[name] = StageSettings(
            model=str(s["model"]),
            prompt=str(s["prompt"]),
            default_cost_usd=float(s["default_cost_usd"]),
            thinking=cast(Thinking, thinking),
            effort=cast(Effort, effort) if effort is not None else None,
            requests_per_minute=int(s["requests_per_minute"])
            if "requests_per_minute" in s
            else None,
        )
    endpoint = raw.get("endpoint", "runtime")
    if endpoint not in ENDPOINTS:
        raise ConfigError(f"endpoint must be one of {ENDPOINTS}")
    if endpoint == "anthropic" and not raw.get("api_key_parameter"):
        raise ConfigError("the anthropic endpoint needs api_key_parameter")
    prompts = raw["prompts"]
    return Settings(
        region=str(raw["region"]),
        concurrency=int(raw["concurrency"]),
        excerpt_cap_tokens=int(raw["excerpt_cap_tokens"]),
        review_flag_threshold=int(raw["review_flag_threshold"]),
        max_tokens=int(raw["max_tokens"]),
        invalid_output_retries=int(raw["invalid_output_retries"]),
        refusal_fallback_model=str(raw["refusal_fallback_model"]),
        endpoint=cast(Endpoint, endpoint),
        prompts=PromptSettings(
            shared_context=str(prompts["shared_context"]),
            question_guide=str(prompts["question_guide"]),
        ),
        stages=MappingProxyType(stages),
        gate=GateSettings(**{k: v for k, v in raw.get("gate", {}).items()}),
        throttle_retries=int(raw.get("throttle_retries", 5)),
        api_key_parameter=str(raw["api_key_parameter"]) if raw.get("api_key_parameter") else None,
        profile=profile,
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


def load_aws(config_dir: Path | None = None) -> AwsConfig:
    raw = _read(_config_dir(config_dir) / "aws.toml")
    return AwsConfig(
        region=str(raw.get("region", "us-west-2")),
        sources_bucket=str(raw["sources_bucket"]),
        drafts_bucket=str(raw.get("drafts_bucket", "")),
        ledger_table=str(raw.get("ledger_table", "")),
        state_machine_arn=str(raw.get("state_machine_arn", "")),
        packs_bucket=str(raw.get("packs_bucket", "")),
        distribution_id=str(raw.get("distribution_id", "")),
        cdn_base_url=str(raw.get("cdn_base_url", "")),
    )
