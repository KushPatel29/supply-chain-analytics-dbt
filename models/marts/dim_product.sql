select
    product_id,
    sku,
    product_name,
    category,
    subcategory,
    shelf_life_days,
    unit_of_measure,
    unit_cost,
    unit_price
from {{ ref('stg_products') }}
