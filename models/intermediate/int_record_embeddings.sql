-- Stage 2, part 2: embed every record's normalized issue text, once.
--
-- This exists as its own model for two reasons. It is the only Cortex spend in Stage 2,
-- so computing it here means it is paid for once and read twice (the resolver links on
-- it, and anything downstream that wants to explain a link reads the same vectors rather
-- than re-embedding). And it separates the expensive, cacheable part of identity
-- resolution from the cheap, iterable part, so the linking logic can be changed and
-- rebuilt without spending on embeddings again.
--
-- Stored as an ARRAY rather than a VECTOR because the resolver is a Snowpark Python model
-- and reads the values back into plain Python. The warehouse-native alternative -- keeping
-- a VECTOR column and letting VECTOR_COSINE_SIMILARITY do the pair scoring in SQL -- is
-- the path to take if this ever has to run at a scale where the in-memory scan does not
-- fit; see the scaling note in int_linkage_graph.py.
--
-- issue_text is what is embedded, not raw_content: measured, embedding the raw record
-- lets channel formatting dominate the vector and collapses within-case similarity from
-- a 0.651 minimum to 0.241.
select
    record_id,
    snowflake.cortex.embed_text_768(
        '{{ var("cortex_embed_model") }}',
        issue_text
    )::array as embedding
from {{ ref('int_record_entities') }}
