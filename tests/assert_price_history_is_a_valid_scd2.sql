-- SCD Type 2 correctness for the price history.
--
-- Three ways a snapshot goes wrong, none of which any generic test can see:
-- a product with two rows open at once, a validity window that ends before it
-- starts, and two windows for the same product that overlap. All three make
-- an as-of join return more rows than it should, which reads downstream as
-- inflated revenue rather than as a broken dimension.
--
-- With static seeds each product currently has one open version, so today
-- this guards the shape rather than a change that has happened. It earns its
-- place the first time procurement reprices a SKU and the snapshot runs again.
with open_versions as (
    select product_id, count(*) as n
    from {{ ref('product_price_snapshot') }}
    where dbt_valid_to is null
    group by product_id
    having count(*) <> 1
),

backwards as (
    select product_id, 1 as n
    from {{ ref('product_price_snapshot') }}
    where dbt_valid_to is not null
      and dbt_valid_to < dbt_valid_from
),

overlapping as (
    select a.product_id, 1 as n
    from {{ ref('product_price_snapshot') }} a
    join {{ ref('product_price_snapshot') }} b
      on a.product_id = b.product_id
     and a.dbt_scd_id <> b.dbt_scd_id
    where a.dbt_valid_from < coalesce(b.dbt_valid_to, timestamp '9999-12-31')
      and b.dbt_valid_from < coalesce(a.dbt_valid_to, timestamp '9999-12-31')
),

every_product_has_history as (
    select p.product_id, 1 as n
    from {{ ref('stg_products') }} p
    left join {{ ref('product_price_snapshot') }} s on p.product_id = s.product_id
    where s.product_id is null
)

select product_id, n from open_versions
union all select product_id, n from backwards
union all select product_id, n from overlapping
union all select product_id, n from every_product_has_history
