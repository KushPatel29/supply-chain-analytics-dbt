"""Execute real dbt late-correction, bad-schema and recovery drills in a copy.

Never changes the working project's seeds, database or cloud targets.
Run after dbt deps: python governance/recovery_drill.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[1]


def fingerprint(folder: Path) -> str:
    with duckdb.connect(str(folder / "target/supply_chain.duckdb"), read_only=True) as con:
        rows = con.execute("select * from fct_orders order by order_id").fetchall()
    return hashlib.sha256(json.dumps(rows, default=str).encode()).hexdigest()


def drill() -> dict:
    if not (ROOT / "dbt_packages/dbt_utils").is_dir():
        raise RuntimeError("Run dbt deps --profiles-dir . first")
    commands = []
    checks = {}
    with tempfile.TemporaryDirectory(prefix="dbt-recovery-") as temp:
        folder = Path(temp)
        for name in ("models", "macros", "seeds", "dbt_packages"):
            shutil.copytree(ROOT / name, folder / name)
        for name in ("dbt_project.yml", "profiles.yml", "packages.yml", "package-lock.yml"):
            shutil.copy2(ROOT / name, folder / name)

        def run(*args: str, succeeds: bool = True) -> subprocess.CompletedProcess:
            env = dict(os.environ, DBT_SEND_ANONYMOUS_USAGE_STATS="false", NO_COLOR="1")
            result = subprocess.run(
                [sys.executable, "-m", "dbt.cli.main", *args, "--profiles-dir", "."],
                cwd=folder, env=env, text=True, capture_output=True, timeout=180,
            )
            commands.append({"args": list(args), "returncode": result.returncode})
            if (result.returncode == 0) != succeeds:
                raise AssertionError(f"Unexpected dbt outcome for {args}:\n{result.stdout[-4500:]}\n{result.stderr[-1000:]}")
            if succeeds and args[0] == "run" and not (folder / "target/run_results.json").is_file():
                raise AssertionError("dbt did not actually execute")
            return result

        seed = folder / "seeds/raw_fact_orders.csv"
        with seed.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames
            records = list(reader)

        def write(records_to_write, columns=fields):
            with seed.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                writer.writerows(records_to_write)

        run("seed", "--select", "raw_fact_orders")
        run("run", "--select", "+fct_orders", "--full-refresh")
        initial = fingerprint(folder)
        oldest = min(records, key=lambda row: row["order_date"])
        latest = max(date.fromisoformat(row["order_date"]) for row in records)
        start = date.fromisoformat(oldest["order_date"])
        if latest - start <= timedelta(days=7):
            raise AssertionError("Fixture does not exercise an older-than-window correction")
        oldest["unit_price"] = str(float(oldest["unit_price"]) + 5)
        write(records)
        run("seed", "--select", "raw_fact_orders", "--full-refresh")
        run("run", "--select", "+fct_orders")
        checks["old_correction_outside_default_window_detected"] = fingerprint(folder) == initial
        window = json.dumps({"backfill_start": str(start), "backfill_end": str(start + timedelta(days=1))})
        run("run", "--select", "+fct_orders", "--vars", window)
        repaired = fingerprint(folder)
        checks["historical_backfill_changed_old_record"] = repaired != initial
        run("run", "--select", "+fct_orders", "--vars", window)
        checks["backfill_is_idempotent"] = fingerprint(folder) == repaired

        # A renamed required field fails the real staging SQL; the last mart survives.
        renamed = [{("order_date_broken" if k == "order_date" else k): v for k, v in row.items()} for row in records]
        write(renamed, ["order_date_broken" if k == "order_date" else k for k in fields])
        run("seed", "--select", "raw_fact_orders", "--full-refresh")
        run("run", "--select", "+fct_orders", succeeds=False)
        checks["breaking_schema_rejected_and_mart_preserved"] = fingerprint(folder) == repaired
        write(records)
        run("seed", "--select", "raw_fact_orders", "--full-refresh")
        run("run", "--select", "+fct_orders", "--vars", window)
        checks["schema_recovery_restored_same_mart"] = fingerprint(folder) == repaired
        run("run", "--select", "+fct_orders", "--vars", '{"backfill_start":"2024-01-01"}', succeeds=False)
        checks["incomplete_backfill_request_rejected"] = fingerprint(folder) == repaired

        # Full recomputation is the reference for every column, not just a count.
        run("run", "--select", "+fct_orders", "--full-refresh")
        checks["repaired_incremental_equals_full_rebuild"] = fingerprint(folder) == repaired
    if not all(checks.values()):
        raise AssertionError(checks)
    return {"schema_version": 1, "executed_at_utc": datetime.now(UTC).isoformat(),
            "environment": "temporary local DuckDB; actual dbt subprocesses",
            "boundary": "No cloud deployment, source deletion capture or production SLA is claimed.",
            "checks": checks, "commands": commands, "all_checks_passed": True}


if __name__ == "__main__":
    receipt = drill()
    output = ROOT / "output/recovery_drill.json"
    output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt["checks"], indent=2))
