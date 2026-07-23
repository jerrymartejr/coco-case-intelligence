-- Stage 1 normalize: chat JSON -> common schema via Cortex AI.
with raw as (
    select record_id, raw_content, received_ts
    from {{ ref('raw_chat') }}
),
extracted as (
    select
        record_id,
        received_ts,
        raw_content,
        {{ extract_common_fields('raw_content') }} as ex
    from raw
)
select
    record_id,
    'chat'::varchar as source_type,
    'chat'::varchar as channel,
    ex:customer_name::varchar                                             as customer_name,
    ex:customer_email::varchar                                            as customer_email,
    ex:order_ref::varchar                                                 as order_ref,
    coalesce(try_to_timestamp_ntz(ex:occurred_ts::varchar), received_ts)  as occurred_ts,
    ex:agent_id::varchar                                                  as agent_id,
    ex:issue_text::varchar                                                as issue_text,
    ex:resolution_text::varchar                                           as resolution_text,
    lower(ex:sentiment::varchar)                                          as sentiment,
    received_ts,
    raw_content
from extracted
