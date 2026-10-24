{% macro validated_backfill_window() %}
    {# Validate even on full-refresh: a misspelled request must not silently pass. #}
    {% set start = var('backfill_start', none) %}
    {% set end = var('backfill_end', none) %}
    {% if (start is none) != (end is none) %}
        {{ exceptions.raise_compiler_error('backfill_start and backfill_end must be supplied together') }}
    {% endif %}
    {% if start is not none %}
        {% if start is not string or end is not string
              or not modules.re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}', start)
              or not modules.re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}', end) %}
            {{ exceptions.raise_compiler_error('backfill dates must be ISO YYYY-MM-DD strings') }}
        {% endif %}
        {% set start_date = modules.datetime.datetime.strptime(start, '%Y-%m-%d') %}
        {% set end_date = modules.datetime.datetime.strptime(end, '%Y-%m-%d') %}
        {% if start_date >= end_date %}
            {{ exceptions.raise_compiler_error('backfill_start must precede exclusive backfill_end') }}
        {% endif %}
    {% endif %}
    {{ return({'start': start, 'end': end}) }}
{% endmacro %}
