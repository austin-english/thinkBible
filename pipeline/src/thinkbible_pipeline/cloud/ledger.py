"""The spend ledger in DynamoDB: one item per run, shared by every section Lambda (R8, R15).

Spend is added with an atomic ``ADD``, so concurrent sections never lose an update. A section
starts only while ``spentUsd < capUsd`` and the run is still ``running``; sections already in
flight when the cap is crossed finish (SC-008).
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from thinkbible_pipeline.ledger import LedgerError, LedgerState, RunStatus

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient

TTL_DAYS = 90


def _num(value: float) -> str:
    # DynamoDB numbers travel as strings; Decimal keeps cents exact.
    return str(Decimal(str(round(value, 8))))


class DynamoLedger:
    def __init__(self, table: str, client: DynamoDBClient | None = None) -> None:
        if client is None:
            import boto3

            client = boto3.client("dynamodb")
        self.table = table
        self._db = client

    def create(
        self, run_id: str, book: str, cap_usd: float | None, *, execution_arn: str | None = None
    ) -> None:
        item: dict[str, Any] = {
            "runId": {"S": run_id},
            "book": {"S": book},
            "spentUsd": {"N": "0"},
            "status": {"S": "running"},
            "startedAt": {"N": str(int(time.time()))},
            "ttl": {"N": str(int(time.time()) + TTL_DAYS * 86400)},
        }
        if cap_usd is not None:
            item["capUsd"] = {"N": _num(cap_usd)}
        if execution_arn:
            item["executionArn"] = {"S": execution_arn}
        self._db.put_item(TableName=self.table, Item=item)

    def get(self, run_id: str) -> LedgerState | None:
        resp = self._db.get_item(
            TableName=self.table, Key={"runId": {"S": run_id}}, ConsistentRead=True
        )
        item = resp.get("Item")
        if not item:
            return None
        counts = {k: int(v["N"]) for k, v in item.get("counts", {}).get("M", {}).items()}
        return LedgerState(
            run_id=run_id,
            book=item["book"]["S"],
            cap_usd=float(item["capUsd"]["N"]) if "capUsd" in item else None,
            spent_usd=float(item["spentUsd"]["N"]),
            status=item["status"]["S"],  # type: ignore[arg-type]
            counts=counts,
            execution_arn=item.get("executionArn", {}).get("S"),
        )

    def _require(self, run_id: str) -> LedgerState:
        state = self.get(run_id)
        if state is None:
            raise LedgerError(f"no ledger entry for run {run_id}")
        return state

    def can_start(self, run_id: str) -> bool:
        state = self._require(run_id)
        return state.status == "running" and state.under_cap

    def add(self, run_id: str, cost_usd: float) -> None:
        if cost_usd <= 0:
            return
        self._db.update_item(
            TableName=self.table,
            Key={"runId": {"S": run_id}},
            UpdateExpression="ADD spentUsd :c",
            ExpressionAttributeValues={":c": {"N": _num(cost_usd)}},
        )

    def mark_stopped(self, run_id: str) -> None:
        self._db.update_item(
            TableName=self.table,
            Key={"runId": {"S": run_id}},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": {"S": "stopped-cap"}},
        )

    def finish(self, run_id: str, status: RunStatus, counts: dict[str, int]) -> None:
        self._db.update_item(
            TableName=self.table,
            Key={"runId": {"S": run_id}},
            UpdateExpression="SET #s = :s, #c = :c",
            ExpressionAttributeNames={"#s": "status", "#c": "counts"},
            ExpressionAttributeValues={
                ":s": {"S": status},
                ":c": {"M": {k: {"N": str(v)} for k, v in counts.items()}},
            },
        )
