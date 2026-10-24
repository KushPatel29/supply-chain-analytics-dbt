select
    customer_id,
    customer_name,
    channel,
    region
from {{ ref('raw_dim_customer') }}
