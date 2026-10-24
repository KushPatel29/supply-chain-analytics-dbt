with inventory as (
    select * from {{ ref('stg_inventory') }}
),

enriched as (
    select
        i.snapshot_date,
        i.lot_id,
        i.product_id,
        i.warehouse_id,
        i.qty_on_hand,
        {{ dbt.datediff('i.snapshot_date', 'l.expiry_date', 'day') }} as days_until_expiry,
        round(i.qty_on_hand * p.unit_cost, 2) as inventory_value
    from inventory i
    inner join {{ ref('stg_lots') }} l on i.lot_id = l.lot_id
    inner join {{ ref('stg_products') }} p on i.product_id = p.product_id
)

select
    *,
    {{ expiry_band('days_until_expiry') }} as expiry_risk_flag
from enriched
