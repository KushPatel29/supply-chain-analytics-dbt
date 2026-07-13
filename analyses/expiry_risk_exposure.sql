-- Dollars sitting in Critical/Warning expiry bands by warehouse:
-- the writedown-avoidance work list.
select
    w.warehouse_name,
    i.expiry_risk_flag,
    sum(i.inventory_value) as value_at_risk
from {{ ref('fct_inventory') }} i
join {{ ref('dim_warehouse') }} w using (warehouse_id)
where i.expiry_risk_flag in ('Critical', 'Warning')
group by 1, 2
order by value_at_risk desc
