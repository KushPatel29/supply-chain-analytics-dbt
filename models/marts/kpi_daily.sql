-- Daily KPI rollup: the grain an executive trend page reads.
with orders as (
    select * from {{ ref('fct_orders') }}
)

select
    order_date,
    count(*)                                      as orders,
    sum(revenue)                                  as revenue,
    sum(gross_margin)                             as gross_margin,
    round(sum(otif_flag) * 1.0 / count(*), 4)     as otif_rate,
    round(avg(fill_rate), 4)                      as avg_fill_rate
from orders
group by order_date
