-- Stage 3: collapse each case's records into ONE case-fact row.
-- One AI_COMPLETE call per case returns the synthesised fields as structured JSON
-- (more controllable than AI_AGG for multi-field output, per the CoCo review).
-- The core table. One row per case.
with case_records as (
    select
        case_id,
        any_value(customer_id)                        as customer_id,
        count(*)                                      as record_count,
        array_agg(distinct channel)                   as channels,
        array_agg(distinct agent_id)                  as agents_involved,
        min(occurred_ts)                              as first_ts,
        max(occurred_ts)                              as last_ts,
        listagg(
            '[' || channel || ' @ ' || to_varchar(occurred_ts) || '] '
            || coalesce(issue_text, '')
            || case when resolution_text is not null then ' -> ' || resolution_text else '' end,
            '\n'
        ) within group (order by occurred_ts)         as records_blob
    from {{ ref('int_case_records') }}
    group by case_id
),
synthesised as (
    select
        case_id,
        customer_id,
        record_count,
        channels,
        agents_involved,
        first_ts,
        last_ts,
        try_parse_json(regexp_replace(
            ai_complete('mistral-large2',
                'You summarize a single customer-support CASE assembled from multiple records. '
                || 'Return ONLY a JSON object (no prose, no markdown, no code fences) with EXACTLY these keys: '
                || 'issue, timeline, resolved, root_cause, resolution_path, sentiment. '
                || 'resolved must be a JSON boolean (true/false). '
                || 'sentiment must be exactly one of: negative, neutral, positive. '
                || 'issue = the normalized underlying problem. '
                || 'timeline = one or two sentences describing what happened, in order. '
                || 'root_cause = the most likely underlying cause. '
                || 'resolution_path = how it was resolved, or null if unresolved. '
                || 'Records for this case:' || chr(10) || records_blob
            ), '```json|```', ''
        )) as f
    from case_records
)
select
    case_id,
    customer_id,
    f:issue::varchar            as issue,
    channels,
    record_count,
    agents_involved,
    first_ts,
    last_ts,
    f:timeline::varchar         as timeline,
    f:resolved::boolean         as resolved,
    f:root_cause::varchar       as root_cause,
    f:resolution_path::varchar  as resolution_path,
    lower(f:sentiment::varchar)  as sentiment
from synthesised
