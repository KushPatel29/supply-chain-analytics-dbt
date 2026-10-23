{{
    config(
        materialized='incremental',
        unique_key='order_id',
        incremental_strategy='delete+insert'
    )
}}

with orders as (
    select * from {{ ref('stg_orders') }}

    {% if is_incremental() %}
    -- Reprocess a 7-day window behind the high-water mark so
    -- late-arriving order updates are picked up (delete+insert on
    -- order_id keeps the reload idempotent).
    where order_date > (
        select {{ dbt.dateadd('day', -7, "coalesce(max(order_date), '1900-01-01')") }}
        from {{ this }}
    )
    {% endif %}
)

select
    order_id,
    order_date,
    customer_id,
    product_id,
    lot_id,
    warehouse_id,
    qty_ordered,
    qty_shipped,
    promised_date,
    shipped_date,
    unit_price,
    unit_cost,
    round(qty_shipped * unit_price, 2)               as revenue,
    round(qty_shipped * unit_cost, 2)                as cogs,
    round(qty_shipped * (unit_price - unit_cost), 2) as gross_margin,
    case when qty_ordered = 0 then 0.0
         else round(qty_shipped * 1.0 / qty_ordered, 4) end as fill_rate,
    case
        when shipped_date is not null
         and shipped_date <= promised_date
         and qty_ordered > 0
         and qty_shipped * 1.0 / qty_ordered >= 0.95
        then 1 else 0
    end as otif_flag
from orders
