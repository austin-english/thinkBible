import pytest
from pydantic import ValidationError

from thinkbible_pipeline.requests import STAGE_ORDER, PublishRequest, RunRequest


def test_cloud_json_matches_cli_contract() -> None:
    req = RunRequest.model_validate_json(
        '{"book":"mark","stages":["all"],"capUsd":20,"autoApprove":true}'
    )
    assert req.stages == list(STAGE_ORDER)
    assert req.cap_usd == 20
    assert req.auto_approve is True
    assert req.book_info.code == "MRK"
    assert req.env == "dev"


def test_cli_style_values() -> None:
    req = RunRequest(book="MRK", stages="generate,summaries", sections="mrk-1-1, mrk-1-9")  # type: ignore[arg-type]
    # Stages always run in pipeline order.
    assert req.stages == ["summaries", "generate"]
    assert req.sections == ["mrk-1-1", "mrk-1-9"]


def test_all_expands_without_duplicates() -> None:
    req = RunRequest(book="mark", stages=["generate", "all"])
    assert req.stages == list(STAGE_ORDER)


@pytest.mark.parametrize(
    "payload",
    [
        '{"book":"mark","stages":["generat"]}',
        '{"book":"narnia","stages":["all"]}',
        '{"book":"mark","stages":[]}',
        '{"book":"mark","stages":["all"],"capUsd":0}',
        '{"book":"mark","stages":["all"],"env":"staging"}',
        '{"book":"mark","stages":["all"],"bogus":1}',
    ],
)
def test_rejects_bad_requests(payload: str) -> None:
    with pytest.raises(ValidationError):
        RunRequest.model_validate_json(payload)


def test_publish_request_aliases() -> None:
    req = PublishRequest.model_validate_json('{"book":"mark","env":"prod","dryRun":true}')
    assert req.dry_run is True
    assert req.env == "prod"
