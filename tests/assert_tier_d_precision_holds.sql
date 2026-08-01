-- Adversarial guard: tier D precision must not fall below its measured floor.
--
-- This test is a different shape from the other two on purpose. Tiers A-C are asserted at
-- 100% because they are generated under the resolver's own assumptions and anything less
-- is a regression. Tier D breaks those assumptions deliberately, so the honest question
-- is not "is it perfect" but "has it got worse than what we published". The floor lives
-- in `tier_d_precision_floor` (dbt_project.yml) and is set to the measured result, never
-- above it. Whatever it is, the same number is published in the README.
--
-- Precision is counted over predicted cases: a predicted case holding records from two
-- different true cases is one false merge.
with per_predicted_case as (
    select
        pred_case_id,
        count(distinct true_case_id) as n_true_cases
    from {{ ref('eval_case_linkage') }}
    where tier = 'D'
    group by pred_case_id
),

scored as (
    select
        count(*)                                              as predicted_cases,
        sum(case when n_true_cases = 1 then 1 else 0 end)     as clean_cases
    from per_predicted_case
)

select
    predicted_cases,
    clean_cases,
    clean_cases / nullif(predicted_cases, 0) as tier_d_precision
from scored
where clean_cases / nullif(predicted_cases, 0) < {{ var('tier_d_precision_floor') }}
