-- OTIF rows must actually satisfy the definition: shipped on/before
-- promise AND fill rate >= 95%.
select *
from {{ ref('fct_orders') }}
where otif_flag = 1
  and (
        shipped_date is null
     or shipped_date > promised_date
     or fill_rate < 0.95
  )
