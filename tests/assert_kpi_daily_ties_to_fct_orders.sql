-- The daily rollup is the only thing an executive trend page reads, and it is
-- a second computation of numbers that already exist. Recompute it from the
-- fact and require every day to agree: order count, revenue, margin, and the
-- OTIF rate. A group-by that silently drops or duplicates a day shows up here
-- and nowhere else -- kpi_daily's own uniqueness test is satisfied either way.
with recomputed as (
    select
        order_date,
        count(*)                                  as orders,
        sum(revenue)                              as revenue,
        sum(gross_margin)                         as gross_margin,
        round(sum(otif_flag) * 1.0 / count(*), 4) as otif_rate
    from {{ ref('fct_orders') }}
    group by order_date
)

select
    k.order_date,
    k.orders,
    r.orders   as recomputed_orders,
    k.revenue,
    r.revenue  as recomputed_revenue
from {{ ref('kpi_daily') }} k
full outer join recomputed r on k.order_date = r.order_date
where k.order_date is null
   or r.order_date is null
   or k.orders       <> r.orders
   or abs(k.revenue      - r.revenue)      > 0.01
   or abs(k.gross_margin - r.gross_margin) > 0.01
   or abs(k.otif_rate    - r.otif_rate)    > 0.0001
