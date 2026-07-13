with source as (
    select * from {{ ref('raw_fact_inventory_snapshot') }}
)

select
    cast(snapshot_date as date) as snapshot_date,
    lot_id,
    product_id,
    warehouse_id,
    qty_on_hand
from source
