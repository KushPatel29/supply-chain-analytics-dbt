-- The governed semantic metric is declared as SUM(fct_orders.revenue).
-- Reconcile that definition to the executive daily mart without requiring a
-- commercial MetricFlow service in this zero-infrastructure project.
with semantic_definition as (
    select round(sum(revenue), 2) as total_revenue
    from {{ ref('fct_orders') }}
),
executive_mart as (
    select round(sum(revenue), 2) as total_revenue
    from {{ ref('kpi_daily') }}
)

select
    semantic_definition.total_revenue as semantic_total_revenue,
    executive_mart.total_revenue as mart_total_revenue
from semantic_definition
cross join executive_mart
where abs(semantic_definition.total_revenue - executive_mart.total_revenue) > 0.01
