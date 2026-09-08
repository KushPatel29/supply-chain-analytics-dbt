-- Inventory value is quantity times the product's unit cost, and it is the
-- number a write-down decision is made on. The join that supplies that cost
-- is an inner join on product_id: if it ever matched the wrong product, every
-- value here would still be positive, non-null and in range.
select
    i.snapshot_date,
    i.lot_id,
    i.inventory_value,
    round(i.qty_on_hand * p.unit_cost, 2) as expected_value
from {{ ref('fct_inventory') }} i
join {{ ref('dim_product') }} p on i.product_id = p.product_id
where abs(i.inventory_value - round(i.qty_on_hand * p.unit_cost, 2)) > 0.01
