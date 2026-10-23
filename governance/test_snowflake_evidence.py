"""The Snowflake run is recorded, not repeated in CI. Hold the record to what the README says."""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "docs" / "snowflake"
README = (ROOT / "README.md").read_text(encoding="utf-8")


def summary() -> dict:
    return json.loads((EVIDENCE / "run_summary.json").read_text(encoding="utf-8"))


def test_every_node_passed_on_snowflake():
    s = summary()
    assert s["failures"] == []
    assert all(k.endswith((":success", ":pass", ":no-op")) for k in s["nodes"])
    green = sum(v for k, v in s["nodes"].items() if not k.endswith(":no-op"))
    assert f"{green} of {green} nodes green on Snowflake" in README


def test_the_snowflake_run_covers_every_test_the_badge_counts():
    s = summary()
    ran = s["nodes"].get("test:pass", 0) + s["nodes"].get("unit_test:pass", 0)
    badge = int(re.search(r"dbt%20tests-(\d+)%20across", README).group(1))
    assert ran == badge, "the Snowflake record is from an older version of the project; rerun it"


def test_every_mart_measure_matches_duckdb():
    rows = list(csv.DictReader((EVIDENCE / "reconciliation.csv").open(encoding="utf-8")))
    marts = {r["mart"] for r in rows}
    assert {r["match"] for r in rows} == {"yes"}
    assert f"{len(rows)} of {len(rows)} Snowflake measures across {len(marts)} marts" in README
    assert all(any(r["mart"] == m and r["measure"] == "row_count" for r in rows) for m in marts)


def test_the_reconciliation_is_built_from_the_recorded_query_result():
    record = json.loads((EVIDENCE / "snowflake_totals.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader((EVIDENCE / "reconciliation.csv").open(encoding="utf-8")))
    recorded = {(t["mart"], t["measure"]): float(t["value"]) for t in record["totals"]}
    assert len(recorded) == len(rows)
    for r in rows:
        assert float(r["snowflake"]) == recorded[(r["mart"], r["measure"])]
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", record["query_id"])


def test_the_profile_holds_no_snowflake_credential():
    profile = (ROOT / "profiles.yml").read_text(encoding="utf-8")
    block = profile[profile.index("    snowflake:"):]
    assert "password" not in block and "private_key" not in block and "token" not in block
