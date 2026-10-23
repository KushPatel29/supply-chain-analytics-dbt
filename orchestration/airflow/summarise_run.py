"""Turn the Airflow CLI's JSON for one DAG run into the summary CI records.

Usage: python summarise_run.py '<dags list-runs json>' '<tasks states-for-dag-run json>'
"""

import json
import sys
from datetime import datetime


def _seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    return round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds(), 1)


def main(runs_json: str, tasks_json: str) -> dict:
    run = json.loads(runs_json)[0]
    tasks = json.loads(tasks_json)
    return {
        "dag_id": run["dag_id"],
        "run_id": run["run_id"],
        "created_by": "scheduler" if run["run_id"].startswith("scheduled__") else "other",
        "logical_date": run.get("execution_date") or run.get("logical_date"),
        "state": run["state"],
        "started": run.get("start_date"),
        "ended": run.get("end_date"),
        "seconds": _seconds(run.get("start_date"), run.get("end_date")),
        "tasks": sorted(
            (
                {
                    "task_id": t["task_id"],
                    "state": t["state"],
                    "started": t.get("start_date"),
                    "ended": t.get("end_date"),
                    "seconds": _seconds(t.get("start_date"), t.get("end_date")),
                }
                for t in tasks
            ),
            key=lambda t: t["started"] or "",
        ),
    }


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), indent=2))
