select
    warehouse_id,
    warehouse_name,
    city,
    region
from {{ ref('stg_warehouses') }}
