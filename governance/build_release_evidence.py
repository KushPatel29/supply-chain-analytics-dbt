"""Build an auditable analytics-engineering release packet from dbt artifacts.

The packet deliberately distinguishes evidence we execute (DuckDB build,
contracts, reconciliations) from production-shaped examples we only validate
(the Snowflake profile and Airflow DAG).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "target"
OUTPUT = ROOT / "output"
BASELINE = ROOT / "governance" / "baseline_state.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_packet_digest(packet: dict[str, Any]) -> bool:
    content = dict(packet)
    claimed = content.pop("packet_sha256", "")
    return bool(claimed) and claimed == canonical_sha256(content)


def tracked_nodes(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return code-controlled graph nodes and stable checksums."""
    tracked: dict[str, dict[str, Any]] = {}
    for unique_id, node in manifest.get("nodes", {}).items():
        if node.get("resource_type") not in {"model", "snapshot", "seed"}:
            continue
        checksum = node.get("checksum", {}).get("checksum")
        if not checksum:
            checksum = hashlib.sha256(
                str(node.get("raw_code", "")).encode("utf-8")
            ).hexdigest()
        tracked[unique_id] = {
            "name": node.get("name"),
            "resource_type": node.get("resource_type"),
            "checksum": checksum,
            "depends_on": sorted(node.get("depends_on", {}).get("nodes", [])),
        }
    return dict(sorted(tracked.items()))


def baseline_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "purpose": "Committed comparison state for deterministic change-impact analysis",
        "nodes": tracked_nodes(manifest),
    }


def descendants(manifest: dict[str, Any], roots: set[str]) -> set[str]:
    child_map = manifest.get("child_map", {})
    found: set[str] = set()
    queue: deque[str] = deque(sorted(roots))
    while queue:
        parent = queue.popleft()
        for child in child_map.get(parent, []):
            if child not in found and child not in roots:
                found.add(child)
                queue.append(child)
    return found


def change_impact(
    manifest: dict[str, Any], baseline: dict[str, Any]
) -> tuple[list[dict[str, str]], set[str]]:
    current = tracked_nodes(manifest)
    previous = baseline.get("nodes", {})
    changed: set[str] = set()
    rows: list[dict[str, str]] = []
    for unique_id in sorted(set(current) | set(previous)):
        before = previous.get(unique_id)
        after = current.get(unique_id)
        if before is None:
            status = "added"
        elif after is None:
            status = "removed"
        elif before.get("checksum") != after.get("checksum"):
            status = "modified"
        else:
            status = "unchanged"
        if status != "unchanged":
            changed.add(unique_id)
        rows.append(
            {
                "unique_id": unique_id,
                "name": str((after or before or {}).get("name", "")),
                "resource_type": str((after or before or {}).get("resource_type", "")),
                "change_status": status,
                "downstream_impact": "",
            }
        )
    impacted = descendants(manifest, changed)
    for row in rows:
        if row["unique_id"] in impacted:
            row["downstream_impact"] = "impacted"
    return rows, impacted


def result_statuses(run_results: dict[str, Any]) -> dict[str, int]:
    statuses: dict[str, int] = {}
    for result in run_results.get("results", []):
        status = str(result.get("status", "unknown"))
        statuses[status] = statuses.get(status, 0) + 1
    return dict(sorted(statuses.items()))


def contract_is_enforced(manifest: dict[str, Any], model_name: str) -> bool:
    node = manifest.get("nodes", {}).get(f"model.supply_chain_analytics.{model_name}", {})
    return bool(node.get("config", {}).get("contract", {}).get("enforced"))


def semantic_inventory(manifest: dict[str, Any]) -> dict[str, list[str]]:
    metrics = sorted(metric.get("name", "") for metric in manifest.get("metrics", {}).values())
    semantic_models = sorted(
        model.get("name", "") for model in manifest.get("semantic_models", {}).values()
    )
    exposures = sorted(
        exposure.get("name", "") for exposure in manifest.get("exposures", {}).values()
    )
    return {
        "metrics": metrics,
        "semantic_models": semantic_models,
        "exposures": exposures,
    }


