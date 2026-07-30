-- Stage 3: collapse each case's records into ONE case-fact row.
-- One AI_COMPLETE call per case returns the synthesised fields as structured JSON
-- (more controllable than AI_AGG for multi-field output, per the CoCo review).
-- The core table. One row per case.
--
-- Two fields describe the cause, deliberately:
--   root_cause          free text, specific to this case, for reading a case
--   root_cause_category one of a fixed vocabulary, for counting cases
-- Free text alone does not aggregate: 225 cases produced 139 distinct root causes, and
-- "Potential bug in the order history feature" and "Defect in the app's order history
-- screen" are one driver split in two, which silently distorts any ranking built on it.
-- The vocabulary below is generic support-domain language rather than anything specific
-- to our synthetic issues, so it still applies when real data is swapped in. Extend it
-- here and the rollups follow automatically.
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
                || 'issue, timeline, resolved, root_cause, root_cause_category, resolution_path, sentiment. '
                || 'resolved must be a JSON boolean (true/false). '
                || 'sentiment must be exactly one of: negative, neutral, positive. '
                || 'issue = the normalized underlying problem. '
                || 'timeline = one or two sentences describing what happened, in order. '
                || 'root_cause = the most likely underlying cause, specific to this case. '
                || 'root_cause_category must be EXACTLY one of these strings. Classify by what '
                || 'FAILED, not by how the customer felt about it: '
                || '"Delivery failure" (parcel lost, late, or never arrived), '
                || '"Fulfilment error" (wrong, missing or damaged item shipped), '
                || '"Billing error" (charged twice, wrong amount, unexpected charge), '
                || '"Refund delay" (refund owed but not paid, or past its window), '
                || '"Payment processing failure" (payment declined, held, or in a mismatched state), '
                || '"Account access" (locked out, login, verification or trusted-device problems), '
                || '"Product defect" (the app or product itself crashes, syncs wrongly, or misbehaves), '
                || '"Returns or warranty policy" (a return or warranty request that policy blocks), '
                || '"Subscription management" (cancellation, renewal or confirmation not processed), '
                || '"Customer record error" (wrong address, phone or contact detail on file), '
                || '"Service handling" (the underlying fault is NOT the problem: the support process '
                || 'itself failed, through transfers, lost context, repeat contacts or unread notes), '
                || '"Other" (the cause is genuinely unclear from the records). '
                || 'Pick "Service handling" ONLY when the complaint is about how support handled the '
                || 'contact rather than about an underlying product, order or payment fault. If a '
                || 'concrete fault is identifiable, always name that fault instead. '
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
    -- Trust but verify: an LLM asked for one of twelve strings will occasionally return a
    -- thirteenth. Anything off-vocabulary collapses to 'Other' rather than quietly becoming
    -- a category of one, which is the exact failure this column exists to prevent.
    case
        when f:root_cause_category::varchar in (
            'Delivery failure', 'Fulfilment error', 'Billing error', 'Refund delay',
            'Payment processing failure', 'Account access', 'Product defect',
            'Returns or warranty policy', 'Subscription management', 'Customer record error',
            'Service handling', 'Other'
        ) then f:root_cause_category::varchar
        else 'Other'
    end                         as root_cause_category,
    f:resolution_path::varchar  as resolution_path,
    lower(f:sentiment::varchar)  as sentiment
from synthesised
