-- A ratio metric must divide total OTIF orders by total orders. Averaging the
-- already-rounded daily percentages would silently weight a quiet day like a
-- busy one, so both calculations are made explicit here.
with semantic_definition as (
    select sum(otif_flag) * 1.0 / count(*) as otif_rate
    from {{ ref('fct_orders') }}
),
mart_reconstruction as (
    select sum(otif_rate * orders) / sum(orders) as otif_rate
    from {{ ref('kpi_daily') }}
)

select
    semantic_definition.otif_rate as semantic_otif_rate,
    mart_reconstruction.otif_rate as reconstructed_otif_rate
from semantic_definition
cross join mart_reconstruction
where abs(semantic_definition.otif_rate - mart_reconstruction.otif_rate) > 0.0001
