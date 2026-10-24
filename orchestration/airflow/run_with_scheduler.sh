#!/usr/bin/env bash
# Run the nightly DAG the way Airflow runs it: a real scheduler, a metadata
# database, the DAG unpaused, and the run created by the scheduler itself from
# the DAG's schedule (catchup=False makes it schedule the latest interval).
# Nothing here runs the DAG in-process or triggers a run by hand.
#
# Needs: AIRFLOW_HOME, DBT_BIN, DBT_PROJECT_DIR. Writes $AIRFLOW_HOME/run_summary.json
# and exits non-zero unless the scheduled run and every task in it succeeded.
set -euo pipefail

DAG_ID=supply_chain_dbt_nightly
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-1200}"

export AIRFLOW__CORE__DAGS_FOLDER="$HERE"
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=True
export AIRFLOW__SCHEDULER__MIN_FILE_PROCESS_INTERVAL=5
export AIRFLOW__SCHEDULER__DAG_DIR_LIST_INTERVAL=5
export AIRFLOW__EMAIL__EMAIL_BACKEND=airflow.utils.email.send_email_smtp
export AIRFLOW__SMTP__SMTP_HOST=localhost

# The CLI prints log lines to stdout; keep them out of the JSON it returns.
cli() { AIRFLOW__LOGGING__LOGGING_LEVEL=ERROR airflow "$@" 2>/dev/null; }
json_of() { python -c 'import sys; t=sys.stdin.read(); print(t[t.index("["):t.rindex("]")+1] if "[" in t else "[]")'; }

airflow db migrate > "$AIRFLOW_HOME/db_migrate.log" 2>&1
airflow dags reserialize > /dev/null 2>&1 || true

airflow scheduler > "$AIRFLOW_HOME/scheduler.log" 2>&1 &
SCHEDULER_PID=$!
trap 'kill $SCHEDULER_PID 2>/dev/null || true' EXIT

# Wait until the scheduler has parsed the DAG, then unpause it.
for _ in $(seq 1 60); do
  if cli dags list -o plain | grep -q "$DAG_ID"; then break; fi
  sleep 2
done
cli dags unpause "$DAG_ID" > /dev/null

start=$(date +%s)
state=""
while :; do
  runs=$(cli dags list-runs -d "$DAG_ID" -o json | json_of)
  state=$(python -c 'import json,sys; r=json.loads(sys.argv[1] or "[]"); print(r[0]["state"] if r else "")' "$runs")
  if [ "$state" = "success" ] || [ "$state" = "failed" ]; then break; fi
  if [ $(( $(date +%s) - start )) -gt "$TIMEOUT_SECONDS" ]; then echo "timed out in state '$state'"; break; fi
  sleep 10
done

run_id=$(python -c 'import json,sys; r=json.loads(sys.argv[1]); print(r[0]["run_id"])' "$runs")
tasks=$(cli tasks states-for-dag-run "$DAG_ID" "$run_id" -o json | json_of)
python "$HERE/summarise_run.py" "$runs" "$tasks" > "$AIRFLOW_HOME/run_summary.json"
cat "$AIRFLOW_HOME/run_summary.json"
case "$run_id" in scheduled__*) ;; *) echo "run $run_id was not created by the scheduler"; exit 1 ;; esac
[ "$state" = "success" ]
