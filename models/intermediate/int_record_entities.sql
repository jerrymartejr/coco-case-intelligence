-- Stage 2, part 1: expose the per-record signals used for identity resolution.
-- The heavy matching (name-token overlap, embeddings, connected components) happens
-- in the Snowpark model int_case_assignments; this model just surfaces clean signals.
select
    record_id,
    source_type,
    channel,
    occurred_ts,
    agent_id,
    customer_name,
    lower(nullif(trim(customer_email), '')) as email,
    upper(nullif(trim(order_ref), ''))      as order_ref,
    issue_text,
    resolution_text,
    sentiment
from {{ ref('stg_records') }}
