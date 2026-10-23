"""After the scheduler run: every mart and the price snapshot exist and hold rows.

Usage: python check_built_marts.py <duckdb file> <run_summary.json>
Writes marts.json next to the summary and exits non-zero on any failure.
"""

import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_TASKS = {"dbt_deps", "dbt_seed", "dbt_run.run_staging", "dbt_run.run_marts",
                  "dbt_run.snapshot_prices", "dbt_test"}


def main(db_path: str, summary_path: str) -> int:
    summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    problems = []
    if summary["created_by"] != "scheduler":
        problems.append(f"run {summary['run_id']} was not created by the scheduler")
    states = {t["task_id"]: t["state"] for t in summary["tasks"]}
    if set(states) != EXPECTED_TASKS:
        problems.append(f"tasks {sorted(states)} are not the DAG's {sorted(EXPECTED_TASKS)}")
    problems += [f"{t} ended {s}" for t, s in states.items() if s != "success"]

    marts = sorted(p.stem for p in (ROOT / "models" / "marts").glob("*.sql"))
    snapshots = sorted(p.stem for p in (ROOT / "snapshots").glob("*.sql"))
    con = duckdb.connect(db_path, read_only=True)
    rows = {}
    for name in marts + snapshots:
        try:
            rows[name] = con.execute(f'select count(*) from "{name}"').fetchone()[0]
        except duckdb.Error as exc:
            problems.append(f"{name}: {exc}")
            continue
        if rows[name] == 0:
            problems.append(f"{name} is empty")

    out = Path(summary_path).with_name("marts.json")
    out.write_text(json.dumps({"rows": rows, "problems": problems}, indent=2), encoding="utf-8")
    print(json.dumps({"rows": rows, "problems": problems}, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
