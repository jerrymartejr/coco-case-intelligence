-- Stage 5 rollup: root-cause category x day. Feeds "diagnose top drivers".
--
-- Grouped on root_cause_category, not the free-text root_cause. Free text does not
-- aggregate: it produced 139 distinct causes across 225 cases, so the same driver appeared
-- several times under different wording and no ranking built on it was trustworthy. A
-- representative free-text cause is carried through as example_root_cause so the rollup
-- still reads like something a human wrote.
select
    root_cause_category,
    to_date(last_ts)                                        as case_date,
    count(*)                                                as case_count,
    sum(revenue_at_risk)                                    as revenue_at_risk,
    round(avg(csat_score), 2)                               as avg_csat,
    round(avg(datediff('hour', first_ts, last_ts)), 1)      as avg_hours_to_resolve,
    sum(case when resolved then 0 else 1 end)               as unresolved_count,
    max(root_cause)                                         as example_root_cause
from {{ ref('fct_case_enriched') }}
where root_cause_category is not null
group by 1, 2
