-- Stage 5 rollup: per agent. Feeds agent-performance views.
with exploded as (
    select
        f.value::varchar as agent_id,
        ce.case_id,
        ce.resolved,
        ce.sentiment
    from {{ ref('fct_case_enriched') }} ce,
        lateral flatten(input => ce.agents_involved) f
)
select
    agent_id,
    count(distinct case_id)                                             as cases_handled,
    round(avg(case when resolved then 1 else 0 end), 2)                 as resolution_rate,
    sum(case when sentiment = 'positive' then 1 else 0 end)             as positive_cases,
    sum(case when sentiment = 'negative' then 1 else 0 end)             as negative_cases
from exploded
where agent_id is not null
group by 1
