---
name: search_case_records
description: >-
  Find the actual customer records behind a question by searching what people wrote, across
  chat, email, QA notes, CSAT verbatims and PDF escalation forms. Use this whenever the user
  asks to find, search, show, or look for records, messages, complaints or documents; asks
  "has anyone else reported X", "what are customers saying about X", "show me the emails
  about X", or "find the escalation forms for X"; or asks anything the aggregate tables
  cannot answer because the answer is in the text rather than in a count. Retrieves with the
  CASE_RECORD_SEARCH Cortex Search service, then answers from the retrieved text.
---

# search_case_records

Retrieval first, then reasoning. The other skills query aggregates; this one finds the
source records and answers from what they actually say.

## When to use this instead of ask_case_intelligence

| Question | Skill |
|---|---|
| "How many cases are unresolved?" | `ask_case_intelligence` — it is a count |
| "What are customers actually saying about the app crashing?" | this one — the answer is in the text |
| "Find the escalation forms raised for account lockouts" | this one — retrieval over documents |
| "Which driver costs the most?" | `diagnose_top_drivers` |

## The service

`CASE_INTEL.ANALYTICS.CASE_RECORD_SEARCH` indexes **one row per raw record**, every record
in the corpus, across all five source formats. Every hit carries the case it belongs to and what the
pipeline concluded about that case, so retrieval and analysis join up in one step.

Searchable text: the record's channel, customer name, extracted issue, and the **verbatim
source content** — the chat transcript, the email body, the QA note, the survey comment, or
the text Cortex parsed out of the PDF.

Attributes available for filtering and display:
`record_id`, `case_id`, `channel`, `customer_name`, `occurred_ts`, `root_cause_category`,
`resolved`, `revenue_at_risk`.

`channel` is one of: `chat`, `email`, `qa_note`, `survey`, `document`.

## Steps

1. Search. Put the user's question in `query` in natural language; do not reduce it to
   keywords, the service does semantic matching and reranking.

   ```sql
   select snowflake.cortex.search_preview(
       'CASE_INTEL.ANALYTICS.CASE_RECORD_SEARCH',
       '{
          "query": "<the user question, in their words>",
          "columns": ["record_id","channel","customer_name","case_id",
                      "root_cause_category","resolved","revenue_at_risk","searchable_text"],
          "limit": 8
        }'
   ) as hits;
   ```

2. Filter when the question names a format or a state. Filters go inside the JSON:

   ```json
   "filter": {"@eq": {"channel": "document"}}
   "filter": {"@eq": {"resolved": false}}
   "filter": {"@and": [{"@eq": {"channel": "email"}},
                       {"@eq": {"root_cause_category": "Refund delay"}}]}
   ```

3. Answer from what was retrieved. Quote or closely paraphrase the customer's own words for
   two or three of the strongest hits, and name the `record_id` and `channel` for each so the
   answer can be checked.

4. If the retrieved records span several cases, say so and give the case ids. Cases are how
   this system groups records that share no key, so "these five messages are actually three
   cases" is usually the insight.

5. Never invent a record. If retrieval returns nothing relevant, say that and suggest a
   broader phrasing.

## Following up

If the user then asks about scale or cost ("how much is that worth", "how many like this"),
hand off: `ask_case_intelligence` for counts and totals, `diagnose_top_drivers` if they want
the ranked drivers, `recommend_action` to turn it into something to do.
