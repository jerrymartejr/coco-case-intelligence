-- Structured: clean CSAT scores, keyed to order / customer.
select
    survey_id,
    nullif(order_ref, '')             as order_ref,
    customer_id,
    score::int                        as score,
    submitted_ts
from {{ ref('csat_scores') }}
