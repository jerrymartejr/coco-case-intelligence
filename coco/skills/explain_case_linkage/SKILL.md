---
name: explain_case_linkage
description: >-
  Explain WHY a set of records was judged to be one case, with the evidence. Use this
  whenever the user asks why records are grouped together, how the system knows two
  records are related, what linked them, or whether a grouping can be trusted: "why are
  these one case", "how do you know these are related", "show me the evidence", "what
  linked these records", "why is this PDF part of that case", "prove these belong
  together", "show the linkage for CASE_G007", "which records are in this case", "how was
  this case assembled", "was this case linked by an identifier or by meaning". Reads the
  persisted linkage graph in CASE_INTEL.ANALYTICS.INT_CASE_EDGES together with the
  records themselves, and narrates the actual signals rather than asserting a result.
---

# explain_case_linkage

Every other skill answers questions *about* cases. This one answers questions about how a
case came to exist at all, which is the part a sceptical person should be asking about,
because `case_id` appears in **no source record**. It is inferred.

## The tables

`CASE_INTEL.ANALYTICS.INT_CASE_EDGES` — one row per link the resolver made.

| column | meaning |
|---|---|
| `record_a`, `record_b` | the two records that were linked |
| `edge_type` | `email`, `order_ref`, `resolved_customer`, or `semantic` |
| `cosine_sim` | issue-text similarity; populated for `semantic` edges only |
| `hours_apart` | how far apart in time the two records were |
| `case_id` | the case the link belongs to |
| `same_case` | false if the episode-gap rule later cut this link |

`CASE_INTEL.ANALYTICS.INT_CASE_ASSIGNMENTS` — record to case, plus `match_method`
(`entity`, `semantic`, `entity+semantic`, `singleton`).

`CASE_INTEL.ANALYTICS.SEARCH_CORPUS` — the verbatim source text per record, plus channel,
customer name and timestamp.

## What each edge type actually means

Say it in these terms. The distinction is the whole point of the project.

- **`semantic`** — nothing was shared but a name token, closeness in time, and the meaning
  of the complaint. **No identifier existed.** This is the hard case and the one worth
  pointing at.
- **`email`** / **`order_ref`** — the two records carried the same address or the same
  order reference.
- **`resolved_customer`** — neither record named the other's identifier, but each resolved
  to the same customer through the `orders` table. Structured data doing the work.

## Steps

1. **Find the case.** If the user named one (`CASE_G007`), use it. If they described a
   problem instead, find it first:

   ```sql
   select case_id, issue, record_count, channels
   from CASE_INTEL.ANALYTICS.FCT_CASE_ENRICHED
   where issue ilike '%<their words>%'
   order by record_count desc
   limit 5;
   ```

   If they mentioned a record id (`esc_0003`), go through the assignment:
   `select case_id from CASE_INTEL.ANALYTICS.INT_CASE_ASSIGNMENTS where record_id = '...'`.

2. **Get the members and the evidence** in one pass:

   ```sql
   select r.record_id, r.channel, r.customer_name, r.occurred_ts, r.issue_text
   from CASE_INTEL.ANALYTICS.INT_CASE_ASSIGNMENTS a
   join CASE_INTEL.ANALYTICS.STG_RECORDS r on r.record_id = a.record_id
   where a.case_id = '<CASE_ID>'
   order by r.occurred_ts;

   select record_a, record_b, edge_type, round(cosine_sim, 3) as cosine_sim,
          round(hours_apart, 1) as hours_apart
   from CASE_INTEL.ANALYTICS.INT_CASE_EDGES
   where case_id = '<CASE_ID>' and same_case
   order by record_a, record_b;
   ```

3. **Narrate it, in this order.**
   - What the case is, and how many records in how many formats.
   - The records in time order: channel, when, and what each one said.
   - Then the links, one line each, in plain language. For example: *"esc_0003 (a PDF
     escalation form) was tied to chat_0007 by a shared surname, 13.4 hours apart, with an
     issue similarity of 0.732 — there was no order reference and no email address on
     either record."*
   - Whether the case is **fully keyless** (every edge `semantic`) or had an identifier to
     lean on. Check it, do not assume: `select count(*), count_if(edge_type = 'semantic')
     from ... where case_id = '...' and same_case`.

4. **Be honest about the limits when asked whether this can be trusted.** The method is
   measured, and it is measured to fail in one specific place. From
   `CASE_INTEL.ANALYTICS.AGG_LINKAGE_ACCURACY`: tiers A-C and the noise records score
   1.000, but they are generated under conditions the resolver needs, so they are a
   regression floor rather than a result. The adversarial tier D is the real number, and
   its `collision_keyless` shape scores **0.000** — two different customers who share a
   surname, write in the same hours and carry no identifier anywhere are merged into one
   case every time, because nothing in the text distinguishes them. Where those customers
   *do* carry identity evidence, the same shape scores 1.000. Say both.

5. **Never invent an edge.** If `int_case_edges` has no rows for the case, it is a
   single-record case: say that it was never linked to anything, rather than describing a
   link that does not exist.

## Following up

- "What are these records actually saying?" → `search_case_records`
- "How many cases like this?" → `ask_case_intelligence`
- "What is it costing us?" → `diagnose_top_drivers`
