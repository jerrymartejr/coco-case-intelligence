-- Recall guard: every non-noise true case must resolve to exactly ONE predicted case.
-- Returns offending cases; the test passes only when empty (i.e. all cases fully linked).
select
    true_case_id,
    count(distinct pred_case_id) as n_predicted_cases
from {{ ref('eval_case_linkage') }}
where is_noise = 'false'
group by true_case_id
having count(distinct pred_case_id) > 1
