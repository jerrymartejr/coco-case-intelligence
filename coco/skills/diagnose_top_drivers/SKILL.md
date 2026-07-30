---
name: diagnose_top_drivers
description: Scan the root-cause rollup, identify the biggest driver(s) of revenue at risk and poor CSAT, and explain why with the supporting cases.
---

# diagnose_top_drivers

Find what is hurting most right now and explain it.

## Steps
1. Run this against `CASE_INTEL.ANALYTICS`:
   ```sql
   select root_cause_category,
          max(example_root_cause)   as example_root_cause,
          sum(revenue_at_risk)      as revenue_at_risk,
          sum(case_count)           as cases,
          sum(unresolved_count)     as unresolved,
          round(avg(avg_csat), 2)   as avg_csat,
          round(avg(avg_hours_to_resolve), 1) as avg_hours_to_resolve
   from agg_root_cause_daily
   group by root_cause_category
   order by revenue_at_risk desc, unresolved desc;
   ```
2. Take the top 1-2 drivers by `revenue_at_risk` (break ties by `unresolved`).
3. Pull the underlying cases for the top driver:
   ```sql
   select case_id, customer_id, issue, root_cause, resolved, revenue_at_risk, csat_score
   from fct_case_enriched
   where root_cause_category = :top_root_cause_category
   order by revenue_at_risk desc;
   ```
4. Name the driver by its category, and use `example_root_cause` or the per-case `root_cause`
   values to say concretely what is going wrong underneath it.
5. Explain in 2-3 sentences: the driver, the dollars at risk, how many cases / how many
   unresolved, and the CSAT impact. Ground every number in the query results.

Hand the top driver to `recommend_action` to turn the diagnosis into a concrete ask.
