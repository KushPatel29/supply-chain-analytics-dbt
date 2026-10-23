select
    l.lot_id,
    l.product_id,
    l.supplier_id,
    s.supplier_name,
    l.production_date,
    l.received_date,
    l.expiry_date
from {{ ref('stg_lots') }} l
left join {{ ref('stg_suppliers') }} s
    on l.supplier_id = s.supplier_id
