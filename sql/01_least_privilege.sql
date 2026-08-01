-- Case Intelligence: roles and the deployed app's service user.
--
-- Run once, as ACCOUNTADMIN, after sql/00_setup.sql. Idempotent: safe to re-run.
--
-- Two principals, because they need different things:
--
--   CASE_INTEL_ROLE      what the BUILD needs. Creates and replaces every object dbt
--                        writes, including the stage the PDFs land in and the Cortex
--                        Search service the post-hook creates. This is what dbt and the
--                        CoCo skills should run as -- not ACCOUNTADMIN, which is what
--                        they defaulted to before and is the first thing a security
--                        review flags.
--
--   CASE_INTEL_APP_ROLE  what the DEPLOYED APP needs, which is far less: read the
--                        finished marts and call one Cortex function. It cannot write
--                        anything, cannot see the RAW schema, and is granted to a
--                        separate user with its own key pair, so the credential pasted
--                        into a hosting provider's secret store is not the credential
--                        that can rebuild the warehouse.
--
-- Nothing here grants ACCOUNTADMIN to anything. ACCOUNTADMIN is used only to run this
-- file and sql/00_setup.sql.

use role accountadmin;

-- ---------------------------------------------------------------------------------------
-- 1. The build role.
-- ---------------------------------------------------------------------------------------

create role if not exists case_intel_role
  comment = 'Builds and owns the Case Intelligence pipeline. Used by dbt and CoCo.';

grant usage, operate on warehouse compute_wh to role case_intel_role;
grant usage on database case_intel to role case_intel_role;
grant usage, create table, create view, create stage, create file format,
      create cortex search service
  on schema case_intel.raw to role case_intel_role;
grant usage, create table, create view, create stage, create file format,
      create cortex search service
  on schema case_intel.analytics to role case_intel_role;

-- dbt drops and recreates on --full-refresh, so it needs ownership of what already
-- exists, not merely the right to create more.
grant all on all tables in schema case_intel.raw to role case_intel_role;
grant all on all tables in schema case_intel.analytics to role case_intel_role;
grant all on all views in schema case_intel.analytics to role case_intel_role;
grant all on all stages in schema case_intel.raw to role case_intel_role;
grant all on future tables in schema case_intel.raw to role case_intel_role;
grant all on future tables in schema case_intel.analytics to role case_intel_role;
grant all on future views in schema case_intel.analytics to role case_intel_role;
grant all on future stages in schema case_intel.raw to role case_intel_role;

-- Every Cortex function the pipeline calls: AI_COMPLETE, EMBED_TEXT_768,
-- PARSE_DOCUMENT, and the Cortex Search service.
grant database role snowflake.cortex_user to role case_intel_role;

-- ---------------------------------------------------------------------------------------
-- 2. The app role: read the marts, call one Cortex function, nothing else.
-- ---------------------------------------------------------------------------------------

create role if not exists case_intel_app_role
  comment = 'Read-only. Backs the deployed Streamlit app. No write, no RAW schema.';

grant usage on warehouse compute_wh to role case_intel_app_role;
grant usage on database case_intel to role case_intel_app_role;
grant usage on schema case_intel.analytics to role case_intel_app_role;
grant select on all tables in schema case_intel.analytics to role case_intel_app_role;
grant select on all views in schema case_intel.analytics to role case_intel_app_role;
grant select on future tables in schema case_intel.analytics to role case_intel_app_role;
grant select on future views in schema case_intel.analytics to role case_intel_app_role;

-- The app generates its recommendation inline with AI_COMPLETE, so it needs this. It is
-- the only privilege the app has beyond reading.
grant database role snowflake.cortex_user to role case_intel_app_role;

-- ---------------------------------------------------------------------------------------
-- 3. The app's service user.
-- ---------------------------------------------------------------------------------------
--
-- Key-pair only: no password is ever set, so there is no interactive login to phish and
-- nothing to rotate but the key. Generate the key pair OUTSIDE the repo:
--
--   openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM \
--     -out ~/.snowflake/keys/case_intel_app_svc.p8 -nocrypt
--   openssl rsa -in ~/.snowflake/keys/case_intel_app_svc.p8 -pubout \
--     -out ~/.snowflake/keys/case_intel_app_svc.pub
--
-- then paste the body of the .pub (no header, footer or newlines) into the ALTER below.

create user if not exists case_intel_app_svc
  type = service
  default_role = case_intel_app_role
  default_warehouse = compute_wh
  default_namespace = case_intel.analytics
  comment = 'Service account for the deployed Case Intelligence app. Read-only.';

grant role case_intel_app_role to user case_intel_app_svc;

-- alter user case_intel_app_svc set rsa_public_key='MIIBIjANBgkq...';

-- ---------------------------------------------------------------------------------------
-- 4. Grant the build role to yourself, then switch to it.
-- ---------------------------------------------------------------------------------------
-- Replace <YOUR_USER>, run, and set SNOWFLAKE_ROLE=CASE_INTEL_ROLE in your .env.
--
-- grant role case_intel_role to user <YOUR_USER>;

-- ---------------------------------------------------------------------------------------
-- 5. Hand over what already exists.
-- ---------------------------------------------------------------------------------------
--
-- On a FRESH account this section does nothing: the build role creates every object and
-- owns it from the start. It matters on an account that built the pipeline before the
-- role existed, where everything is owned by ACCOUNTADMIN.
--
-- Ownership, not privilege, is the operative word. `grant all` lets a role read and write
-- a table but not `create or replace` it, and create-or-replace is exactly what every dbt
-- run does. Without this, switching dbt to CASE_INTEL_ROLE fails on the first model.
--
-- `copy current grants` keeps the existing grants attached, so nothing that could read
-- these objects a moment ago stops being able to.

grant ownership on schema case_intel.raw to role case_intel_role copy current grants;
grant ownership on schema case_intel.analytics to role case_intel_role copy current grants;
grant ownership on all tables in schema case_intel.raw to role case_intel_role copy current grants;
grant ownership on all tables in schema case_intel.analytics to role case_intel_role copy current grants;
grant ownership on all views in schema case_intel.analytics to role case_intel_role copy current grants;
grant ownership on all stages in schema case_intel.raw to role case_intel_role copy current grants;
grant ownership on all cortex search services in schema case_intel.analytics
  to role case_intel_role copy current grants;

-- The app role's SELECT grants were attached to the tables above, and `copy current
-- grants` preserved them. Re-run them anyway: it is idempotent, and it is cheaper than
-- discovering later that the deployed app went blind.
grant usage on schema case_intel.analytics to role case_intel_app_role;
grant select on all tables in schema case_intel.analytics to role case_intel_app_role;
grant select on all views in schema case_intel.analytics to role case_intel_app_role;
