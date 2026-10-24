from copy import deepcopy

from governance.build_release_evidence import (
    baseline_payload,
    canonical_sha256,
    change_impact,
    contract_is_enforced,
    descendants,
    semantic_inventory,
    tracked_nodes,
    verify_packet_digest,
)


def sample_manifest():
    return {
        "nodes": {
            "model.p.a": {
                "name": "a",
                "resource_type": "model",
                "checksum": {"checksum": "aaa"},
                "depends_on": {"nodes": []},
            },
            "model.p.b": {
                "name": "b",
                "resource_type": "model",
                "checksum": {"checksum": "bbb"},
                "depends_on": {"nodes": ["model.p.a"]},
            },
        },
        "child_map": {"model.p.a": ["model.p.b"]},
        "metrics": {"metric.p.revenue": {"name": "revenue"}},
        "semantic_models": {"semantic_model.p.orders": {"name": "orders"}},
        "exposures": {"exposure.p.dashboard": {"name": "dashboard"}},
    }


def test_tracked_nodes_are_stable_and_sorted():
    assert list(tracked_nodes(sample_manifest())) == ["model.p.a", "model.p.b"]


def test_descendants_follow_the_manifest_graph():
    assert descendants(sample_manifest(), {"model.p.a"}) == {"model.p.b"}


def test_mutated_checksum_marks_model_and_downstream_impact():
    manifest = sample_manifest()
    baseline = baseline_payload(manifest)
    changed = deepcopy(manifest)
    changed["nodes"]["model.p.a"]["checksum"]["checksum"] = "changed"
    rows, impacted = change_impact(changed, baseline)
    by_id = {row["unique_id"]: row for row in rows}
    assert by_id["model.p.a"]["change_status"] == "modified"
    assert by_id["model.p.b"]["downstream_impact"] == "impacted"
    assert impacted == {"model.p.b"}


def test_added_and_removed_nodes_are_reported():
    manifest = sample_manifest()
    baseline = baseline_payload(manifest)
    changed = deepcopy(manifest)
    changed["nodes"].pop("model.p.b")
    changed["nodes"]["model.p.c"] = {
        "name": "c",
        "resource_type": "model",
        "checksum": {"checksum": "ccc"},
        "depends_on": {"nodes": []},
    }
    rows, _ = change_impact(changed, baseline)
    status = {row["unique_id"]: row["change_status"] for row in rows}
    assert status["model.p.b"] == "removed"
    assert status["model.p.c"] == "added"


def test_packet_digest_is_order_independent():
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})


def test_packet_digest_detects_tampering():
    packet = {"decision": "APPROVE"}
    packet["packet_sha256"] = canonical_sha256(packet)
    assert verify_packet_digest(packet)
    packet["decision"] = "HOLD"
    assert not verify_packet_digest(packet)


def test_semantic_inventory_is_explicit():
    inventory = semantic_inventory(sample_manifest())
    assert inventory == {
        "metrics": ["revenue"],
        "semantic_models": ["orders"],
        "exposures": ["dashboard"],
    }


def test_missing_contract_fails_closed():
    assert contract_is_enforced(sample_manifest(), "kpi_daily") is False
