# Case Intelligence — shared contract

One document every tool and teammate builds against (Cursor, CoCo, Claude Code, humans).
CoCo Hackathon 2026, Track 2 (Unstructured Data Intelligence). Domain: customer support / BPO.
Synthetic data only. Grain: one row per **case**. Output must be **actionable**.

## Thesis (do not dilute)

The product is **linking records that share no key** into a single case. Records arrive
across channels (chat, email, QA note, CSAT, PDF escalation form) describing the same issue for the same customer
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
| root_cause       | STRING    | synthesised root cause, free text, specific to the case | Stage 3  |
| root_cause_category | STRING | one of a fixed vocabulary — **group and count on this**, not on the free text | Stage 3 |
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
- **PDF documents** — real binary files in the Snowflake stage `RAW.DOCUMENTS`, not seeds.
  Read back with `SNOWFLAKE.CORTEX.PARSE_DOCUMENT` in `stg_documents`, which derives
  `record_id` from the filename and parses `Date raised:` for the timestamp, then feeds the
  same extraction as every other channel. Upload with `scripts/upload_documents.py`.

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
- **Tier D — adversarial:** the tier that exists so the result is not self-fulfilling.
  Tiers A-C are generated under invariants the resolver happens to need (unique surnames,
  a customer's cases far apart in time), so a perfect score on them measures the
  generator. Tier D breaks those invariants deliberately, at rates taken from the
  reference data in `docs/realism-report.md`, in three shapes:
  - *collision_with_identity* — two different customers with the SAME surname contact
    support in the same window about the SAME issue. Nothing in the text separates them;
    only the structured side does, which is where orders stop being enrichment and start
    being evidence. On half of these the address on one record is corrupted so the email
    bridge misses it.
  - *collision_keyless* — the same collision with no identifier anywhere and different
    issues, leaving the cosine floor alone against a shared surname.
  - *same_customer_in_window* — one customer, two separate problems opened close
    together, testing whether a shared email fuses two episodes.
  Tier D is **scored separately and expected to be imperfect**. Tiers A-C stay at 100% as
  a regression floor. Tier D names are disjoint from the main pool at the token level, so
  it can only contaminate itself; that containment is a stated limitation.
- Plus **noise**: unrelated records that must NOT merge.

## Ground truth

`data/synthetic/ground_truth.json` maps every record_id -> its true case_id (or "noise"),
plus each case's true issue / root_cause / resolution / tier. This is how we **measure** that
keyless linking worked. It is evidence for the demo, never an input the pipeline reads.

## Stage decisions (post CoCo review, 2026-07-23)

1. Stage 1 normalize: `AI_COMPLETE` returning structured JSON. (`AI_EXTRACT` was the original
   plan; its return shape was fiddlier to depend on, so it is not used.)
2. Stage 2 resolve: dbt **Python (Snowpark)** model. Deterministic entity pass first
   (email/order_ref/resolved customer), then `EMBED_TEXT_768` for the keyless tier, then
   Union-Find connected components. **Precompute embeddings once.** Cortex Search is NOT
   used here (it is a runtime retrieval service) — it belongs in Stage 5 NL Q&A.
   Embeddings are persisted in their own model (`int_record_embeddings`) so they are paid
   for once and read by both the linker and anything that later explains a link. The
   resolver returns the **whole graph** — assignments AND the edges behind them — in one
   relation, projected apart by `int_case_assignments` and `int_case_edges`; a dbt Python
   model can only return one relation, and the edges are the evidence the thesis rests on.
   Candidate pairs come from inverted indexes on the gate keys rather than a full pairwise
   scan: roughly 3,000 candidates against the 188,191 pairs a full scan over 614 records
   would visit, and the same link set by construction.
   Five properties of the link rule matter, all measured on the current corpus:
   - **The deterministic pass is time-gated** (`TIME_WINDOW_HOURS = 72`). A case is a bounded
     episode, so a shared email or a shared resolved customer only links records inside the
     same window. Without the gate a returning customer's separate cases fuse into one.
   - **A case is also bounded by silence** (`MAX_EPISODE_GAP_HOURS = 24`). The window bounds
     one edge; it does not bound a component, because Union-Find chains transitively. A
     component is cut wherever consecutive records fall silent for longer than a working
     day. This is a stated assumption, not a fitted number: Tier D plants repeat episodes
     on both sides of it to measure what it costs.
   - **Components refuse to merge when they disagree about the customer.** Identity is
     tracked on the component, not the record, so a case resolving to CUST_012 can never
     absorb one resolving to CUST_047 however similar the text. This is the only thing that
     separates two people who share a surname and complain about the same thing in the same
     hour, and it is why the structured side is evidence rather than enrichment.
   - **A surname the orders table shows belongs to two customers is not identifying.** A
     pair whose only shared name token is ambiguous needs a second signal to link. Measured:
     no change to Tier A/B/C/noise, and Tier D's corrupted-identity precision 0.33 → 1.00.
   - **`SIM_FLOOR = 0.62` is a relevance floor, not a separator.** Within-case pairs and
     different-issue pairs overlap in cosine (within-case min 0.651; different-issue p95
     0.808), so no cutoff separates them. The **surname token plus the 72h window do the
     separating**; the floor only rejects plainly unrelated content. Identity and time are
     the primary signals, not semantic similarity — and the name token is never dropped,
     since same-issue pairs from different customers sit at a median cosine of 0.897.
   Rejected on measurement: refusing a link when two records carry conflicting given names.
   It separates colliding surnames, but display-name divergence means a customer's own
   records conflict too — Tier B recall fell from 1.000 to 0.893 and Tier C to 0.786.
3. Stage 3 synthesize: one `AI_COMPLETE` per case returning **structured JSON** (wrap in
   `TRY_PARSE_JSON`), not `AI_AGG`. Keep one `AI_AGG` for a Stage 5 rollup summary where it fits.
   Cause is emitted twice on purpose: `root_cause` free text for reading one case, and
   `root_cause_category` from a fixed twelve-item vocabulary for counting many. Free text alone
   does not aggregate — it produced 139 distinct causes across 225 cases, splitting single
   drivers across wordings and distorting every ranking built on it. Anything the model returns
   outside the vocabulary is forced to `Other` in SQL. The list is generic support-domain
   language, not tailored to our synthetic issues, so it survives real data; extend it in
   `models/marts/fct_case_fact.sql` and the rollups follow.
4. Stage 4 enrich: plain SQL join to the structured seeds.
5. Stage 5: retrieval + agents. `search_corpus` is a RECORD-grain mart, and a post-hook
   creates the `CASE_RECORD_SEARCH` Cortex Search service over it. This is where Cortex
   Search always belonged: linking records at build time is a batch problem and uses
   embeddings directly (Stage 2), while answering a question about them later is a runtime
   retrieval problem. Every hit carries its case_id and the case's derived attributes, so
   retrieval and analysis join in one step. Five CoCo skills sit on top: search (retrieval),
   ask (aggregates), diagnose, recommend, deliver. Streamlit shows the same visually.
   MCP/Slack delivery is a stretch, not core.

## Known limitations (state in README)

Full-refresh only (no incremental). LLM output can be malformed — handled with TRY_PARSE_JSON.
