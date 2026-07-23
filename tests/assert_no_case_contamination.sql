-- Precision guard: no predicted case may contain records from two different true cases.
-- Returns offending predicted cases; passes only when empty (i.e. no false merges).
select
    pred_case_id,
    count(distinct true_case_id) as n_true_cases
from {{ ref('eval_case_linkage') }}
where is_noise = 'false'
group by pred_case_id
having count(distinct true_case_id) > 1
