# Setup: running Case Intelligence on your own Snowflake

Everything here is one-time except the last step. Budget about 30 minutes, most of it
waiting on the Snowflake trial signup.

The pipeline runs entirely inside Snowflake: dbt builds the tables and Cortex AI runs
inside the models. You need your own Snowflake account because the build spends credits.

---

## 0. Before you start

| Requirement | Notes |
|---|---|
| Snowflake account with Cortex | A free trial works. Pick a region where Cortex is available (see step 2). |
| `ACCOUNTADMIN` on that account | Needed for the one-time setup SQL and to register your key. Nothing after step 3 runs as `ACCOUNTADMIN`. |
| Python **3.12** | 3.13 is not supported by dbt-snowflake 1.12. |
| `git` | To clone. |

**Cost warning.** One full `dbt build` makes roughly **1,500 Cortex calls** at the current
data scale (614 records through Stage 1, 614 embeddings in Stage 2, 244 case syntheses in
Stage 3, plus 41 `PARSE_DOCUMENT` calls). That is small but not free, and it re-runs every
time. Do not put it in a loop. Parsing the PDFs is the slow part, roughly four minutes.
The build also creates a Cortex Search service with a one-day target lag, which refreshes
on its own schedule and costs a little compute; drop it with
`drop cortex search service case_intel.analytics.case_record_search` when you are done.
If you only want to see the code work, `dbt build --select stg_chat` is far cheaper.

---

## 1. Clone and create the Python environment

```bash
git clone git@github.com:jerrymartejr/coco-case-intelligence.git
cd coco-case-intelligence

python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If `python3.12` is not on your machine: `brew install python@3.12` on macOS, or use
whatever your platform provides. Check with `python3.12 --version`.

---

## 2. Create the Snowflake objects

Open a Snowsight worksheet on your account, as `ACCOUNTADMIN`, and run
[`sql/00_setup.sql`](../sql/00_setup.sql). It creates:

- warehouse `COMPUTE_WH` (XSMALL, auto-suspend 60s)
- database `CASE_INTEL` with schemas `RAW` and `ANALYTICS`

and then runs two preflight checks that call the Cortex models the pipeline depends on:
`mistral-large2` and `snowflake-arctic-embed-m-v1.5`.

**Both preflight statements must succeed.** Cortex model availability is regional. If
either fails, see [troubleshooting](#troubleshooting) before going further, because the
build cannot work without them.

---

## 3. Create the roles

Still as `ACCOUNTADMIN`, run [`sql/01_least_privilege.sql`](../sql/01_least_privilege.sql).
It creates two roles and one service user, and it is the last thing you run as account
admin:

| principal | what it is for | what it can do |
|---|---|---|
| `CASE_INTEL_ROLE` | the build: dbt, the PDF uploader, CoCo | create and replace objects in the two schemas, call Cortex |
| `CASE_INTEL_APP_ROLE` | the deployed Streamlit app | `SELECT` on `ANALYTICS` and one Cortex function. No writes, no `RAW` |
| `CASE_INTEL_APP_SVC` | the app's service user, key-pair only | holds `CASE_INTEL_APP_ROLE` and nothing else |

Two lines in that file are commented out because they need your values: granting
`CASE_INTEL_ROLE` to your own user, and registering the service user's public key. Do the
first now; the second only matters if you deploy the app.

Running the pipeline as account admin works, and it is what a hurry would do. The reason
not to is that `dbt build` and a public web app then share the single credential that can
delete everything in the account — and one of those two is pasted into a hosting
provider's secret store.

---

## 4. Accept the Anaconda terms

Stage 2 (`models/intermediate/int_linkage_graph.py`) is a dbt **Python** model, which
Snowflake runs as a Snowpark stored procedure. Snowpark pulls its packages from
Snowflake's Anaconda channel, and an `ORGADMIN` has to accept those terms once per
account before any Python model will run.

In Snowsight: **Admin → Billing & Terms → Anaconda → Enable**.

Skipping this is the single most common first-run failure, and the error message does not
make the cause obvious. Every other model in the project is SQL and will build fine, so
you can hit this quite far into the build.

---

## 5. Generate a key pair and register it

dbt authenticates headlessly with a key pair, so there is no browser prompt mid-build.

```bash
mkdir -p ~/.snowflake/keys && cd ~/.snowflake/keys

