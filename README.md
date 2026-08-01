# Case Intelligence

**Snowflake CoCo Hackathon 2026 · Track 2 (Unstructured Data Intelligence)**

Turn a pile of unstructured customer-support records that share **no common key** into a
tested, queryable, **actionable** case-intelligence table, and an agent that reasons and
acts on top of it.

## The idea

Support interactions for one problem arrive across channels (chat, email, QA notes, CSAT,
and PDF escalation forms) in different words, with **different or missing identifiers**. The hard, valuable part is
linking them into a single *case* without a shared key. That is the product here, not a
glorified join.

- **dbt** owns the deterministic, tested backbone (Stages 1-4 + rollups).
- **Cortex AI SQL** runs inside the dbt models (AI_COMPLETE, EMBED_TEXT_768).
- **Cortex Search** indexes every raw record so questions can be answered from the source text.
- **CoCo Agent Skills + Streamlit** own the agentic layer (Stage 5): search, ask, diagnose, recommend, act.

## Pipeline

| Stage | Model(s) | What it does | Cortex |
|-------|----------|--------------|--------|
| 1 normalize | `stg_chat/email/qa_notes/csat/documents` -> `stg_records` | every format, text and binary, -> one common schema | PARSE_DOCUMENT, AI_COMPLETE |
| 2 resolve | `int_record_entities` -> `int_case_assignments` (Snowpark) -> `int_case_records` | link keyless records into a `case_id`: deterministic entity pass, then embedding similarity + Union-Find | EMBED_TEXT_768 |
| 3 synthesize | `fct_case_fact` | collapse each case into one fact row (issue, timeline, resolved, root cause, sentiment) | AI_COMPLETE |
| 4 enrich | `fct_case_enriched` | join structured metrics (revenue at risk, CSAT, FCR, AHT) | SQL |
| 5 retrieve | `search_corpus` -> `CASE_RECORD_SEARCH` | index every raw record so questions can be answered from what customers actually wrote | Cortex Search |
| 5 act | `agg_*`, `coco/skills/`, `app/` | rollups, NL query, diagnose driver, recommend + deliver action | AI_COMPLETE |

## Measured result

Identity resolution over **614 records / 192 planted cases / 67 customers**, scored against
a ground-truth key the pipeline never reads (`data/synthetic/ground_truth.json`).

The corpus is deliberately in two halves, and the split is the whole point. Tiers A-C are
generated under conditions the resolver needs — unique surnames, a customer's cases far
apart in time. **A perfect score on those measures the generator, not the method**, so they
are published as a regression floor rather than as a result. Tier D breaks those conditions
on purpose, at collision rates taken from real-shaped reference data
([`docs/realism-report.md`](docs/realism-report.md), where 82% of customers collide on
surname). Tier D is the result.

| tier | shape | cases | recall | precision |
|---|---|---:|---:|---:|
| A | entity overlap | 53 | 1.000 | 1.000 |
| B | **semantic only — the keyless hero tier** | 103 | 1.000 | 1.000 |
| C | shared ticket id | 14 | 1.000 | 1.000 |
| **D** | collision, identity present | 6 | **1.000** | **1.000** |
| **D** | collision, identity corrupted | 4 | 0.750 | 1.000 |
| **D** | collision, fully keyless | 6 | 1.000 | **0.000** |
| **D** | same customer, one window | 6 | 1.000 | 0.800 |
| noise | must not merge | 55 | 1.000 | 1.000 |

**Tier D overall: recall 0.955, precision 0.789.** Read the two extremes, because they are
the honest edges of the method:

- **Identity present, 1.000/1.000.** Two *different* customers who share a surname, contact
  support the same afternoon, about the *same* issue, with their records interleaved in
  time. Name, time and meaning all agree — nothing in the unstructured text can separate
  them. The order and the address can, and do. This is the proof that fusing structured with
  unstructured data is load-bearing here rather than decorative.
- **Fully keyless, 0.000.** The same collision with no identifier anywhere. Every pair false
  merges. Two strangers who share a surname, write in the same hours, and carry no
  identifier simply cannot be told apart from text — the measured limit of keyless linking,
  stated rather than hidden.

Also measured: **31 of the 41 PDF escalation forms sit in the keyless tier and were linked
semantically** — a binary document tied to a chat and an email by nothing but a surname, the
meaning of the complaint, and a few hours. Every link is inspectable in `int_case_edges`,
and the whole table above is a query: `select * from agg_linkage_accuracy`.

