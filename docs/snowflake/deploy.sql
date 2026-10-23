-- Deploy and run this dbt project with dbt Projects on Snowflake.
-- Run in a Snowsight SQL file. Nothing here holds a credential: the
-- repository is public, and the project runs as the signed-in user.

-- 1. One read-only Git integration, limited to this GitHub account (ACCOUNTADMIN).
USE ROLE ACCOUNTADMIN;
CREATE API INTEGRATION IF NOT EXISTS GITHUB_KUSHPATEL29
  API_PROVIDER = git_https_api
  API_ALLOWED_PREFIXES = ('https://github.com/KushPatel29/')
  ENABLED = TRUE
  COMMENT = 'Read-only: public repositories under github.com/KushPatel29, no credentials';
GRANT USAGE ON INTEGRATION GITHUB_KUSHPATEL29 TO ROLE SYSADMIN;

-- 2. Everything else is owned by SYSADMIN, the role the dbt profile uses.
USE ROLE SYSADMIN;
CREATE WAREHOUSE IF NOT EXISTS DBT_WH
  WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE;
USE WAREHOUSE DBT_WH;
CREATE DATABASE IF NOT EXISTS SUPPLY_CHAIN;
CREATE SCHEMA IF NOT EXISTS SUPPLY_CHAIN.DEPLOY;

-- 3. The repository, read from the snowflake-deploy branch: master plus the
--    dbt packages CI installs, because a trial account cannot reach dbt Hub.
CREATE GIT REPOSITORY IF NOT EXISTS SUPPLY_CHAIN.DEPLOY.SUPPLY_CHAIN_ANALYTICS_DBT
  API_INTEGRATION = GITHUB_KUSHPATEL29
  ORIGIN = 'https://github.com/KushPatel29/supply-chain-analytics-dbt.git';
ALTER GIT REPOSITORY SUPPLY_CHAIN.DEPLOY.SUPPLY_CHAIN_ANALYTICS_DBT FETCH;

-- 4. Deploy the project object and build it: seeds, models, snapshot, tests.
CREATE OR REPLACE DBT PROJECT SUPPLY_CHAIN.DEPLOY.SUPPLY_CHAIN_ANALYTICS
  FROM '@SUPPLY_CHAIN.DEPLOY.SUPPLY_CHAIN_ANALYTICS_DBT/branches/snowflake-deploy'
  DBT_VERSION = '1.11.11'
  DEFAULT_TARGET = 'snowflake';  -- deploy compiles at once; without this it uses the default target, DuckDB
EXECUTE DBT PROJECT SUPPLY_CHAIN.DEPLOY.SUPPLY_CHAIN_ANALYTICS
  ARGS = 'build --target snowflake --full-refresh';

-- 5. Run the incremental fact a second time: delete+insert over its 7-day window.
EXECUTE DBT PROJECT SUPPLY_CHAIN.DEPLOY.SUPPLY_CHAIN_ANALYTICS
  ARGS = 'run --select fct_orders --target snowflake';

-- 6. Reconcile with DuckDB: paste the output of
--      python governance/reconcile_snowflake.py sql
--    here, run it, save the JSON it returns to docs/snowflake/snowflake_totals.json,
--    then run `python governance/reconcile_snowflake.py compare docs/snowflake/snowflake_totals.json`.
