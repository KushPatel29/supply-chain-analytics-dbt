"""The Databricks run is recorded, not repeated in CI. Hold the record to what the README says."""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "docs" / "databricks"
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_every_node_passed_on_databricks():
    s = json.loads((EVIDENCE / "run_summary.json").read_text(encoding="utf-8"))
    assert s["failures"] == []
    assert all(k.endswith((":success", ":pass", ":no-op")) for k in s["nodes"])
    green = sum(v for k, v in s["nodes"].items() if not k.endswith(":no-op"))
    assert f"{green} of {green} nodes green" in README


def test_the_databricks_run_covers_every_test_the_badge_counts():
    s = json.loads((EVIDENCE / "run_summary.json").read_text(encoding="utf-8"))
    ran = s["nodes"].get("test:pass", 0) + s["nodes"].get("unit_test:pass", 0)
    badge = int(re.search(r"dbt%20tests-(\d+)%20across", README).group(1))
    assert ran == badge, "the Databricks record is from an older version of the project; rerun it"


def test_every_mart_measure_matches_duckdb():
    rows = list(csv.DictReader((EVIDENCE / "reconciliation.csv").open(encoding="utf-8")))
    marts = {r["mart"] for r in rows}
    assert {r["match"] for r in rows} == {"yes"}
    assert f"{len(rows)} of {len(rows)} measures across {len(marts)} marts" in README
    assert all(any(r["mart"] == m and r["measure"] == "row_count" for r in rows) for m in marts)
