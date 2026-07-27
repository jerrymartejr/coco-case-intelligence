-- Case Intelligence: one-time Snowflake setup.
--
-- Run this once in a Snowsight worksheet on a fresh account, as ACCOUNTADMIN,
-- BEFORE the first `dbt build`. Creates the objects the pipeline expects and then
-- checks that the two Cortex models it depends on actually answer in your region.
--
-- See docs/SETUP.md for the surrounding steps (key pair, env vars, Anaconda terms).

use role accountadmin;

-- 1. Compute. XSMALL is enough: the heavy work is Cortex, not the warehouse.
create warehouse if not exists compute_wh
  warehouse_size = 'XSMALL'
  auto_suspend = 60
  auto_resume = true
  initially_suspended = true;

-- 2. Database and the two schemas the project writes to.
--    RAW holds the seeds, ANALYTICS holds staging/intermediate/marts.
create database if not exists case_intel;
create schema if not exists case_intel.raw;
create schema if not exists case_intel.analytics;

use warehouse compute_wh;
use database case_intel;
use schema analytics;

-- 3. Register your public key so dbt can authenticate headlessly.
--    Paste the body of case_intel_rsa_key.pub, with no header, footer or newlines.
--    Generate it as shown in docs/SETUP.md, then uncomment and run:
-- alter user <YOUR_USER> set rsa_public_key='MIIBIjANBgkq...';

-- 4. Preflight: both Cortex functions must work, or the pipeline cannot build.
--    Cortex model availability is REGIONAL. If either statement errors with
--    "unknown model" or "not available in region", see the troubleshooting table
--    in docs/SETUP.md for substitutes and update the model names in
--    macros/extract_common_fields.sql and models/intermediate/int_case_assignments.py.

-- 4a. Stage 1 and Stage 3 use this text model.
select snowflake.cortex.ai_complete('mistral-large2',
  'Reply with exactly one word: ok') as ai_complete_check;

-- 4b. Stage 2 uses this embedding model. Expect a 768-element vector.
select array_size(
  snowflake.cortex.embed_text_768('snowflake-arctic-embed-m-v1.5', 'test')::array
) as embed_dims_expect_768;

-- If both statements return without error, you are ready to run `dbt build`.
