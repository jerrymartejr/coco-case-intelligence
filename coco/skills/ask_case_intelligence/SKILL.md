---
name: ask_case_intelligence
description: Answer a natural-language question about support cases by writing and running SQL over the case-intelligence marts, then giving a grounded answer with the numbers.
---

# ask_case_intelligence

Turn a plain-English question into SQL over the case-intelligence tables and answer it,
grounded in the actual rows.

## Data
Query `CASE_INTEL.ANALYTICS`:
- `fct_case_enriched` — one row per case: `case_id, customer_id, issue, resolved, root_cause,
  resolution_path, sentiment, channels, record_count, agents_involved, first_ts, last_ts,
  revenue_at_risk, csat_score, fcr, aht`.
- `agg_root_cause_daily` — `root_cause, case_date, case_count, revenue_at_risk, avg_csat,
  avg_hours_to_resolve, unresolved_count`.
- `agg_agent_performance` — `agent_id, cases_handled, resolution_rate, positive_cases, negative_cases`.

## How to answer
1. Pick the smallest table that answers the question (rollups before the case table).
2. Write ONE SQL query and run it with the SQL tool. Prefer explicit aggregates.
3. Answer in one or two sentences, citing the numbers. Never invent values not in the result.
4. If the question is ambiguous, state the assumption you made.

## Examples
- "Which root cause is costing us the most this week?" -> sum `revenue_at_risk` by `root_cause`.
- "How many cases are still unresolved?" -> `count(*) where not resolved` on `fct_case_enriched`.
- "Who has the best resolution rate?" -> order `agg_agent_performance` by `resolution_rate`.
