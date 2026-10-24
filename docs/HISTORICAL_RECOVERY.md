# Historical corrections and recovery

The default incremental order mart reprocesses the last seven days. An older
source correction needs an explicit repair. The new, validated half-open window
includes that history alongside the ordinary daily window:

```bash
dbt run --profiles-dir . --select +fct_orders --vars '{"backfill_start":"2024-01-01","backfill_end":"2024-02-01"}'
```

Supply both ISO dates; the end is exclusive. Missing/reversed/invalid dates fail
compilation. Bound the window, reconcile the result and review the release
evidence before promotion. The command does not identify historical corrections
automatically, capture hard source deletions, or update an absent source record.
Use source CDC or a separately controlled full rebuild for those requirements.

`python governance/recovery_drill.py` executes real dbt commands in a temporary
copy: establish the mart; correct a record older than its watermark; show the
default window misses it; repair it; replay idempotently; rename a required
source column; prove failure preserves the prior mart; restore the schema; reject
an incomplete request; and compare every repaired row/column with a full rebuild.
The source files and cloud targets are untouched. An initial `dbt deps` is needed.

[Dated execution receipt](../output/recovery_drill.json). CI repeats the drill;
timestamps and timings are observations, so its receipt is not byte-diffed.
