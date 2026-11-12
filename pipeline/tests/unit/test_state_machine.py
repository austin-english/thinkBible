"""The state machine template (infra/modules/pipeline/state_machine.asl.json.tftpl) is wired up
right."""

import json
import re
from pathlib import Path
from typing import Any

from thinkbible_pipeline.cloud import handlers
from thinkbible_pipeline.config import load_settings

ASL = (
    Path(__file__).resolve().parents[3]
    / "infra"
    / "modules"
    / "pipeline"
    / "state_machine.asl.json.tftpl"
)
FUNCTIONS = {"start_run", "plan_stage", "run_section", "finish_stage", "finish_run"}


def render(max_concurrency: int = 10) -> dict[str, Any]:
    """Fill the Terraform template variables the way `templatefile` does."""
    text = ASL.read_text(encoding="utf-8")
    variables = set(re.findall(r"\$\{(\w+)\}", text))
    assert variables == {f"{f}_arn" for f in FUNCTIONS} | {"max_concurrency"}
    text = text.replace("${max_concurrency}", str(max_concurrency))
    for f in FUNCTIONS:
        text = text.replace(f"${{{f}_arn}}", f"arn:aws:lambda:us-west-2:1:function:{f}")
    doc: dict[str, Any] = json.loads(text)
    return doc


def _states(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name, state in doc["States"].items():
        out[name] = state
        if state["Type"] == "Map":
            out.update(_states(state["ItemProcessor"]))
    return out


def test_tasks_call_exactly_the_five_handlers() -> None:
    states = _states(render())
    called = {
        s["Parameters"]["FunctionName"].rsplit(":", 1)[1]
        for s in states.values()
        if s["Type"] == "Task"
    }
    assert called == FUNCTIONS
    # Every function the state machine calls exists in cloud/handlers.py (Terraform maps
    # function name → module attribute, with "_handler" for the two that clash with step names).
    for f in FUNCTIONS:
        attr = f if hasattr(handlers, f) else f"{f}_handler"
        assert callable(getattr(handlers, attr)), f


def test_stages_in_order_sections_in_parallel() -> None:
    states = _states(render(max_concurrency=load_settings().concurrency))
    assert states["Stages"]["MaxConcurrency"] == 1
    assert states["Stages"]["ItemsPath"] == "$.request.stages"
    assert states["Sections"]["MaxConcurrency"] == load_settings().concurrency
    assert states["Sections"]["ItemsPath"] == "$.sectionIds"


def test_throttling_retried_and_checksum_fails_cleanly() -> None:
    states = _states(render())
    retries = states["RunSection"]["Retry"]
    assert retries[0]["ErrorEquals"] == ["Throttled"]
    assert retries[0]["MaxAttempts"] >= 3
    catch = states["StartRun"]["Catch"][0]
    assert catch["ErrorEquals"] == [handlers.SourceChecksumError.__name__]
    assert states[catch["Next"]]["Type"] == "Fail"
    assert states[catch["Next"]]["Error"] == "SourceChecksum"  # app.wait_for_execution maps → 2


def test_payload_keys_match_the_handler_messages() -> None:
    states = _states(render())
    for name in ("Stages", "Sections"):
        selector = states[name]["ItemSelector"]
        assert {"runId.$", "request.$", "capUsd.$"} <= set(selector)
    assert "sectionId.$" in states["Sections"]["ItemSelector"]
    assert states["Sections"]["ResultPath"] == "$.outcomes"
    assert states["Stages"]["ResultPath"] == "$.stageResults"