Four of these are build gates, not claims: `assert_cases_fully_linked`,
`assert_no_case_contamination`, `assert_noise_stays_isolated` and
`assert_tier_d_precision_holds`. `dbt build` fails if any regresses.

## Synthetic data

We generate both halves of the data so the pipeline runs end to end today; real data swaps
in later at the same schemas (see below). `scripts/generate_synthetic_data.py` is
deterministic and produces **614 records across 192 cases and 67 customers** in five
formats and four difficulty tiers:

- **Tier A** entity overlap (shared email / order ref)
- **Tier B** semantic-only, the hero: no shared key, linkable by fuzzy name + issue semantics + time
- **Tier C** trivial (shared ticket id), plus noise that must not merge
- **Tier D** adversarial: colliding surnames, corrupted addresses and repeat episodes inside
  the link window. The tier that exists so the headline result cannot be self-fulfilling;
  its rates come from [`docs/realism-report.md`](docs/realism-report.md)

The five formats are chat JSON, email with headers, free-text QA notes, CSAT JSON, and
**real PDF escalation forms**. The PDFs are written by the generator, uploaded to a
Snowflake stage, and read back with Cortex `PARSE_DOCUMENT`, so the pipeline genuinely
spans a binary modality rather than four flavours of text.

## Run it

**First time on a new machine or account, follow [`docs/SETUP.md`](docs/SETUP.md).** It
covers the Snowflake objects, the Anaconda terms step needed by the Stage 2 Python model,
key-pair auth, the environment variables, and the regional Cortex caveat. About 30 minutes.

Once set up:

```bash
source .venv/bin/activate && source .env          # credentials, see docs/SETUP.md
dbt deps --profiles-dir .
python3 scripts/upload_documents.py               # PDFs -> Snowflake stage (once)
dbt build --profiles-dir .                        # seed -> run -> test, one command
streamlit run app/streamlit_app.py                # the demo UI (optional)
```

The data is committed, so you only need the generator if you want to regenerate it (it is
deterministic and produces identical output):

```bash
python3 scripts/generate_synthetic_data.py
dbt build --profiles-dir . --full-refresh
```

Auth: dbt uses key-pair auth, configured through environment variables in `profiles.yml`.
Cortex/CoCo use a named connection in `~/.snowflake/connections.toml`. A full build makes
roughly 1,500 Cortex calls, so it is cheap but not free.

## Talking to your data through CoCo (the agentic layer)

The four CoCo Agent Skills in `coco/skills/` turn CoCo into a natural-language front door
over the marts. Register them once (machine-local):

```bash
bash scripts/register_skills.sh
```

Then open CoCo in the repo and ask in plain English:

```bash
cortex -c coco_trial
```

- **ask_case_intelligence** — "How many cases are unresolved and what's the total revenue at risk?"
- **search_case_records** — "What are customers actually saying about the app crashing?" Retrieves the real
  records across all five formats with Cortex Search, then answers from their own words.
- **diagnose_top_drivers** — "What's the biggest driver of revenue at risk, and why?"
- **recommend_action** — "Recommend a concrete action for the top driver."
- **deliver_action** — "Draft the message to send the owning team" (posts via MCP if Slack/ticketing is configured, otherwise returns the ready-to-send message).

These have been tested end to end: CoCo writes SQL over the marts, grounds every number,
chains diagnose → recommend → deliver, and falls back cleanly when no delivery integration
is present.

## Swapping in real data

Everything is built against the contract in `AGENTS.md`, not against specific files. To use
real data, replace the generator's outputs at the **same schemas**:

- unstructured -> the `RAW_*` seed CSVs (or a Snowpipe/stage load into the same tables)
- structured -> `seeds/orders.csv`, `seeds/csat_scores.csv`, `seeds/agent_daily_metrics.csv`

Then `dbt build`. No model changes.

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
ruff check .        # lint, including the bandit security rules
pytest              # unit tests, no Snowflake connection needed
```

CI runs the same three steps plus a `dbt parse` on every push, and re-runs the generator to
prove the committed corpus is still reproducible from it. Nothing in CI needs credentials.
The accuracy tests that do need a warehouse run inside `dbt build`.

## Known limitations

Full-refresh only (no incremental). LLM output can be malformed and is guarded with
`TRY_PARSE_JSON`. Structured enrichment attaches only where an identity resolves.