def warehouse_evidence(database: Path) -> dict[str, Any]:
    connection = duckdb.connect(str(database), read_only=True)
    row = connection.execute(
        """
        select
            min(order_date), max(order_date), count(*),
            round(sum(revenue), 2), round(sum(gross_margin), 2),
            round(sum(otif_flag) * 1.0 / count(*), 6)
        from main.fct_orders
        """
    ).fetchone()
    kpi = connection.execute(
        """
        select round(sum(revenue), 2), round(sum(gross_margin), 2),
               round(sum(otif_rate * orders) / sum(orders), 6)
        from main.kpi_daily
        """
    ).fetchone()
    snapshot = connection.execute(
        "select min(snapshot_date), max(snapshot_date), count(*) from main.fct_inventory"
    ).fetchone()
    connection.close()
    return {
        "declared_static_dataset_window": {
            "orders_min": str(row[0]),
            "orders_max": str(row[1]),
            "inventory_min": str(snapshot[0]),
            "inventory_max": str(snapshot[1]),
            "interpretation": "Synthetic, fixed-seed portfolio data; freshness is assessed against this declared window, not wall-clock time.",
        },
        "order_rows": row[2],
        "inventory_rows": snapshot[2],
        "reconciliation": {
            "semantic_total_revenue": row[3],
            "kpi_total_revenue": kpi[0],
            "semantic_total_gross_margin": row[4],
            "kpi_total_gross_margin": kpi[1],
            "semantic_otif_rate": row[5],
            "weighted_kpi_otif_rate": kpi[2],
            "revenue_delta": round(abs(row[3] - kpi[0]), 6),
            "gross_margin_delta": round(abs(row[4] - kpi[1]), 6),
            "otif_delta": round(abs(row[5] - kpi[2]), 6),
        },
    }


