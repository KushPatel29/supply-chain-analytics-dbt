-- Control total: mart revenue must equal revenue recomputed from staging,
-- line-rounded identically on both sides.
with staging_total as (
    select sum(round(qty_shipped * unit_price, 2)) as revenue
    from {{ ref('stg_orders') }}
),

mart_total as (
    select sum(revenue) as revenue
    from {{ ref('fct_orders') }}
)

select *
from staging_total s
cross join mart_total m
where abs(s.revenue - m.revenue) > 0.01
