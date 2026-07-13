select
    warehouse_id,
    warehouse_name,
    city,
    region
from {{ ref('raw_dim_warehouse') }}
