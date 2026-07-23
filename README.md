# Case Intelligence

**Snowflake CoCo Hackathon 2026 · Track 2 (Unstructured Data Intelligence)**

Turn a pile of unstructured customer-support records that share **no common key** into a
tested, queryable, **actionable** case-intelligence table, and an agent that reasons and
acts on top of it.

## The idea

Support interactions for one problem arrive across channels (chat, email, QA notes, CSAT)
in different words, with **different or missing identifiers**. The hard, valuable part is
linking them into a single *case* without a shared key. That is the product here, not a
glorified join.

- **dbt** owns the deterministic, tested backbone (Stages 1-4 + rollups).
- **Cortex AI SQL** runs inside the dbt models (AI_COMPLETE, EMBED_TEXT_768).
- **CoCo Agent Skills + Streamlit** own the agentic layer (Stage 5): ask, diagnose, recommend, act.

## Pipeline

| Stage | Model(s) | What it does | Cortex |
|-------|----------|--------------|--------|
| 1 normalize | `stg_chat/email/qa_notes/csat` -> `stg_records` | every format -> one common schema | AI_COMPLETE |
| 2 resolve | `int_record_entities` -> `int_case_assignments` (Snowpark) -> `int_case_records` | link keyless records into a `case_id`: deterministic entity pass, then embedding similarity + Union-Find | EMBED_TEXT_768 |
| 3 synthesize | `fct_case_fact` | collapse each case into one fact row (issue, timeline, resolved, root cause, sentiment) | AI_COMPLETE |
| 4 enrich | `fct_case_enriched` | join structured metrics (revenue at risk, CSAT, FCR, AHT) | SQL |
| 5 act | `agg_*`, `coco/skills/`, `app/` | rollups, NL query, diagnose driver, recommend + deliver action | AI_COMPLETE |

## Measured result (on synthetic data with a ground-truth key)

Stage 2 identity resolution, scored against `data/synthetic/ground_truth.json`:

- **8/8** planted cases fully linked (including the keyless "semantic-only" tier)
- **0** false merges (perfect precision)
- **12/12** noise records correctly isolated

These are enforced as dbt tests: `assert_cases_fully_linked` (recall) and
`assert_no_case_contamination` (precision). `dbt build` fails if either regresses.

## Synthetic data

We generate both halves of the data so the pipeline runs end to end today; real data swaps
in later at the same schemas (see below). `scripts/generate_synthetic_data.py` is
deterministic and produces three difficulty tiers:

- **Tier A** entity overlap (shared email / order ref)
- **Tier B** semantic-only, the hero: no shared key, linkable by fuzzy name + issue semantics + time
- **Tier C** trivial (shared ticket id), plus noise that must not merge

## Run it

```bash
python3 scripts/generate_synthetic_data.py         # regenerate synthetic data + ground truth
dbt deps
dbt build                                          # seed -> run -> test, one command
streamlit run app/streamlit_app.py                 # the demo UI (optional)
```

Auth: dbt uses key-pair auth against the Snowflake trial (see `profiles.yml`). Cortex/CoCo
use the `coco_trial` connection in `~/.snowflake/connections.toml`.

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

## Known limitations

Full-refresh only (no incremental). LLM output can be malformed and is guarded with
`TRY_PARSE_JSON`. Structured enrichment attaches only where an identity resolves.
