"""
Production-shaped Airflow DAG for the supply-chain dbt project.

Nightly: dbt deps -> seed -> run (staging, then marts) -> test,
with retries, an SLA, and explicit failure surface. The CI pipeline
imports this file with a DagBag and asserts the structure, so a broken
DAG fails the build before it ever reaches a scheduler.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.task_group import TaskGroup

DBT = "dbt --no-use-colors"
PROJECT_FLAGS = "--project-dir /opt/dbt/supply_chain_analytics --profiles-dir /opt/dbt/supply_chain_analytics"

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
    default_args=default_args,
    tags=["dbt", "supply-chain", "analytics-engineering"],
    sla_miss_callback=None,
) as dag:

    dbt_deps = BashOperator(
        task_id="dbt_deps",
        bash_command=f"{DBT} deps {PROJECT_FLAGS}",
    )

    dbt_seed = BashOperator(
        task_id="dbt_seed",
        bash_command=f"{DBT} seed {PROJECT_FLAGS} --full-refresh",
    )

    with TaskGroup(group_id="dbt_run") as dbt_run:
        run_staging = BashOperator(
            task_id="run_staging",
            bash_command=f"{DBT} run {PROJECT_FLAGS} --select staging",
        )
        run_marts = BashOperator(
            task_id="run_marts",
            bash_command=f"{DBT} run {PROJECT_FLAGS} --select marts",
            sla=timedelta(minutes=30),
        )
        run_staging >> run_marts

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"{DBT} test {PROJECT_FLAGS}",
    )

    dbt_deps >> dbt_seed >> dbt_run >> dbt_test
