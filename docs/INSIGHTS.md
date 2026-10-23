# Analyst notebook — what the marts actually say

Every number below is reproducible: `dbt build --profiles-dir .`, then run
the queries in [`analyses/`](../analyses/) against `target/supply_chain.duckdb`.
This is the "so what" layer that dashboards alone don't prove you can do.

## Findings (H1 2025, $56.8M revenue, 23.6% gross margin)

**1. Revenue is *not* Pareto-concentrated — that changes the OTIF play.**
It takes 31 of 40 customers to reach 80% of revenue (`customer_revenue_pareto.sql`).
There is no whale to protect; fulfillment improvements must be systemic
(warehouse/process-level), not key-account babysitting. That's the opposite
of the usual 80/20 assumption, and it's exactly why you check.

**2. OTIF averages 80.4% and its floor matters more than its mean.**
The worst day (June 6: 72.8%) is 20+ points below the 95% contract standard.
Averages hide the days that trigger retailer chargebacks — the OTIF gauge on
the Power BI report tracks the daily floor for this reason.

**3. Expiry risk is concentrated, so the fix is cheap.**
"Critical" (≤2 days) inventory value clusters in one site — BC Interior DC 5
(~$823K at risk, `expiry_risk_exposure.sql`). A FEFO pick-priority rule at a
single DC addresses most of the writedown exposure.

**4. Channel margins are flat (23.5–23.7%) — mix shifts won't move margin.**
Wholesale, Foodservice, and Retail earn within 0.2pts of each other, so
"sell more of the profitable channel" isn't a lever here; cost and expiry
waste are.

## Why this file exists

A mart nobody interrogates is furniture. These four findings each changed
what the "right" operational response would be — which is the actual job
of an analyst, after the pipelines and dashboards are built.
