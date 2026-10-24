select
    supplier_id,
    supplier_name,
    region
from {{ ref('raw_dim_supplier') }}
