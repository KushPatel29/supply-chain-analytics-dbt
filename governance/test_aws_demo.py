"""Hand-calculated money boundaries for the independent Athena judge."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("aws_demo", ROOT / "cloud/aws/run_demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)

def test_decimal_judge_prices_shipped_quantity_and_rounds_each_line():
    csv = b"warehouse_id,qty_shipped,unit_price,unit_cost\n1,0.1,1.05,0.55\n1,0.1,1.05,0.55\n2,,5,3\n"
    assert demo.expected_totals(csv) == [
        {"warehouse_id": 1, "lines": 2, "qty_shipped": "0.20", "revenue": "0.22", "cogs": "0.12"},
        {"warehouse_id": 2, "lines": 1, "qty_shipped": "0.00", "revenue": "0.00", "cogs": "0.00"},
    ]

def test_source_is_pinned_and_within_the_execution_budget():
    data = (ROOT / "seeds/raw_fact_orders.csv").read_bytes()
    assert demo.SOURCE_COMMIT in demo.SOURCE_URL
    assert len(demo.SOURCE_COMMIT) == 40
    assert len(data) <= demo.MAX_SOURCE_BYTES < demo.SCAN_LIMIT
    assert sum(row["lines"] for row in demo.expected_totals(data)) == 20000
