# Security

## Credentials

No credentials are committed to this repository.

- **Snowflake auth** is key-pair. The private key lives outside the repo (by default under
  `~/.snowflake/keys/`) and is referenced by path through the `SNOWFLAKE_PRIVATE_KEY_PATH`
  environment variable. See [`docs/SETUP.md`](docs/SETUP.md).
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
