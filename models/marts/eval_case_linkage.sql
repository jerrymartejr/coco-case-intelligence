-- Measurement: join Stage 2 assignments to the ground-truth key so linkage accuracy
-- is a queryable, tested artifact (not just a claim). Feeds the assert_* tests and the
-- agg_linkage_accuracy scoreboard.
--
-- `shape` matters as much as `tier`. Tier D's three shapes fail for different reasons,
-- so averaging them into one adversarial number would hide which of the resolver's
-- assumptions actually broke.
select
    m.record_id,
    m.tier,
    m.shape,
    m.is_noise,
    m.true_case_id,
    a.case_id as pred_case_id
from {{ ref('ground_truth_map') }} m
join {{ ref('int_case_assignments') }} a
    on a.record_id = m.record_id
