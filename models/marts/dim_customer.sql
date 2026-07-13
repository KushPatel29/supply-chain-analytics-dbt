select
    customer_id,
    customer_name,
    channel,
    region
from {{ ref('stg_customers') }}
