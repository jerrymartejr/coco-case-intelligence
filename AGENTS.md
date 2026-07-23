# Case Intelligence — shared contract

One document every tool and teammate builds against (Cursor, CoCo, Claude Code, humans).
CoCo Hackathon 2026, Track 2 (Unstructured Data Intelligence). Domain: customer support / BPO.
Synthetic data only. Grain: one row per **case**. Output must be **actionable**.

## Thesis (do not dilute)

The product is **linking records that share no key** into a single case. Records arrive
across channels (chat, email, QA note, CSAT) describing the same issue for the same customer
in different words, with **different or missing identifiers**. Resolving them into one case
is the value. We do NOT plant shared case keys as a crutch. See the difficulty tiers below.

## Build strategy

Build against this contract, not against anyone's deliverables. We generate synthetic data
for both the unstructured side (normally Francis) and the structured side (normally Jim) now,
so the pipeline runs end to end today. When real data arrives it replaces the generated inputs
at the **same schemas** and we rerun. No model changes.

- **dbt** owns the deterministic backbone (Stages 1-4): staging -> intermediate -> marts,
  with Cortex AI SQL run inside models. Tested, materialized, one `dbt build`.
- **CoCo Agent Skills / Streamlit** own the agentic Stage 5: NL query, diagnose drivers,
  recommend + (stretch) deliver an action.

## The contract: `fct_case_fact` (one row per case)

| column           | type      | meaning                                             | populated by |
|------------------|-----------|-----------------------------------------------------|--------------|
| case_id          | STRING PK | generated when records are unified                  | Stage 2      |
| customer_id      | STRING    | resolved customer identity                          | Stage 2      |
| issue            | STRING    | the underlying problem, normalized                  | Stage 3      |
| channels         | ARRAY     | channels the case appeared on                       | Stage 2/3    |
| record_count     | INT       | how many raw records were unified                   | Stage 2      |
| agents_involved  | ARRAY     | agent ids that touched the case                     | Stage 3      |
| first_ts/last_ts | TIMESTAMP | case open/close window                              | Stage 3      |
| timeline         | STRING    | ordered what-happened narrative                     | Stage 3      |
| resolved         | BOOLEAN   | was it resolved                                     | Stage 3      |
| root_cause       | STRING    | synthesised root cause                              | Stage 3      |
| resolution_path  | STRING    | how it was fixed                                    | Stage 3      |
| sentiment        | STRING    | overall sentiment (neg/neutral/pos)                 | Stage 3      |
| revenue_at_risk  | NUMBER    | joined from orders                                  | Stage 4      |
| csat_score       | INT       | joined from csat                                    | Stage 4      |
| fcr / aht        | NUMBER    | joined from agent-daily metrics                     | Stage 4      |

Everything coarser (per customer, agent, day, root cause) is a Stage 5 rollup on top.

## Source schemas (unstructured, Francis's side)

Raw tables loaded into schema `RAW`. Each row is one raw record; the model reads `raw_content`.

- `RAW_CHAT`      (record_id STRING, raw_content STRING, received_ts TIMESTAMP) — chat JSON blob
- `RAW_EMAIL`     (record_id STRING, raw_content STRING, received_ts TIMESTAMP) — email text w/ headers
- `RAW_QA_NOTES`  (record_id STRING, raw_content STRING, received_ts TIMESTAMP) — free-text QA note
- `RAW_CSAT`      (record_id STRING, raw_content STRING, received_ts TIMESTAMP) — CSAT survey JSON

Staging extracts a common schema from each via Cortex AI:
`record_id, source_type, customer_name, customer_email, order_ref, occurred_ts, channel, agent_id, issue_text, resolution_text, sentiment`.

## Structured schemas (Jim's side) — dbt seeds

- `orders`(order_id, customer_id, email, value, placed_ts, status) — also the email<->order bridge
- `csat_scores`(survey_id, order_ref, customer_id, score, submitted_ts)
- `agent_daily_metrics`(agent_id, metric_date, aht, fcr, occupancy, avg_csat)

## Difficulty tiers (the synthetic data must span all three)

- **Tier A — entity overlap:** no case key, but records share an entity value (same email, or
  order_ref that joins to `orders`). Real resolution work, not a given foreign key.
- **Tier B — semantic only (HERO):** no shared entity at all. Linkable only by same-issue
  paraphrase + fuzzy customer name + temporal proximity. These prove the thesis.
- **Tier C — trivial:** a shared ticket id. Kept minimal; we do not rely on it.
- Plus **noise**: unrelated records that must NOT merge.

## Ground truth

`data/synthetic/ground_truth.json` maps every record_id -> its true case_id (or "noise"),
plus each case's true issue / root_cause / resolution / tier. This is how we **measure** that
keyless linking worked. It is evidence for the demo, never an input the pipeline reads.

## Stage decisions (post CoCo review, 2026-07-23)

1. Stage 1 normalize: `AI_EXTRACT` (array-of-keys syntax, not typed objects) + `AI_COMPLETE`.
2. Stage 2 resolve: dbt **Python (Snowpark)** model. Deterministic entity pass first
   (email/order_ref), then `EMBED_TEXT_768` + cosine similarity (>=0.85) for the keyless tier,
   then Union-Find connected components. **Precompute embeddings once.** Cortex Search is NOT
   used here (it is a runtime retrieval service) — it belongs in Stage 5 NL Q&A.
3. Stage 3 synthesize: one `AI_COMPLETE` per case returning **structured JSON** (wrap in
   `TRY_PARSE_JSON`), not `AI_AGG`. Keep one `AI_AGG` for a Stage 5 rollup summary where it fits.
4. Stage 4 enrich: plain SQL join to the structured seeds.
5. Stage 5: Streamlit (case explorer, root-cause rollup, recommended action). MCP/Slack
   delivery is a stretch, not core.

## Known limitations (state in README)

Full-refresh only (no incremental). LLM output can be malformed — handled with TRY_PARSE_JSON.
