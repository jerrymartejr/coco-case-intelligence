-- Stage 5, retrieval: the searchable corpus behind the Cortex Search service.
--
-- The other marts are aggregates: one row per case, one row per driver. This one is
-- deliberately at RECORD grain, because retrieval and reasoning want different things.
-- When someone asks "has anyone else reported the app dying on order history", the useful
-- answer is the actual customer messages, not a rolled-up count -- and once a record is
-- retrieved, the case it belongs to and everything Stages 3 and 4 derived about that case
-- come with it as attributes.
--
-- The post-hook creates the Cortex Search service over this table. Search is a runtime
-- retrieval service, which is exactly why it belongs here in Stage 5 and not in Stage 2:
-- linking records at build time is a batch problem, answering a question about them later
-- is a retrieval problem.
{{
    config(
        materialized='table',
        post_hook=[
            "create or replace cortex search service {{ this.database }}.{{ this.schema }}.case_record_search
               on searchable_text
               attributes record_id, case_id, channel, customer_name, occurred_ts,
                          root_cause_category, resolved, revenue_at_risk
               warehouse = {{ target.warehouse }}
               target_lag = '1 day'
               as (select searchable_text, record_id, case_id, channel, customer_name,
                          occurred_ts, root_cause_category, resolved, revenue_at_risk
                   from {{ this }})"
        ]
    )
}}

with raw_text as (
    {% set sources = ['stg_chat', 'stg_email', 'stg_qa_notes', 'stg_csat', 'stg_documents'] %}
    {% for src in sources %}
    select record_id, source_type, raw_content from {{ ref(src) }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

select
    r.record_id,
    a.case_id,
    n.channel,
    n.customer_name,
    n.occurred_ts,
    -- Case-level context travels with every record, so a retrieved message can be
    -- answered about without a second round trip.
    c.root_cause_category,
    c.resolved,
    c.revenue_at_risk,
    -- What actually gets indexed. The channel and customer are prepended so a query can
    -- match on them as text as well as filter on them as attributes, and the raw source
    -- text is included verbatim rather than the AI's summary of it: retrieval should find
    -- what the customer actually wrote.
    n.channel || ' from ' || coalesce(n.customer_name, 'unknown') || ': '
        || coalesce(n.issue_text, '') || chr(10) || r.raw_content as searchable_text
from raw_text r
join {{ ref('stg_records') }} n            on n.record_id = r.record_id
join {{ ref('int_case_assignments') }} a   on a.record_id = r.record_id
left join {{ ref('fct_case_enriched') }} c on c.case_id = a.case_id
