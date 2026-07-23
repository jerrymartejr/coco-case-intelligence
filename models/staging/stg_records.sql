-- Stage 1 output: the normalized_records table. UNION ALL of every source in the
-- common schema. One row per raw record, format-agnostic from here on.
{% set sources = ['stg_chat', 'stg_email', 'stg_qa_notes', 'stg_csat'] %}

{% for src in sources %}
select
    record_id,
    source_type,
    channel,
    customer_name,
    customer_email,
    order_ref,
    occurred_ts,
    agent_id,
    issue_text,
    resolution_text,
    sentiment,
    received_ts
from {{ ref(src) }}
{% if not loop.last %}union all{% endif %}
{% endfor %}
