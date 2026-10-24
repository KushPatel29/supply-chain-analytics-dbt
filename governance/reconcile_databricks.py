"""Hold the Databricks build to the DuckDB build, mart by mart.

    python governance/reconcile_databricks.py

The same dbt project runs on two engines: DuckDB in CI, and a serverless SQL
warehouse on Databricks Free Edition. A green `dbt build` on each proves the
tests pass on each; it does not prove the two engines produced the same
numbers. This script does: for every mart it compares the row count and the
sum of every numeric column, and writes the comparison to
docs/databricks/reconciliation.csv. Any difference beyond rounding exits 1.

It needs the DuckDB build (`dbt build --profiles-dir .`) and a Databricks
login. It signs in with OAuth in the browser, like the dbt profile, so no
token is read from anywhere:

    export DATABRICKS_HOST=dbc-xxxx.cloud.databricks.com
    export DATABRICKS_WAREHOUSE_ID=<id>
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import duckdb
from databricks.sdk import WorkspaceClient

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "databricks" / "reconciliation.csv"
MARTS = ["dim_customer", "dim_lot", "dim_product", "dim_warehouse", "fct_inventory", "fct_orders", "kpi_daily"]
NUMERIC = ("int", "double", "decimal", "float", "bigint", "hugeint", "smallint", "tinyint")
TOLERANCE = 1e-6


def duck_profile(con, table: str) -> dict[str, float]:
    cols = [(n, t.lower()) for n, t, *_ in con.execute(f"describe main.{table}").fetchall()]
    nums = [n for n, t in cols if t.startswith(NUMERIC)]
    exprs = ", ".join(["count(*)"] + [f"sum({c})" for c in nums])
    row = con.execute(f"select {exprs} from main.{table}").fetchone()
    return dict(zip(["row_count"] + nums, (float(v or 0) for v in row), strict=True))


def dbx_query(w: WorkspaceClient, warehouse: str, sql: str) -> list[list[str]]:
    r = w.statement_execution.execute_statement(warehouse_id=warehouse, statement=sql, wait_timeout="50s")
    if r.status.state.value != "SUCCEEDED":
        raise RuntimeError(f"{sql}: {r.status}")
    return r.result.data_array or []


def dbx_profile(w: WorkspaceClient, warehouse: str, schema: str, table: str, cols: list[str]) -> dict[str, float]:
    exprs = ", ".join(["count(*)"] + [f"sum({c})" for c in cols[1:]])
    row = dbx_query(w, warehouse, f"select {exprs} from {schema}.{table}")[0]
    return dict(zip(cols, (float(v or 0) for v in row), strict=True))


def main() -> int:
    host = os.environ["DATABRICKS_HOST"]
    warehouse = os.environ["DATABRICKS_WAREHOUSE_ID"]
    schema = os.environ.get("DATABRICKS_SCHEMA", "workspace.supply_chain")
    w = WorkspaceClient(host=f"https://{host}", auth_type="external-browser")
    con = duckdb.connect(str(ROOT / "target" / "supply_chain.duckdb"), read_only=True)

    rows, bad = [], 0
    for table in MARTS:
        duck = duck_profile(con, table)
        dbx = dbx_profile(w, warehouse, schema, table, list(duck))
        for measure, d in duck.items():
            b = dbx[measure]
            diff = abs(d - b)
            ok = diff <= TOLERANCE * max(1.0, abs(d))
            bad += not ok
            rows.append({"mart": table, "measure": measure, "duckdb": repr(d), "databricks": repr(b),
                         "abs_diff": f"{diff:.3g}", "match": "yes" if ok else "NO"})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="\n", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        wr.writeheader()
        wr.writerows(rows)
    print(f"{len(rows)} measures across {len(MARTS)} marts; {bad} differ")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
