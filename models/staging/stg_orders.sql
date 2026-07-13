with source as (
    select * from {{ ref('raw_fact_orders') }}
)

select
    order_id,
    cast(order_date as date)    as order_date,
    customer_id,
    product_id,
    lot_id,
    warehouse_id,
    qty_ordered,
    qty_shipped,
    cast(promised_date as date) as promised_date,
    cast(shipped_date as date)  as shipped_date,
    unit_price,
    unit_cost
from source
