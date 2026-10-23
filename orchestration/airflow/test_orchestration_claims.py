"""What the documents say about Airflow must match what CI does with it.

For a long time CI only imported this DAG through a DagBag, and this file held
the documents to that: the portfolio site had once claimed CI "actually
executes" the DAG when it never had. In October 2026 a real run was added
(.github/workflows/airflow-run.yml): Airflow's own scheduler, on a throwaway
runner, creates the run from the DAG's schedule and executes every task. The
first real runs found two defects no import test could (a working directory
that vanished between tasks, and a snapshot the tests needed but no task built).

So the claim is pinned to the new mechanism: the run must come from the
scheduler, not from a hand-triggered `dags test`, and the prose may say the DAG
runs nightly in CI but must not dress that up as a production deployment.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"
RUN = ROOT / ".github" / "workflows" / "airflow-run.yml"
SCRIPT = ROOT / "orchestration" / "airflow" / "run_with_scheduler.sh"
README = ROOT / "README.md"


def test_ci_still_validates_the_dag_on_every_push():
    assert "test_dag_integrity.py" in CI.read_text(encoding="utf-8")


def test_a_real_scheduler_runs_the_dag_every_night():
    run = RUN.read_text(encoding="utf-8")
    assert re.search(r"schedule:\s*\n\s*- cron:", run), "the run is no longer nightly"
    assert "run_with_scheduler.sh" in run and "check_built_marts.py" in run
    script = SCRIPT.read_text(encoding="utf-8")
    assert "airflow scheduler" in script and "dags unpause" in script
    # The point is that the scheduler makes the run. A hand-triggered or
    # in-process run would prove less, so none may creep in.
    shortcut = re.findall(r"\b(?:dags|tasks)\s+(?:test|backfill|trigger|run)\b", script + run)
    assert not shortcut, f"the run no longer comes from the scheduler: {shortcut}"
    assert "created_by" in (ROOT / "orchestration" / "airflow" / "check_built_marts.py").read_text(
        encoding="utf-8"
    )


def test_the_readme_claims_a_ci_run_and_not_production():
    prose = README.read_text(encoding="utf-8")
    flat = prose.replace("%20", " ")
    assert "imports the DAG with a DagBag" in prose
    assert "scheduler" in flat and "runs nightly in CI" in flat
    assert "not a production deployment" in flat
    overclaims = ["in production", "production Airflow", "orchestrated nightly in production",
                  "deployed Airflow", "Airflow cluster"]
    for overclaim in overclaims:
        assert overclaim not in flat, f"README claims {overclaim!r}; CI runs a throwaway scheduler"
