# Analytics release operations

This runbook turns the repository from a collection of dbt models into a small,
auditable release process. It applies to the local DuckDB target and its fixed,
synthetic seed data.

## Release path

1. Run `dbt deps --profiles-dir .`.
2. Run `dbt build --profiles-dir .` and stop on any model, contract, unit-test,
   or data-test failure.
3. Run `python exports/build_dbt_metadata.py` to flatten the manifest, results,
   lineage and daily KPI mart.
4. Run `pytest governance/test_release_evidence.py -q` to prove the change-impact
   engine, including a mutated-model fan-out case.
5. Run `python governance/build_release_evidence.py`. A `HOLD` decision exits
   non-zero; `APPROVE` writes the integrity-hashed packet, change inventory, release memo
   and run-lineage events under `output/`.

CI performs the same path on every push and pull request.

## Release gates

| Gate | Pass condition | Recovery |
|---|---|---|
| dbt execution | no `error` or `fail` result | inspect the failed node and its parents; do not publish marts |
| KPI contract | `kpi_daily` contract is enforced | align model SQL and declared types deliberately; never weaken the contract to make CI green |
| revenue reconciliation | semantic and executive-mart totals differ by no more than $0.01 | trace `fct_orders → kpi_daily`; check grain and rounding |
| OTIF reconciliation | order-grain ratio and weighted KPI reconstruction differ by no more than 0.0001 | check numerator, denominator and daily weighting |
| discoverability | governed metrics and downstream exposure are present | restore semantic declarations or exposure dependencies |

## Change review

`governance/baseline_state.json` stores stable checksums and parents for
code-controlled dbt nodes. The release builder compares the current manifest to
that baseline, labels additions/modifications/removals, and traverses the dbt
child graph to identify downstream impact. Review `output/change_impact.csv`
before approval. Refresh the baseline only in the same reviewed change that
intentionally accepts the new model state:

```bash
python governance/build_release_evidence.py --write-baseline
```

## Rollback and incident handling

- Keep the last green commit deployable. If a release fails, revert the model
  change through normal version control and rebuild; do not edit generated
  artifacts by hand.
- Treat a reconciliation failure as a data-product incident even when SQL
  completes successfully. The executive mart is not publishable until the
  governed definition ties out.
- The Airflow DAG is imported and structurally tested in CI. Scheduling,
  credentials, alerts and SLA operations require a real Airflow environment.
- The Snowflake target is configuration evidence only. Warehouse compatibility
  remains unproven until a Snowflake build runs.

## Evidence inventory

- `output/analytics_engineering_release_packet.json` — gate results, boundaries,
  reconciliations and SHA-256 integrity digest.
- `output/analytics_engineering_release_memo.md` — human review summary.
- `output/change_impact.csv` — node state and downstream impact.
- `output/run_lineage_events.jsonl` — model-run lineage in an OpenLineage-compatible
  evidence shape; this is not a deployed OpenLineage integration.
