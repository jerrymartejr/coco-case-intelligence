---
name: ask_case_intelligence
description: >-
  Answer ANY question about support cases, unresolved cases, revenue at risk, CSAT,
  root causes, agents or customers. Use this whenever the user asks how many, how much,
  which, or what about cases or the case data. ALWAYS query CASE_INTEL.ANALYTICS.FCT_CASE_ENRICHED
  (the Stage 4 table that has revenue_at_risk, csat_score, fcr and aht) or the agg_* rollups
  — never FCT_CASE_FACT, which lacks the business metrics. Answers are grounded in real rows.
---

# ask_case_intelligence

Turn a plain-English question into SQL over the case-intelligence tables and answer it,
grounded in the actual rows.

## Data
Query `CASE_INTEL.ANALYTICS`:
- `fct_case_enriched` — one row per case: `case_id, customer_id, issue, resolved, root_cause,
  root_cause_category, resolution_path, sentiment, channels, record_count, agents_involved,
  first_ts, last_ts, revenue_at_risk, csat_score, fcr, aht`.
  `root_cause` is free text specific to the case; `root_cause_category` is one of a fixed
  vocabulary. ALWAYS group and count on `root_cause_category` — grouping on the free-text
  `root_cause` splits one driver across several wordings and gives a wrong ranking.
- `agg_root_cause_daily` — `root_cause_category, case_date, case_count, revenue_at_risk,
  avg_csat, avg_hours_to_resolve, unresolved_count, example_root_cause`.
- `agg_agent_performance` — `agent_id, cases_handled, resolution_rate, positive_cases, negative_cases`.

## How to answer
1. Pick the smallest table that answers the question (rollups before the case table).
2. Write ONE SQL query and run it with the SQL tool. Prefer explicit aggregates.
3. Answer in one or two sentences, citing the numbers. Never invent values not in the result.
4. If the question is ambiguous, state the assumption you made.

## Examples
- "Which root cause is costing us the most this week?" -> sum `revenue_at_risk` by
  `root_cause_category`.
- "How many cases are still unresolved?" -> `count(*) where not resolved` on `fct_case_enriched`.
- "Who has the best resolution rate?" -> order `agg_agent_performance` by `resolution_rate`.
