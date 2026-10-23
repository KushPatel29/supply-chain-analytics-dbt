select
    lot_id,
    product_id,
    supplier_id,
    warehouse_id,
    cast(production_date as date) as production_date,
    cast(received_date as date)   as received_date,
    cast(expiry_date as date)     as expiry_date
from {{ ref('raw_dim_lot') }}