# Private key, unencrypted so dbt can read it without a passphrase prompt.
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out case_intel_rsa_key.p8 -nocrypt
chmod 600 case_intel_rsa_key.p8

# Matching public key.
openssl rsa -in case_intel_rsa_key.p8 -pubout -out case_intel_rsa_key.pub

# Print it as one line for the ALTER USER statement.
grep -v "^-----" case_intel_rsa_key.pub | tr -d '\n'; echo
```

Copy that output and run in Snowsight, replacing both placeholders:

```sql
alter user <YOUR_USER> set rsa_public_key='<PASTE_THE_ONE_LINE_KEY>';
```

Keep the private key outside the repo. It is not gitignored by name, only by location.

`-nocrypt` writes the key unencrypted, which is what lets dbt read it mid-build without
stopping for a passphrase. That is a local-development trade-off: anyone who can read the
file can authenticate as you. To harden it, drop `-nocrypt`, and set
`SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` alongside `SNOWFLAKE_PRIVATE_KEY_PATH`.

---

## 6. Point the project at your account

`profiles.yml` reads everything from environment variables and has **no defaults** for the
three that identify your account, so a missing variable fails loudly instead of quietly
pointing at somebody else's warehouse.

```bash
cp .env.example .env
# edit .env with your account, user and private key path
source .env
```

`SNOWFLAKE_ROLE` defaults to `CASE_INTEL_ROLE` from step 3. The other optional overrides
(`SNOWFLAKE_DATABASE`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_SCHEMA`) only matter if you
changed them in step 2.

`.env` is gitignored. Re-`source` it in each new terminal, or add it to your shell profile.
Then confirm:

```bash
dbt debug --profiles-dir .
```

You want `Connection test: [OK connection ok]`. Do not continue until you get it.

---

## 7. Build it

```bash
source .env                                 # the variables from step 5
dbt deps --profiles-dir .                   # installs dbt_utils
python3 scripts/upload_documents.py         # PDFs -> the RAW.DOCUMENTS stage
dbt build --profiles-dir .                  # seed -> run models -> tests
```

`upload_documents.py` is needed because one of the five sources is a real binary format.
The PDF escalation forms cannot be dbt seeds, so they are PUT into a Snowflake stage with a
directory table and read back by `stg_documents` with Cortex `PARSE_DOCUMENT`. Re-run it
whenever you regenerate the corpus.

Takes about five minutes, most of it parsing the PDFs. The data is already committed, so you do **not** need to run the
generator first. If you want to regenerate it (it is deterministic, so you get identical
output):

```bash
python3 scripts/generate_synthetic_data.py
dbt build --profiles-dir . --full-refresh   # --full-refresh whenever seed columns change
```

### What a correct run looks like

```
Done. PASS=89 WARN=0 ERROR=0 SKIP=0 TOTAL=89
```

Four of those tests score Stage 2 against the hidden ground-truth key on every build:
`assert_cases_fully_linked` (recall), `assert_no_case_contamination` (precision),
`assert_noise_stays_isolated`, and `assert_tier_d_precision_holds` for the adversarial
tier. Tiers A-C hold at 100% as a regression floor; tier D is measured, not assumed, and
currently scores recall 0.955 / precision 0.789.

To see the whole scoreboard yourself, per tier and per adversarial shape:

```sql
select * from case_intel.analytics.agg_linkage_accuracy;
```

---

## 8. The Streamlit demo (optional)

```bash
pip install -r app/requirements.txt
streamlit run app/streamlit_app.py
```

---

## 9. CoCo Agent Skills (optional)

The six skills in `coco/skills/` turn CoCo into a natural-language front door over the
finished tables. One of them, `search_case_records`, retrieves the underlying records with
the Cortex Search service that `dbt build` creates, so questions can be answered from what
customers actually wrote rather than only from aggregates. They need the Cortex CLI installed and a named connection.

