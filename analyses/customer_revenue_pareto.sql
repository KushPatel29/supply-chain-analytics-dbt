-- Which customers concentrate revenue? (classic 80/20 check —
-- compiled by dbt, run ad hoc)
with by_customer as (
    select
        c.customer_name,
        sum(o.revenue) as revenue
    from {{ ref('fct_orders') }} o
    join {{ ref('dim_customer') }} c using (customer_id)
    group by 1
)

select
    customer_name,
    revenue,
    round(100.0 * revenue / sum(revenue) over (), 2)                          as pct_of_total,
    round(100.0 * sum(revenue) over (order by revenue desc) / sum(revenue) over (), 2) as running_pct
from by_customer
order by revenue desc
