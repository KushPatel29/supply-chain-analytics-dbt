# Containerized build: `docker build -t sca-dbt . && docker run --rm sca-dbt`
# runs the full dbt build (seed + run + snapshot + test) on DuckDB inside
# the container. CI does exactly this on every push.
FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir dbt-duckdb

COPY . .
RUN dbt deps --profiles-dir .

ENTRYPOINT ["dbt"]
CMD ["build", "--profiles-dir", "."]
