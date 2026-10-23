"""
Production-shaped Airflow DAG for the supply-chain dbt project.

Nightly: dbt deps -> seed -> run staging -> (marts, price snapshot) -> test,
with retries, an SLA, and explicit failure surface. CI imports this file
with a DagBag on every push, and every night a real Airflow scheduler on a
throwaway runner runs it end to end (.github/workflows/airflow-run.yml).
"""

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.task_group import TaskGroup

# Where dbt and the project live. The defaults are the container layout; the CI
# run points them at the checkout and at a dbt installed beside Airflow.
DBT_BIN = os.environ.get("DBT_BIN", "dbt")
DBT_PROJECT_DIR = os.environ.get("DBT_PROJECT_DIR", "/opt/dbt/supply_chain_analytics")
DBT = f"{DBT_BIN} --no-use-colors"
# Every task runs in the project directory. BashOperator otherwise starts each
# task in a fresh temporary directory, and the DuckDB profile's relative path
# (target/supply_chain.duckdb) then pointed somewhere that vanished after each
# task: the first real run failed at dbt_seed with "Cannot open file".
PROJECT_FLAGS = f"--project-dir {DBT_PROJECT_DIR} --profiles-dir {DBT_PROJECT_DIR}"

default_args = {
    "owner": "analytics-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": True,
    "email": ["dharma.patel552@gmail.com"],
}

with DAG(
    dag_id="supply_chain_dbt_nightly",
    description="Nightly build of the supply-chain dbt marts with tests as the quality gate",
    schedule="0 6 * * *",
    start_date=datetime(2026, 7, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["dbt", "supply-chain", "analytics-engineering"],
    sla_miss_callback=None,
) as dag:

    dbt_deps = BashOperator(
        task_id="dbt_deps",
        bash_command=f"{DBT} deps {PROJECT_FLAGS}",
        cwd=DBT_PROJECT_DIR,
    )

    dbt_seed = BashOperator(
        task_id="dbt_seed",
        bash_command=f"{DBT} seed {PROJECT_FLAGS} --full-refresh",
        cwd=DBT_PROJECT_DIR,
    )

    with TaskGroup(group_id="dbt_run") as dbt_run:
        run_staging = BashOperator(
            task_id="run_staging",
            bash_command=f"{DBT} run {PROJECT_FLAGS} --select staging",
            cwd=DBT_PROJECT_DIR,
        )
        run_marts = BashOperator(
            task_id="run_marts",
            bash_command=f"{DBT} run {PROJECT_FLAGS} --select marts",
            cwd=DBT_PROJECT_DIR,
            sla=timedelta(minutes=30),
        )
        # The SCD2 price history. `dbt build` runs snapshots; a DAG that splits
        # run and test has to ask for them, and this one did not: the first
        # scheduled run failed at dbt_test because the snapshot's table did not exist.
        snapshot_prices = BashOperator(
            task_id="snapshot_prices",
            bash_command=f"{DBT} snapshot {PROJECT_FLAGS}",
            cwd=DBT_PROJECT_DIR,
        )
        run_staging >> [run_marts, snapshot_prices]

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"{DBT} test {PROJECT_FLAGS}",
        cwd=DBT_PROJECT_DIR,
    )

    dbt_deps >> dbt_seed >> dbt_run >> dbt_test
