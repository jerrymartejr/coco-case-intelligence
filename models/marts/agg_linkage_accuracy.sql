-- Stage 5: the scoreboard. "How do we know the linking is right?" as a table, per tier
-- and per adversarial shape, instead of a number in a README that a reader has to trust.
--
-- The ground truth this scores against is generator output. The pipeline never reads it:
-- it enters the warehouse as a seed, is joined to the predictions here, and is used
-- nowhere upstream. That is the only reason these numbers mean anything.
--
-- Read the rows in two groups. Tiers A, B and C are generated under the resolver's own
-- assumptions, so they are a regression floor and their 100% is not a result. Tier D
-- breaks those assumptions on purpose, one per shape, and IS the result.
with scored as (
    select * from {{ ref('eval_case_linkage') }}
),

-- Recall: a true case is linked when all of its records land in one predicted case.
per_true_case as (
    select
        tier,
        shape,
        true_case_id,
        count(*)                        as records,
        count(distinct pred_case_id)    as predicted_cases
    from scored
    where is_noise = 'false'
    group by 1, 2, 3
),
recall as (
    select
        tier,
        shape,
        count(*)                                            as true_cases,
        sum(case when predicted_cases = 1 then 1 else 0 end) as fully_linked,
        sum(records)                                        as records
    from per_true_case
    group by 1, 2
),

-- Precision: a predicted case is clean when everything in it came from one true case.
per_predicted_case as (
    select
        tier,
        shape,
        pred_case_id,
        count(distinct true_case_id) as true_cases
    from scored
    where is_noise = 'false'
    group by 1, 2, 3
),
precision_ as (
    select
        tier,
        shape,
        count(*)                                        as predicted_cases,
        sum(case when true_cases > 1 then 1 else 0 end) as false_merges
    from per_predicted_case
    group by 1, 2
),

-- Noise is scored on isolation instead: an unrelated record must end up in a predicted
-- case containing nothing but itself.
predicted_case_size as (
    select pred_case_id, count(*) as n_records
    from scored
    group by 1
),
noise as (
    select
        'noise'                                             as tier,
        'noise'                                             as shape,
        count(*)                                            as true_cases,
        sum(case when z.n_records = 1 then 1 else 0 end)    as fully_linked,
        count(*)                                            as records,
        count(distinct s.pred_case_id)                      as predicted_cases,
        0                                                   as false_merges
    from scored s
    join predicted_case_size z on z.pred_case_id = s.pred_case_id
    where s.is_noise = 'true'
),

combined as (
    select
        r.tier, r.shape, r.true_cases, r.fully_linked, r.records,
        p.predicted_cases, p.false_merges
    from recall r
    join precision_ p on p.tier = r.tier and p.shape = r.shape
    union all
    select tier, shape, true_cases, fully_linked, records, predicted_cases, false_merges
    from noise
)

select
    tier,
    shape,
    true_cases,
    fully_linked,
    records,
    predicted_cases,
    false_merges,
    round(fully_linked / nullif(true_cases, 0), 4)                            as recall,
    round((predicted_cases - false_merges) / nullif(predicted_cases, 0), 4)   as precision
from combined
order by case when tier = 'noise' then 'Z' else tier end, shape
