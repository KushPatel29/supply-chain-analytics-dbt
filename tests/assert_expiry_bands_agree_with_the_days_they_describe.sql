-- The bands come from a macro, so this restates the thresholds independently
-- of it against the real data. The unit test pins the macro's boundaries on
-- fixed rows; this catches the macro being changed and the change reaching
-- 7,000 real snapshot rows.
select snapshot_date, lot_id, days_until_expiry, expiry_risk_flag
from {{ ref('fct_inventory') }}
where expiry_risk_flag <> case
        when days_until_expiry <= 2 then 'Critical'
        when days_until_expiry <= 5 then 'Warning'
        else 'OK'
    end
