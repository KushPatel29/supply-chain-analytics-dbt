"""Execute a small, private S3 -> Glue Catalog -> Athena reconciliation.

Run from AWS CloudShell with its existing credentials. Creates no IAM identity,
key, crawler, cluster, recurring job, or public endpoint. No production claim.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

SOURCE_COMMIT = "6991b8f4973eca3c90c971945e11c9466080d741"
SOURCE_URL = f"https://raw.githubusercontent.com/KushPatel29/supply-chain-analytics-dbt/{SOURCE_COMMIT}/seeds/raw_fact_orders.csv"
REGION = "us-east-1"
DATABASE = "portfolio_supply_chain_demo"
WORKGROUP = "portfolio_supply_chain_demo"
SCAN_LIMIT = 10 * 1024 * 1024
MAX_SOURCE_BYTES = 5 * 1024 * 1024
CENT = Decimal("0.01")

def expected_totals(data: bytes) -> list[dict]:
    groups = {}
    for row in csv.DictReader(io.StringIO(data.decode("utf-8-sig"))):
        warehouse = int(row["warehouse_id"])
        group = groups.setdefault(warehouse, {"warehouse_id": warehouse, "lines": 0, "qty_shipped": Decimal(0), "revenue": Decimal(0), "cogs": Decimal(0)})
        qty = Decimal(row["qty_shipped"] or "0")
        group["lines"] += 1
        group["qty_shipped"] += qty
        group["revenue"] += (qty * Decimal(row["unit_price"])).quantize(CENT, rounding=ROUND_HALF_UP)
        group["cogs"] += (qty * Decimal(row["unit_cost"])).quantize(CENT, rounding=ROUND_HALF_UP)
    return [{**g, "qty_shipped": str(g["qty_shipped"].quantize(CENT)), "revenue": str(g["revenue"].quantize(CENT)), "cogs": str(g["cogs"].quantize(CENT))} for _, g in sorted(groups.items())]

def main():
    import boto3
    from botocore.exceptions import ClientError
    with urllib.request.urlopen(SOURCE_URL, timeout=30) as response:
        data = response.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise RuntimeError("Source exceeds the bounded demo budget")
    expected = expected_totals(data)
    session = boto3.Session(region_name=REGION)
    s3, glue, athena = (session.client(name) for name in ("s3", "glue", "athena"))
    bucket = "kush-supply-chain-demo-" + uuid.uuid4().hex[:12]
    s3.create_bucket(Bucket=bucket)
    s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={"BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    s3.put_bucket_encryption(Bucket=bucket, ServerSideEncryptionConfiguration={"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]})
    s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": [{"Key": "Purpose", "Value": "synthetic-portfolio-demo"}]})
    s3.put_bucket_lifecycle_configuration(Bucket=bucket, LifecycleConfiguration={"Rules": [{"ID": "expire-disposable-demo", "Status": "Enabled", "Filter": {"Prefix": "demo/"}, "Expiration": {"Days": 7}}]})
    s3.put_object(Bucket=bucket, Key="demo/source/orders.csv", Body=data, ContentType="text/csv", ServerSideEncryption="AES256")
    try:
        glue.create_database(DatabaseInput={"Name": DATABASE, "Description": "Synthetic supply-chain portfolio run; not production"})
    except glue.exceptions.AlreadyExistsException:
        pass
    table = "orders_" + uuid.uuid4().hex[:8]
    fields = next(csv.reader(io.StringIO(data.decode("utf-8-sig")))); assert len(fields) == 12
    glue.create_table(DatabaseName=DATABASE, TableInput={"Name": table, "TableType": "EXTERNAL_TABLE", "Parameters": {"classification": "csv", "skip.header.line.count": "1"}, "StorageDescriptor": {"Columns": [{"Name": field, "Type": "string"} for field in fields], "Location": f"s3://{bucket}/demo/source/", "InputFormat": "org.apache.hadoop.mapred.TextInputFormat", "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat", "SerdeInfo": {"SerializationLibrary": "org.apache.hadoop.hive.serde2.OpenCSVSerde", "Parameters": {"separatorChar": ",", "quoteChar": '"', "escapeChar": "\\"}}}})
    config = {"EnforceWorkGroupConfiguration": True, "BytesScannedCutoffPerQuery": SCAN_LIMIT, "PublishCloudWatchMetricsEnabled": True, "ResultConfiguration": {"OutputLocation": f"s3://{bucket}/demo/results/", "EncryptionConfiguration": {"EncryptionOption": "SSE_S3"}}}
    try:
        athena.create_work_group(Name=WORKGROUP, Configuration=config, Description="Bounded synthetic portfolio query; 10 MiB scan cutoff")
    except ClientError as error:
        if error.response["Error"]["Code"] != "InvalidRequestException" or "already exists" not in str(error).lower(): raise
        athena.update_work_group(WorkGroup=WORKGROUP, ConfigurationUpdates=config)
    sql = f'''SELECT CAST(warehouse_id AS integer) AS warehouse_id, COUNT(*) AS lines,
      CAST(SUM(COALESCE(TRY_CAST(qty_shipped AS decimal(18,2)), 0)) AS decimal(18,2)) AS qty_shipped,
      CAST(SUM(ROUND(COALESCE(TRY_CAST(qty_shipped AS decimal(18,4)),0) * CAST(unit_price AS decimal(18,4)),2)) AS decimal(18,2)) AS revenue,
      CAST(SUM(ROUND(COALESCE(TRY_CAST(qty_shipped AS decimal(18,4)),0) * CAST(unit_cost AS decimal(18,4)),2)) AS decimal(18,2)) AS cogs
      FROM "{DATABASE}"."{table}" GROUP BY 1 ORDER BY 1'''
    query_id = athena.start_query_execution(QueryString=sql, WorkGroup=WORKGROUP)["QueryExecutionId"]
    deadline = time.monotonic() + 120
    while True:
        execution = athena.get_query_execution(QueryExecutionId=query_id)["QueryExecution"]
        state = execution["Status"]["State"]
        if state in {"SUCCEEDED", "FAILED", "CANCELLED"}: break
        if time.monotonic() > deadline:
            athena.stop_query_execution(QueryExecutionId=query_id)
            raise RuntimeError("Demo query exceeded two minutes; stopped it")
        time.sleep(2)
    if state != "SUCCEEDED": raise RuntimeError(json.dumps(execution["Status"]))
    rows = athena.get_query_results(QueryExecutionId=query_id)["ResultSet"]["Rows"]
    columns = [cell["VarCharValue"] for cell in rows[0]["Data"]]
    actual = [dict(zip(columns, [cell.get("VarCharValue", "") for cell in row["Data"]])) for row in rows[1:]]
    for row in actual:
        row["warehouse_id"], row["lines"] = int(row["warehouse_id"]), int(row["lines"])
    if actual != expected: raise AssertionError({"actual": actual, "expected": expected})
    receipt = {"run_at": datetime.now(timezone.utc).isoformat(), "boundary": "Personal AWS free-plan project; synthetic seed; one bounded run, not production. Private demo objects expire after seven days.", "region": REGION, "services_executed": ["S3", "AWS Glue Data Catalog", "Athena"], "source_commit": SOURCE_COMMIT, "source_url": SOURCE_URL, "source_sha256": hashlib.sha256(data).hexdigest(), "source_bytes": len(data), "rows": sum(row["lines"] for row in actual), "warehouse_groups": len(actual), "query_execution_id": query_id, "query_state": state, "bytes_scanned": execution["Statistics"]["DataScannedInBytes"], "scan_cutoff_bytes": SCAN_LIMIT, "engine": execution.get("EngineVersion"), "s3_block_public_access": s3.get_public_access_block(Bucket=bucket)["PublicAccessBlockConfiguration"], "s3_encryption": "AES256", "reconciliation": {"status": "PASS", "method": "Athena decimal aggregates compared to independent Python Decimal row arithmetic in every warehouse", "measures_per_warehouse": 4, "actual": actual}, "sql": sql}
    Path("aws_run_receipt.json").write_text(json.dumps(receipt, indent=2)+"\n")
    print("PORTFOLIO_AWS_RECEIPT="+json.dumps(receipt, separators=(",", ":")), flush=True)

if __name__ == "__main__": main()
