-- Extraction health: Stage 1's failure mode is silence, so it gets a test.
--
-- Every staging model wraps the model output in TRY_PARSE_JSON, which is what stops one
-- malformed response failing a build. The cost is that a malformed response instead
-- returns NULL for every extracted field, and the record travels on into Stage 2 with no
-- name, no address and no issue text, where it quietly fails to link. Nothing raises.
--
-- The bound is deliberately loose. This is not a quality gate on the model's judgement;
-- it is a tripwire for the catastrophic case, where a model substitution or a prompt
-- change stops returning parseable JSON at all and the null rate goes to tens of percent.
-- A handful of nulls in a corpus this size is ordinary LLM variance.
with health as (
    select
        count(*)                                            as records,
        sum(case when issue_text is null then 1 else 0 end) as unextracted
    from {{ ref('stg_records') }}
)

select
    records,
    unextracted,
    unextracted / nullif(records, 0) as unextracted_rate
from health
where unextracted / nullif(records, 0) > {{ var('max_unextracted_rate') }}
