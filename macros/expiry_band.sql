{% macro expiry_band(days_col) %}
    case
        when {{ days_col }} <= 2 then 'Critical'
        when {{ days_col }} <= 5 then 'Warning'
        else 'OK'
    end
{% endmacro %}
