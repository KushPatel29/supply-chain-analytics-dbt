"""DagBag integrity test — run by CI on Linux with Airflow installed."""

from pathlib import Path

from airflow.models import DagBag


def test_dag_loads_without_errors():
    bag = DagBag(dag_folder=str(Path(__file__).parent), include_examples=False)
    assert not bag.import_errors, bag.import_errors
    assert "supply_chain_dbt_nightly" in bag.dags


def test_dag_structure():
    bag = DagBag(dag_folder=str(Path(__file__).parent), include_examples=False)
    dag = bag.dags["supply_chain_dbt_nightly"]
    task_ids = set(dag.task_ids)
    assert {"dbt_deps", "dbt_seed", "dbt_run.run_staging",
            "dbt_run.run_marts", "dbt_test"} <= task_ids
    # tests are the final quality gate
    assert dag.get_task("dbt_test").downstream_task_ids == set()
    assert "dbt_run.run_marts" in dag.get_task("dbt_test").upstream_task_ids
    assert not dag.catchup
