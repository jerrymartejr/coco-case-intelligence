-- Stage 4: fuse the unstructured case facts with structured business metrics.
-- Structured tables are pre-aggregated to their join grain first, so the joins
-- cannot fan out the one-row-per-case grain.
with cf as (
    select * from {{ ref('fct_case_fact') }}
),
order_val as (
    select customer_id, sum(order_value) as customer_order_value
    from {{ ref('stg_orders') }}
    group by customer_id
),
csat as (
    select customer_id, avg(score) as avg_csat_score
    from {{ ref('stg_csat_scores') }}
    group by customer_id
),
agent_metrics as (
    select agent_id, avg(fcr) as fcr, avg(aht) as aht
    from {{ ref('stg_agent_daily') }}
    group by agent_id
),
case_agent as (
    select
        cf.case_id,
        avg(am.fcr) as fcr,
        avg(am.aht) as aht
    from cf,
        lateral flatten(input => cf.agents_involved) f
        join agent_metrics am on am.agent_id = f.value::varchar
    group by cf.case_id
)
select
    cf.case_id,
    cf.customer_id,
    cf.issue,
    cf.channels,
    cf.record_count,
    cf.agents_involved,
    cf.first_ts,
    cf.last_ts,
    cf.timeline,
    cf.resolved,
    cf.root_cause,
    cf.resolution_path,
    cf.sentiment,
    case when cf.resolved = false then coalesce(ov.customer_order_value, 0) else 0 end as revenue_at_risk,
    round(cs.avg_csat_score)                                                          as csat_score,
    ca.fcr,
    ca.aht
from cf
left join order_val ov on ov.customer_id = cf.customer_id
left join csat cs      on cs.customer_id = cf.customer_id
left join case_agent ca on ca.case_id = cf.case_id
