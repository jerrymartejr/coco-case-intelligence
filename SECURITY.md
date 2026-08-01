# Security

## Least privilege

Nothing in this project runs as `ACCOUNTADMIN`. It is used to run
[`sql/00_setup.sql`](sql/00_setup.sql) and [`sql/01_least_privilege.sql`](sql/01_least_privilege.sql)
once, and never again.

| principal | used by | privileges |
|---|---|---|
| `CASE_INTEL_ROLE` | dbt, `upload_documents.py`, CoCo skills | create/replace in `CASE_INTEL.RAW` and `CASE_INTEL.ANALYTICS`, usage on the warehouse, `SNOWFLAKE.CORTEX_USER` |
| `CASE_INTEL_APP_ROLE` | the deployed Streamlit app | `SELECT` on `ANALYTICS` only, usage on the warehouse, `SNOWFLAKE.CORTEX_USER` for the app's one inline `AI_COMPLETE` call |
| `CASE_INTEL_APP_SVC` | the deployed app's identity | a `TYPE = SERVICE` user holding only `CASE_INTEL_APP_ROLE`, authenticating with its own key pair |

The deployed app is the part of this system exposed to the public internet, so it gets the
smallest role and a separate identity: the credential in a hosting provider's secret store
cannot write to the warehouse, cannot read the `RAW` schema, and is not the credential that
builds the pipeline. Being a `TYPE = SERVICE` user, it has no password and cannot log in
interactively.

## Credentials

No credentials are committed to this repository.

- **Snowflake auth** is key-pair. The private key lives outside the repo (by default under
  `~/.snowflake/keys/`) and is referenced by path through the `SNOWFLAKE_PRIVATE_KEY_PATH`
  environment variable. For hosted deployment the app also accepts the key *contents* via
  `SNOWFLAKE_PRIVATE_KEY` or `st.secrets`, since a hosting provider has no filesystem to
  put a key on. See [`docs/SETUP.md`](docs/SETUP.md).
- **Key encryption.** `docs/SETUP.md` generates the local development key with `-nocrypt`
  so dbt can read it without prompting mid-build. That is a stated trade-off, and the
  hardened path (a passphrase plus `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE`) is documented
  alongside it.
- **`profiles.yml`** and **`app/streamlit_app.py`** read every connection setting from
  environment variables. The committed defaults are account and user identifiers only,
  which are not secrets on their own: authentication still requires the private key.
- **CoCo** uses a named connection in `~/.snowflake/connections.toml`, also outside the repo.

## SQL construction

Values are always passed to Snowflake as bind parameters, never interpolated into query
text. The one thing templated into SQL is the schema identifier, because Snowflake cannot
bind an identifier; it is validated against a strict identifier pattern at import and the
app refuses to start if it does not match.

## Automated checks

`ruff` runs with the `bandit` (`S`) rule set enabled on every push, alongside the unit
tests and a `dbt parse`. See [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Reporting

This is a hackathon project, not a supported product. If you find something, open an issue.
