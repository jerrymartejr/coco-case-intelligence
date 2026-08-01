-- Stage 1 normalize, fifth modality: PDF escalation forms.
--
-- The other four channels arrive as text or JSON and can be seeded directly. These are
-- real binary PDFs sitting in a Snowflake stage, read back with Cortex PARSE_DOCUMENT and
-- then put through exactly the same AI_COMPLETE extraction as every other channel. From
-- stg_records downward a document is indistinguishable from a chat message, which is the
-- point: one common schema over genuinely different modalities.
--
-- Populate the stage with `python scripts/upload_documents.py` before building.

with files as (
    select
        relative_path,
        last_modified
    from directory(@{{ target.database }}.raw.documents)
    where lower(relative_path) like '%.pdf'
),

parsed as (
    select
        relative_path,
        last_modified,
        snowflake.cortex.parse_document(
            @{{ target.database }}.raw.documents,
            relative_path,
            {'mode': 'LAYOUT'}
        ):content::varchar as raw_content
    from files
),

typed as (
    select
        -- The filename is the record id, which is how a document joins the ground-truth
        -- key alongside every other record.
        regexp_replace(relative_path, '\\.pdf$', '')                     as record_id,
        raw_content,
        -- The form states when it was raised. Parse that deterministically rather than
        -- depending on the LLM for the timestamp that Stage 2's link window relies on;
        -- fall back to the file's own metadata if the line is ever missing.
        coalesce(
            try_to_timestamp_ntz(
                regexp_substr(raw_content, 'Date raised:\\s*([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2})', 1, 1, 'e', 1)
            ),
            last_modified::timestamp_ntz
        )                                                                as received_ts
    from parsed
),

extracted as (
    select
        record_id,
        received_ts,
        raw_content,
        {{ extract_common_fields('raw_content') }} as ex
    from typed
)

select
    record_id,
    'document'::varchar as source_type,
    'document'::varchar as channel,
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
