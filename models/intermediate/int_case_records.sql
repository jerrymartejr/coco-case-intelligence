-- Stage 2 output: every record joined to its resolved case_id, ready to collapse.
select
    a.case_id,
    a.customer_id,
    a.match_method,
    r.record_id,
    r.source_type,
    r.channel,
    r.occurred_ts,
    r.agent_id,
    r.customer_name,
    r.issue_text,
    r.resolution_text,
    r.sentiment
from {{ ref('int_record_entities') }} r
join {{ ref('int_case_assignments') }} a
    on r.record_id = a.record_id