def lineage_events(
    manifest: dict[str, Any], run_results: dict[str, Any]
) -> list[dict[str, Any]]:
    nodes = manifest.get("nodes", {})
    invocation_id = run_results.get("metadata", {}).get("invocation_id", "unknown")
    events: list[dict[str, Any]] = []
    for result in run_results.get("results", []):
        unique_id = result.get("unique_id", "")
        node = nodes.get(unique_id, {})
        if node.get("resource_type") != "model":
            continue
        inputs = []
        for parent_id in node.get("depends_on", {}).get("nodes", []):
            parent = nodes.get(parent_id, {})
            if parent.get("resource_type") in {"model", "seed", "snapshot"}:
                inputs.append(parent_id)
        events.append(
            {
                "eventType": "COMPLETE" if result.get("status") == "success" else "FAIL",
                "run": {"runId": invocation_id},
                "job": {"namespace": "supply-chain-analytics-dbt", "name": unique_id},
                "inputs": [{"namespace": "dbt", "name": item} for item in sorted(inputs)],
                "outputs": [{"namespace": "duckdb", "name": node.get("relation_name", unique_id)}],
                "facets": {
                    "dbt": {
                        "status": result.get("status"),
                        "execution_time_seconds": result.get("execution_time"),
                    }
                },
                "compatibility_note": "OpenLineage-compatible evidence shape; not a production OpenLineage backend integration.",
            }
        )
    return events


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fields = ["unique_id", "name", "resource_type", "change_status", "downstream_impact"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_release_packet() -> dict[str, Any]:
    manifest = load_json(TARGET / "manifest.json")
    run_results = load_json(TARGET / "run_results.json")
    baseline = load_json(BASELINE)
    impact_rows, impacted = change_impact(manifest, baseline)
    warehouse = warehouse_evidence(TARGET / "supply_chain.duckdb")
    statuses = result_statuses(run_results)
    semantic = semantic_inventory(manifest)
    reconciliation = warehouse["reconciliation"]
    gates = [
        {
            "gate": "dbt execution",
            "passed": not any(key in statuses for key in ("error", "fail")),
            "evidence": statuses,
        },
        {
            "gate": "enforced KPI contract",
            "passed": contract_is_enforced(manifest, "kpi_daily"),
            "evidence": "model.supply_chain_analytics.kpi_daily",
        },
        {
            "gate": "semantic revenue reconciliation",
            "passed": reconciliation["revenue_delta"] <= 0.01,
            "evidence": reconciliation,
        },
        {
            "gate": "semantic OTIF reconciliation",
            "passed": reconciliation["otif_delta"] <= 0.0001,
            "evidence": reconciliation,
        },
        {
            "gate": "discoverability",
            "passed": bool(semantic["metrics"] and semantic["exposures"]),
            "evidence": semantic,
        },
    ]
    packet: dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "decision": "APPROVE" if all(gate["passed"] for gate in gates) else "HOLD",
        "scope": "Local DuckDB analytics build and committed synthetic dataset",
        "boundaries": [
            "Snowflake target is configured but not executed in CI.",
            "Airflow DAG is imported and structurally tested in CI, not scheduled here.",
            "Lineage events are OpenLineage-compatible evidence, not a deployed backend integration.",
            "Business data is synthetic and fixed-seed; findings demonstrate method, not live operations.",
        ],
        "gates": gates,
        "warehouse": warehouse,
        "change_control": {
            "changed_nodes": sum(row["change_status"] != "unchanged" for row in impact_rows),
            "impacted_downstream_nodes": len(impacted),
            "evidence_command": "python governance/build_release_evidence.py",
        },
        "semantic_layer": semantic,
        "lineage_event_count": len(lineage_events(manifest, run_results)),
    }
    packet["packet_sha256"] = canonical_sha256(packet)
    OUTPUT.mkdir(exist_ok=True)
    write_csv(OUTPUT / "change_impact.csv", impact_rows)
    events = lineage_events(manifest, run_results)
    (OUTPUT / "run_lineage_events.jsonl").write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )
    (OUTPUT / "analytics_engineering_release_packet.json").write_text(
        json.dumps(packet, indent=2) + "\n", encoding="utf-8"
    )
    memo = f"""# Analytics engineering release memo

**Decision:** {packet['decision']}  
**Packet digest:** `{packet['packet_sha256']}`

The DuckDB build passed its executable release gates: dbt execution, an enforced
contract on the executive KPI mart, semantic-to-physical revenue and OTIF
reconciliation, and catalog discoverability through governed metrics plus the
downstream Power BI exposure.

## Evidence at a glance

- {sum(statuses.values())} dbt resources reported in the latest run result ({statuses}).
- {len(semantic['metrics'])} governed metrics and {len(semantic['exposures'])} downstream exposure.
- Revenue reconciliation delta: {reconciliation['revenue_delta']:.2f}.
- OTIF reconciliation delta: {reconciliation['otif_delta']:.6f}.
- {len(events)} model-level run-lineage events emitted.
- {packet['change_control']['changed_nodes']} nodes changed versus the committed baseline; {len(impacted)} downstream nodes identified.

## Evidence boundaries

""" + "\n".join(f"- {item}" for item in packet["boundaries"]) + "\n"
    (OUTPUT / "analytics_engineering_release_memo.md").write_text(memo, encoding="utf-8")
    return packet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Capture the current manifest checksums as the committed comparison state.",
    )
    args = parser.parse_args()
    manifest = load_json(TARGET / "manifest.json")
    if args.write_baseline:
        BASELINE.write_text(
            json.dumps(baseline_payload(manifest), indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote {BASELINE.relative_to(ROOT)}")
        return
    packet = build_release_packet()
    print(f"release decision: {packet['decision']}")
    print(f"packet sha256: {packet['packet_sha256']}")
    if packet["decision"] != "APPROVE":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
