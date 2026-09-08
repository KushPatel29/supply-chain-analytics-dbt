"""
Export the dbt project's own metadata (and the one mart with a grain that
exists nowhere else) to CSV, so downstream tools can query the *modelled
warehouse* — models, tests, lineage — as data.

Reads target/manifest.json, target/run_results.json and target/supply_chain.duckdb
(all produced by `dbt build`) and writes flat CSVs into this folder.

    python exports/build_dbt_metadata.py

Deliberately does NOT export the seeds or the passthrough dims: those are the
same rows as the raw ERP extract and are already published elsewhere.
"""

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TARGET = ROOT / "target"

PKG = "supply_chain_analytics"


def layer_of(node):
    """staging / marts / semantic / seed / snapshot / analysis / test."""
    rt = node["resource_type"]
    if rt in ("seed", "snapshot", "analysis", "test"):
        return rt
    fqn = node.get("fqn", [])
    return fqn[1] if len(fqn) > 2 else "root"


def short(uid, nodes=None):
    """model.supply_chain_analytics.fct_orders -> fct_orders (tests keep their real name)."""
    if nodes and uid in nodes:
        return nodes[uid]["name"]
    return uid.split(".")[-1]


def kind(uid):
    return uid.split(".")[0]


_LAYER_BY_KIND = {"exposure": "exposure", "metric": "semantic", "semantic_model": "semantic"}


def layer_for(uid, nodes):
    """Layer for any DAG node, including the ones that live outside manifest['nodes']."""
    if uid in nodes:
        return layer_of(nodes[uid])
    return _LAYER_BY_KIND.get(kind(uid), kind(uid))


def main():
    import duckdb
    dcon = duckdb.connect(str(TARGET / "supply_chain.duckdb"), read_only=True)
    shape = {}
    for (schema, tbl) in dcon.execute(
            "select table_schema, table_name from information_schema.tables").fetchall():
        n_rows = dcon.execute(f'select count(*) from "{schema}"."{tbl}"').fetchone()[0]
        n_cols = len(dcon.execute(f'describe select * from "{schema}"."{tbl}"').fetchall())
        shape[tbl] = (n_rows, n_cols)

    man = json.loads((TARGET / "manifest.json").read_text(encoding="utf-8"))
    run = json.loads((TARGET / "run_results.json").read_text(encoding="utf-8"))

    nodes = man["nodes"]
    results = {r["unique_id"]: r for r in run["results"]}
    child_map = man["child_map"]
    parent_map = man["parent_map"]
    dbt_version = "dbt " + run["metadata"]["dbt_version"]
    built_at = run["metadata"]["generated_at"][:10]

    # ---------------------------------------------------------------- models
    rows = []
    for uid, n in nodes.items():
        if n["resource_type"] == "test":
            continue
        r = results.get(uid, {})
        n_rows, n_cols = shape.get(n.get("alias") or n["name"], (None, None))
        tests_on = sum(
            1 for t in nodes.values()
            if t["resource_type"] == "test"
            and uid in t.get("depends_on", {}).get("nodes", [])
        )
        rows.append({
            "model_name": n["name"],
            "resource_type": n["resource_type"],
            "layer": layer_of(n),
            "materialization": n.get("config", {}).get("materialized"),
            "incremental_strategy": n.get("config", {}).get("incremental_strategy") or "",
            "description": " ".join((n.get("description") or "").split()),
            "file_path": n["original_file_path"].replace("\\", "/"),
            "parent_count": len(parent_map.get(uid, [])),
            "child_count": len(child_map.get(uid, [])),
            "test_count": tests_on,
            "column_count": n_cols,
            "row_count": n_rows,
            "build_status": r.get("status", ""),
            "execution_seconds": round(r["execution_time"], 4) if r.get("execution_time") is not None else None,
            "dbt_version": dbt_version,
            "built_on": built_at,
        })
    for uid, e in man.get("exposures", {}).items():
        rows.append({
            "model_name": e["name"],
            "resource_type": "exposure",
            "layer": "exposure",
            "materialization": e.get("type", ""),
            "incremental_strategy": "",
            "description": " ".join((e.get("description") or "").split()),
            "file_path": e["original_file_path"].replace("\\", "/"),
            "parent_count": len(parent_map.get(uid, [])),
            "child_count": len(child_map.get(uid, [])),
            "test_count": 0,
            "column_count": None,
            "row_count": None,
            "build_status": "",
            "execution_seconds": None,
            "dbt_version": dbt_version,
            "built_on": built_at,
        })
    for group, uid_and_node in (("semantic_model", man.get("semantic_models", {})),
                                ("metric", man.get("metrics", {}))):
        for uid, sm in uid_and_node.items():
            rows.append({
                "model_name": sm["name"],
                "resource_type": group,
                "layer": "semantic",
                "materialization": sm.get("type", "") if group == "metric" else "",
                "incremental_strategy": "",
                "description": " ".join((sm.get("description") or "").split()),
                "file_path": sm["original_file_path"].replace("\\", "/"),
                "parent_count": len(parent_map.get(uid, [])),
                "child_count": len(child_map.get(uid, [])),
                "test_count": 0,
                "column_count": None,
                "row_count": None,
                "build_status": "",
                "execution_seconds": None,
                "dbt_version": dbt_version,
                "built_on": built_at,
            })
    rows.sort(key=lambda r: (r["layer"], r["model_name"]))
    write(HERE / "models.csv", rows)

    # ----------------------------------------------------------------- tests
    trows = []
    for uid, n in nodes.items():
        if n["resource_type"] != "test":
            continue
        meta = n.get("test_metadata") or {}
        tested = [short(d, nodes) for d in n.get("depends_on", {}).get("nodes", [])]
        r = results.get(uid, {})
        trows.append({
            "test_name": n["name"],
            "test_type": meta.get("name", "singular"),
            "test_style": "generic" if meta else "singular",
            "package": meta.get("namespace") or ("dbt" if meta else "supply_chain_analytics"),
            "model_tested": short(n.get("attached_node") or "", nodes) or (tested[0] if tested else ""),
            "column_tested": n.get("column_name") or "",
            "severity": n.get("config", {}).get("severity", ""),
            "models_referenced": len(tested),
            "status": r.get("status", ""),
            "failures": r.get("failures"),
            "execution_seconds": round(r["execution_time"], 4) if r.get("execution_time") is not None else None,
        })
    trows.sort(key=lambda r: (r["model_tested"], r["test_type"], r["test_name"]))
    write(HERE / "tests.csv", trows)

    # --------------------------------------------------------------- lineage
    lrows = []
    for child, parents in parent_map.items():
        for parent in parents:
            lrows.append({
                "parent": short(parent, nodes),
                "parent_type": kind(parent),
                "parent_layer": layer_for(parent, nodes),
                "child": short(child, nodes),
                "child_type": kind(child),
                "child_layer": layer_for(child, nodes),
            })
    lrows.sort(key=lambda r: (r["parent"], r["child"]))
    write(HERE / "lineage.csv", lrows)

    # ------------------------------------------------------------- kpi_daily
    dcon.execute(
        "COPY (SELECT order_date, orders, ROUND(revenue, 2) AS revenue, "
        "ROUND(gross_margin, 2) AS gross_margin, otif_rate, avg_fill_rate "
        "FROM main.kpi_daily ORDER BY order_date) "
        f"TO '{(HERE / 'kpi_daily.csv').as_posix()}' (HEADER, DELIMITER ',')"
    )
    dcon.close()
    print("wrote kpi_daily.csv")


def write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {path.name}  ({len(rows)} rows)")


if __name__ == "__main__":
    main()
