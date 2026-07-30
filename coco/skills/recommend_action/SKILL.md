---
name: recommend_action
description: Given a diagnosed driver, draft a concrete recommended action — the owning team, the affected cases and dollars at risk, and a specific ask.
---

# recommend_action

Turn a diagnosis into a decision-ready recommendation.

## Input
A root cause (from `diagnose_top_drivers`) or a question implying one.

## Steps
1. Gather the evidence for the driver:
   ```sql
   select case_id, customer_id, issue, root_cause, resolved, revenue_at_risk, csat_score, agents_involved
   from CASE_INTEL.ANALYTICS.fct_case_enriched
   where root_cause_category = :root_cause_category
   order by revenue_at_risk desc;
   ```
2. Produce a recommendation with EXACTLY these parts:
   - **Problem** — the driver category plus what is actually going wrong underneath it,
     taken from the per-case `root_cause` values, in one line.
   - **Impact** — total revenue at risk, number of cases, number unresolved, CSAT.
   - **Owning team** — infer from the root cause (billing -> Payments; delivery -> Logistics;
     login/MFA -> Identity; sync -> Platform; refund -> Finance Ops; wrong item -> Fulfilment).
   - **Ask** — one specific, actionable request tied to the evidence (e.g. "reverse the duplicate
     charges on these 2 cases and add a retry-idempotency guard to the payment gateway").
   - **Affected cases** — the `case_id`s.
3. Keep it tight and concrete. Every claim must trace to a queried number.

Pass the recommendation to `deliver_action` to route it.
