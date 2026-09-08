"""What the documents say about Airflow must match what CI does with it.

The portfolio site claimed for weeks that CI "actually executes" this DAG and
that it "is executed in CI rather than described". It never has: the job below
installs Airflow and loads the DAG through a DagBag, which proves it imports and
has the right task graph, and stops there. Validating a DAG and running one are
different claims, and the stronger one was on the surface a reviewer reads first.

So the claim is pinned to the mechanism. If a real task execution is ever added,
this fails and asks for the prose to be upgraded with it — which is the right
direction for that failure to point.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
README = ROOT / "README.md"


def test_ci_validates_the_dag_and_does_not_run_it():
    ci = WORKFLOW.read_text(encoding="utf-8")
    assert "test_dag_integrity.py" in ci, "the DagBag integrity test is no longer run in CI"

    # `airflow tasks test` / `airflow dags test` / `airflow dags backfill` are the
    # commands that would actually execute something. None should be here while
    # the documents describe validation only.
    executing = re.findall(r"airflow\s+(?:tasks|dags)\s+(?:test|backfill|trigger|run)", ci)
    assert not executing, (
        f"CI now executes the DAG ({executing}). That is a stronger and better claim than "
        "the README and the portfolio site currently make - update their wording to match, "
        "then relax this test."
    )


def test_the_readme_claims_validation_rather_than_execution():
    prose = README.read_text(encoding="utf-8")
    assert "imports the DAG with a DagBag" in prose, (
        "the README no longer describes the DagBag import; say what CI does with the DAG"
    )
    # "orchestrated nightly" sat on a badge here and read as a running schedule.
    # Badge text is URL-encoded, so the spaces arrive as %20 -- checking only the
    # human-readable form let the badge keep the overclaim through a mutation
    # test of this very assertion. Both spellings are checked.
    overclaims = ["orchestrated nightly", "CI actually runs", "CI actually executes",
                  "executed in CI rather than described"]
    flat = prose.replace("%20", " ")
    for overclaim in overclaims:
        assert overclaim not in flat, (
            f"README claims {overclaim!r}, but CI only imports and inspects the DAG"
        )
