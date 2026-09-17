-- Protect the KPI definition from becoming an unweighted average of averages.
with expected as (
    select
        order_date,
        round(avg(fill_rate), 4) as avg_fill_rate
    from {{ ref('fct_orders') }}
    group by order_date
),
actual as (
    select order_date, avg_fill_rate
    from {{ ref('kpi_daily') }}
)

select
    coalesce(expected.order_date, actual.order_date) as order_date,
    expected.avg_fill_rate as expected_avg_fill_rate,
    actual.avg_fill_rate as actual_avg_fill_rate
from expected
full outer join actual using (order_date)
where expected.order_date is null
   or actual.order_date is null
   or abs(expected.avg_fill_rate - actual.avg_fill_rate) > 0.000001
