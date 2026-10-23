"""Hold the Snowflake build to the DuckDB build, mart by mart.

The project runs inside Snowflake with dbt Projects on Snowflake, signed in
through Snowsight, so this script never connects to Snowflake and needs no
credential. It works in two steps around one query:

    python governance/reconcile_snowflake.py sql > totals.sql
        Writes the query: for every mart, the row count and the sum of every
        numeric column, returned as one JSON array. The column list comes from
        the DuckDB build, so both engines are asked the same questions.

    python governance/reconcile_snowflake.py compare docs/snowflake/snowflake_totals.json
        Reads what that query returned in Snowsight (saved with its query ID)
        and compares it with the DuckDB build, writing
        docs/snowflake/reconciliation.csv. Any difference beyond rounding exits 1.

Both steps need the DuckDB build (`dbt build --profiles-dir .`).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "snowflake" / "reconciliation.csv"
MARTS = ["dim_customer", "dim_lot", "dim_product", "dim_warehouse", "fct_inventory", "fct_orders", "kpi_daily"]
NUMERIC = ("int", "double", "decimal", "float", "bigint", "hugeint", "smallint", "tinyint")
SCHEMA = "SUPPLY_CHAIN.ANALYTICS"
TOLERANCE = 1e-6


def duck_profile(con, table: str) -> dict[str, float]:
    cols = [(n, t.lower()) for n, t, *_ in con.execute(f"describe main.{table}").fetchall()]
    nums = [n for n, t in cols if t.startswith(NUMERIC)]
    exprs = ", ".join(["count(*)"] + [f"sum({c})" for c in nums])
    row = con.execute(f"select {exprs} from main.{table}").fetchone()
    return dict(zip(["row_count"] + nums, (float(v or 0) for v in row), strict=True))


def duck() -> dict[str, dict[str, float]]:
    con = duckdb.connect(str(ROOT / "target" / "supply_chain.duckdb"), read_only=True)
    return {t: duck_profile(con, t) for t in MARTS}


def snowflake_sql(profiles: dict[str, dict[str, float]]) -> str:
    parts = []
    for table, measures in profiles.items():
        for m in measures:
            expr = "count(*)" if m == "row_count" else f"sum({m})"
            parts.append(f"select '{table}' as mart, '{m}' as measure, to_varchar({expr}) as value "
                         f"from {SCHEMA}.{table.upper()}")
    union = "\n  union all ".join(parts)
    return ("select to_json(array_agg(object_construct('mart', mart, 'measure', measure, 'value', value))\n"
            "         within group (order by mart, measure)) as totals\n"
            f"from (\n  {union}\n);\n")


def compare(profiles: dict[str, dict[str, float]], snow: list[dict]) -> tuple[list[dict], int]:
    got = {(r["mart"], r["measure"]): float(r["value"] or 0) for r in snow}
    rows, bad = [], 0
    for table, measures in profiles.items():
        for measure, d in measures.items():
            s = got.get((table, measure))
            diff = abs(d - s) if s is not None else float("inf")
            ok = diff <= TOLERANCE * max(1.0, abs(d))
            bad += not ok
            rows.append({"mart": table, "measure": measure, "duckdb": repr(d),
                         "snowflake": repr(s) if s is not None else "missing",
                         "abs_diff": f"{diff:.3g}", "match": "yes" if ok else "NO"})
    return rows, bad


def main(argv: list[str]) -> int:
    if argv[:1] == ["sql"]:
        sys.stdout.write(snowflake_sql(duck()))
        return 0
    if len(argv) == 2 and argv[0] == "compare":
        record = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        rows, bad = compare(duck(), record["totals"])
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", newline="\n", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
            wr.writeheader()
            wr.writerows(rows)
        print(f"{len(rows)} measures across {len(MARTS)} marts; {bad} differ")
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