**Install the CLI.** Snowflake publishes an install script at
`https://ai.snowflake.com/static/cc-scripts/install.sh`. If you would rather not pipe a
script straight into a shell, download it, read it, then run it. It lands the binary at
`~/.local/bin/cortex`, so make sure that is on your `PATH`.

**Create the connection** in `~/.snowflake/connections.toml`:

```toml
[case_intel]
account = "ABCDEFG-XY12345"
user = "YOURUSER"
authenticator = "externalbrowser"   # opens a browser once; or use a PAT instead
database = "CASE_INTEL"
schema = "ANALYTICS"
warehouse = "COMPUTE_WH"
role = "CASE_INTEL_ROLE"
```

**Use browser or PAT auth here, not a key pair.** dbt and the Streamlit app authenticate
with the key pair from step 5, but CoCo's SQL tool could not authenticate with one in
testing: the skills fire and write correct SQL, then fail to execute it. Browser auth
works. Run `cortex -c case_intel` once and complete the login before you need it in front
of an audience.

**Register the skills** (machine-local, so everyone does this once):

```bash
bash scripts/register_skills.sh
cortex -c case_intel
```

Then ask in plain English, for example *"How many cases are unresolved and what is the
total revenue at risk?"* or *"What is the biggest driver of revenue at risk, and why?"*

> If you already have a connection under a different name, use that name instead — the
> README and this file both assume `case_intel`.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `stg_documents` returns 0 rows | The stage is empty. Run `python3 scripts/upload_documents.py`. |
| `PARSE_DOCUMENT` errors on the stage | The stage must use server-side encryption (`SNOWFLAKE_SSE`). The uploader creates it correctly; if you made it by hand, recreate it. |
| `250001 Could not connect` / JWT or token errors | The public key never got registered, or `SNOWFLAKE_USER` does not match the user you ran `alter user` on. Redo step 4. |
| `Object 'CASE_INTEL.RAW.X' does not exist` | Setup SQL was not run, or you are pointed at a different database. Redo step 2, check `SNOWFLAKE_DATABASE`. |
| Python model `int_linkage_graph` fails, SQL models are fine | Anaconda terms not accepted. Step 4. |
| `unknown model` / `not available in region` from Cortex | The model is not enabled where your account lives. Either recreate the trial in a supported region, or substitute with one variable: `dbt build --profiles-dir . --vars '{cortex_text_model: llama3.1-70b}'` (also try `snowflake-arctic`). The embedding model is `cortex_embed_model` (try `e5-base-v2`, but note the code assumes 768 dimensions). Both default in `dbt_project.yml`. Export `CASE_INTEL_TEXT_MODEL` so the Streamlit app matches. Rebuild fully afterwards. |
| `invalid identifier` right after changing a seed | Seed column sets changed. Use `dbt build --full-refresh`. |
| `assert_cases_fully_linked` fails | Stage 2 linked fewer records than the ground truth says it should. Usually means a Cortex model substitution changed the embedding behaviour. See the `SIM_FLOOR` note in `models/intermediate/int_linkage_graph.py`, which documents the measured similarity distributions and why the floor sits at 0.62. |
| `ModuleNotFoundError: pandas` inside a Python model | The Snowpark sandbox has no pandas. Use `.collect()`, not `.to_pandas()`. Already handled in this repo; only relevant if you add a Python model. |
| Build is slow or credits drop fast | Expected: about 1,500 Cortex calls per full build. Use `--select` to build a subset while developing. |

---

## Where to read next

- [`AGENTS.md`](../AGENTS.md) — the contract: case-fact schema, source schemas, difficulty
  tiers, and the Stage-by-Stage decisions with their rationale
- [`README.md`](../README.md) — what the project is and the measured results
- [`docs/demo-script.md`](demo-script.md) — the four-minute demo, prompt by prompt
- [`docs/realism-report.md`](realism-report.md) — the analysis of the teammate reference
  datasets and which patterns were harvested into the generator
