"""DynamoLedger matches InMemoryLedger: cap check, atomic adds, stop and finish."""

from collections.abc import Iterator

import boto3
import pytest
from moto import mock_aws
from mypy_boto3_dynamodb import DynamoDBClient

from thinkbible_pipeline.cloud.ledger import DynamoLedger
from thinkbible_pipeline.ledger import InMemoryLedger, LedgerError, SpendLedger

TABLE = "thinkbible-pipeline-runs-test"


def create_table(ddb: DynamoDBClient) -> None:
    ddb.create_table(
        TableName=TABLE,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": "runId", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "runId", "KeyType": "HASH"}],
    )


@pytest.fixture(params=["memory", "dynamo"])
def ledger(request: pytest.FixtureRequest) -> Iterator[SpendLedger]:
    if request.param == "memory":
        yield InMemoryLedger()
        return
    with mock_aws():
        ddb = boto3.client("dynamodb", region_name="us-west-2")
        create_table(ddb)
        yield DynamoLedger(TABLE, client=ddb)


def test_cap_and_spend(ledger: SpendLedger) -> None:
    ledger.create("run-1", "mrk", 1.0, execution_arn="arn:aws:states:x")
    assert ledger.can_start("run-1")
    for _ in range(3):
        ledger.add("run-1", 0.25)
    assert ledger.can_start("run-1")  # 0.75 < 1.00
    ledger.add("run-1", 0.25)
    assert not ledger.can_start("run-1")  # 1.00: no new sections
    state = ledger.get("run-1")
    assert state is not None
    assert state.spent_usd == pytest.approx(1.0)
    assert state.book == "mrk" and state.cap_usd == 1.0


def test_no_cap_and_stop(ledger: SpendLedger) -> None:
    ledger.create("run-2", "mrk", None)
    ledger.add("run-2", 50.0)
    assert ledger.can_start("run-2")
    ledger.mark_stopped("run-2")
    assert not ledger.can_start("run-2")


def test_finish_records_counts(ledger: SpendLedger) -> None:
    ledger.create("run-3", "mrk", 2.0)
    ledger.finish("run-3", "succeeded", {"done": 3, "failed": 1})
    state = ledger.get("run-3")
    assert state is not None
    assert state.status == "succeeded" and state.counts == {"done": 3, "failed": 1}


def test_unknown_run(ledger: SpendLedger) -> None:
    assert ledger.get("nope") is None
    with pytest.raises(LedgerError):
        ledger.can_start("nope")
