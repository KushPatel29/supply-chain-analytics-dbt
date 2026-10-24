{% snapshot product_price_snapshot %}

{{
    config(
        unique_key='product_id',
        strategy='check',
        check_cols=['unit_cost', 'unit_price'],
    )
}}

-- SCD Type 2 history of product cost/price: when procurement reprices
-- a SKU, the old row is end-dated instead of overwritten, so margin
-- can be recomputed as-of any order date.
select
    product_id,
    sku,
    product_name,
    unit_cost,
    unit_price
from {{ ref('stg_products') }}

{% endsnapshot %}
