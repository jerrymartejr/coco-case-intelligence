-- Stage 5 rollup: root cause x day. Feeds "diagnose top drivers".
select
    root_cause,
    to_date(last_ts)                                        as case_date,
    count(*)                                                as case_count,
    sum(revenue_at_risk)                                    as revenue_at_risk,
    round(avg(csat_score), 2)                               as avg_csat,
    round(avg(datediff('hour', first_ts, last_ts)), 1)      as avg_hours_to_resolve,
    sum(case when resolved then 0 else 1 end)               as unresolved_count
from {{ ref('fct_case_enriched') }}
where root_cause is not null
group by 1, 2
