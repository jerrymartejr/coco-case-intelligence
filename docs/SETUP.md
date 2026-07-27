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
| `ACCOUNTADMIN` on that account | Needed for the setup SQL and to register your key. |
| Python **3.12** | 3.13 is not supported by dbt-snowflake 1.12. |
| `git` | To clone. |

**Cost warning.** One full `dbt build` makes roughly **1,270 Cortex calls** at the current
data scale (518 records through Stage 1, 518 embeddings in Stage 2, 225 case syntheses in
Stage 3). That is small but not free, and it re-runs every time. Do not put it in a loop.
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

## 3. Accept the Anaconda terms

Stage 2 (`models/intermediate/int_case_assignments.py`) is a dbt **Python** model, which
Snowflake runs as a Snowpark stored procedure. Snowpark pulls its packages from
Snowflake's Anaconda channel, and an `ORGADMIN` has to accept those terms once per
account before any Python model will run.

In Snowsight: **Admin → Billing & Terms → Anaconda → Enable**.

Skipping this is the single most common first-run failure, and the error message does not
make the cause obvious. Every other model in the project is SQL and will build fine, so
you can hit this quite far into the build.

---

## 4. Generate a key pair and register it

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

---

## 5. Point the project at your account

`profiles.yml` reads everything from environment variables, with the original author's
account as the default. Set at least these three, or you will be trying to connect to an
account you have no key for:

```bash
export SNOWFLAKE_ACCOUNT=ABCDEFG-XY12345          # Snowsight: account name / locator
export SNOWFLAKE_USER=YOURUSER
export SNOWFLAKE_PRIVATE_KEY_PATH=~/.snowflake/keys/case_intel_rsa_key.p8
```

Optional overrides, only if you changed them in step 2: `SNOWFLAKE_ROLE`,
`SNOWFLAKE_DATABASE`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_SCHEMA`.

Put those exports in your shell profile or a local `.env` you source, so they survive a
new terminal. Then confirm:

```bash
dbt debug --profiles-dir .
```

You want `Connection test: [OK connection ok]`. Do not continue until you get it.

---

## 6. Build it

```bash
dbt deps --profiles-dir .                   # installs dbt_utils
dbt build --profiles-dir .                  # seed -> run 16 models -> 17 tests
```

Takes about a minute. The data is already committed, so you do **not** need to run the
generator first. If you want to regenerate it (it is deterministic, so you get identical
output):

```bash
python3 scripts/generate_synthetic_data.py
dbt build --profiles-dir . --full-refresh   # --full-refresh whenever seed columns change
```

### What a correct run looks like

```
Done. PASS=41 WARN=0 ERROR=0 SKIP=0 TOTAL=41
```

The two tests that matter are `assert_cases_fully_linked` (recall) and
`assert_no_case_contamination` (precision). They score Stage 2 against the hidden
ground-truth key on every build. Current measured result:

- **170/170** cases fully linked — Tier A 53/53, Tier B 103/103, Tier C 14/14
- **0** false merges
- **55/55** noise records correctly isolated

To see it yourself:

```sql
select tier, count(distinct true_case_id) as cases,
       count(distinct case when n > 1 then true_case_id end) as split
from (select true_case_id, tier,
             count(distinct pred_case_id) over (partition by true_case_id) as n
      from case_intel.analytics.eval_case_linkage where is_noise = 'false')
group by tier order by tier;
```

---

## 7. The Streamlit demo (optional)

```bash
pip install -r app/requirements.txt
streamlit run app/streamlit_app.py
```

---

## 8. CoCo Agent Skills (optional)

The four skills in `coco/skills/` turn CoCo into a natural-language front door over the
finished tables. They need the Cortex CLI installed and a named connection.

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
role = "ACCOUNTADMIN"
```

**Register the skills** (machine-local, so everyone does this once):

```bash
bash scripts/register_skills.sh
cortex -c case_intel
```

Then ask in plain English, for example *"How many cases are unresolved and what is the
total revenue at risk?"* or *"What is the biggest driver of revenue at risk, and why?"*

> The README examples use a connection named `coco_trial`. Use whatever you named yours.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `250001 Could not connect` / JWT or token errors | The public key never got registered, or `SNOWFLAKE_USER` does not match the user you ran `alter user` on. Redo step 4. |
| `Object 'CASE_INTEL.RAW.X' does not exist` | Setup SQL was not run, or you are pointed at a different database. Redo step 2, check `SNOWFLAKE_DATABASE`. |
| Python model `int_case_assignments` fails, SQL models are fine | Anaconda terms not accepted. Step 3. |
| `unknown model` / `not available in region` from Cortex | The model is not enabled where your account lives. Either recreate the trial in a supported region, or substitute: swap `mistral-large2` in `macros/extract_common_fields.sql` (try `llama3.1-70b` or `snowflake-arctic`) and `snowflake-arctic-embed-m-v1.5` in `models/intermediate/int_case_assignments.py` (try `e5-base-v2`, but note it is 768-dim too, which the code assumes). Rebuild fully afterwards. |
| `invalid identifier` right after changing a seed | Seed column sets changed. Use `dbt build --full-refresh`. |
| `assert_cases_fully_linked` fails | Stage 2 linked fewer records than the ground truth says it should. Usually means a Cortex model substitution changed the embedding behaviour. See the `SIM_FLOOR` note in `models/intermediate/int_case_assignments.py`, which documents the measured similarity distributions and why the floor sits at 0.62. |
| `ModuleNotFoundError: pandas` inside a Python model | The Snowpark sandbox has no pandas. Use `.collect()`, not `.to_pandas()`. Already handled in this repo; only relevant if you add a Python model. |
| Build is slow or credits drop fast | Expected: about 1,270 Cortex calls per full build. Use `--select` to build a subset while developing. |

---

## Where to read next

- [`AGENTS.md`](../AGENTS.md) — the contract: case-fact schema, source schemas, difficulty
  tiers, and the Stage-by-Stage decisions with their rationale
- [`README.md`](../README.md) — what the project is and the measured results
- [`docs/realism-report.md`](realism-report.md) — the analysis of the teammate reference
  datasets and which patterns were harvested into the generator
