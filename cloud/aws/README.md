# The supply-chain seed on AWS

On 24 October 2026 (India time), I ran the existing 20,000-line synthetic
orders seed through **private S3 storage → AWS Glue Data Catalog → Athena**
in a personal free-plan AWS account. This is a dated project execution,
not an employer deployment or a continuously operated pipeline.

[Run receipt](run_receipt.json) records the source commit and checksum,
Athena query ID, SQL, engine, scanned bytes, and returned values. The query
scanned **1,425,165 bytes**. For each of eight warehouses, its row count,
shipped quantity, line-rounded revenue and COGS agree exactly with a separate
Python `Decimal` calculation: **32 of 32 measures**.

## Reproduce

From AWS CloudShell, using the existing console identity:

```bash
python3 cloud/aws/run_demo.py
```

The script creates a uniquely named S3 bucket, a dedicated catalog table and
Athena workgroup. It requires existing S3, Glue Catalog and Athena permissions;
it creates no IAM identity, access key or role. Public access is blocked,
SSE-S3 encryption is explicit, and the workgroup enforces a **10 MiB scan
cutoff**. The source is pinned and limited to 5 MiB; the query is stopped if it
exceeds two minutes. Demo source and result objects expire after seven days;
the empty bucket and catalog/workgroup metadata remain for inspection.

This run does not demonstrate Redshift, Glue ETL jobs/crawlers, IAM design,
cloud-scale performance or AWS production operations. AWS usage may consume
account credits; the script never upgrades the plan or enables recurring jobs.

`governance/test_aws_demo.py` checks the independent arithmetic at the half-cent
boundary and reconciles the recorded Athena output to the committed seed.
