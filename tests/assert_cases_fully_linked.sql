-- Recall guard: every non-noise true case must resolve to exactly ONE predicted case.
-- Returns offending cases; the test passes only when empty (i.e. all cases fully linked).
--
-- Tier A, B and C only. Those tiers are generated under invariants the resolver needs,
-- which is precisely why they make a good regression floor and a poor headline: they
-- must not get worse, but they were never going to be hard. Tier D deliberately breaks
-- those invariants and its recall is reported as measured in agg_linkage_accuracy rather
-- than asserted, because demanding perfection there would only mean planting easier
-- adversarial cases.
select
    true_case_id,
    count(distinct pred_case_id) as n_predicted_cases
from {{ ref('eval_case_linkage') }}
where is_noise = 'false'
  and tier <> 'D'
group by true_case_id
having count(distinct pred_case_id) > 1
