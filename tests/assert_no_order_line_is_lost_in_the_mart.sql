-- Row-count control between staging and the fact. fct_orders is incremental
-- with a seven-day reprocessing window, so a delete+insert that deleted more
-- than it re-inserted would leave a hole that every other test tolerates:
-- uniqueness still holds on the rows that survived, and so do the ranges.
--
-- Written as a set difference in both directions rather than a count
-- comparison, so the failure names the missing order rather than a number.
select s.order_id, 'missing from fct_orders' as problem
from {{ ref('stg_orders') }} s
left join {{ ref('fct_orders') }} f on s.order_id = f.order_id
where f.order_id is null

union all

select f.order_id, 'in fct_orders but not staging' as problem
from {{ ref('fct_orders') }} f
left join {{ ref('stg_orders') }} s on f.order_id = s.order_id
where s.order_id is null
