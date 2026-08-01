-- Precision guard: no predicted case may contain records from two different true cases.
-- Returns offending predicted cases; passes only when empty (i.e. no false merges).
--
-- Any predicted case holding a tier D record is excluded, because tier D is built to
-- cause exactly this failure and is scored against its own floor in
-- assert_tier_d_precision_holds. Excluding the whole predicted case rather than the tier
-- D rows inside it is deliberate: a merge is a property of the predicted case, so half
-- of one cannot be judged here and the other half there.
with adversarial as (
    select distinct pred_case_id
    from {{ ref('eval_case_linkage') }}
    where tier = 'D'
)

select
    pred_case_id,
    count(distinct true_case_id) as n_true_cases
from {{ ref('eval_case_linkage') }}
where is_noise = 'false'
  and pred_case_id not in (select pred_case_id from adversarial)
group by pred_case_id
having count(distinct true_case_id) > 1
