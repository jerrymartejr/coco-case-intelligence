-- Isolation guard: a noise record is unrelated to everything, so its predicted case must
-- contain nothing but itself. Returns offending predicted cases; passes only when empty.
--
-- This was measured and quoted in the README before it was ever enforced. It is enforced
-- now, because the number is only worth quoting if a build fails when it stops being true.
-- Noise names share no token with any customer and no noise address appears in orders, so
-- the resolver has nothing to link them on; if one merges, an assumption has slipped.
with noise_cases as (
    select distinct pred_case_id
    from {{ ref('eval_case_linkage') }}
    where is_noise = 'true'
)

select
    pred_case_id,
    count(*) as n_records
from {{ ref('eval_case_linkage') }}
where pred_case_id in (select pred_case_id from noise_cases)
group by pred_case_id
having count(*) > 1
