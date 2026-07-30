-- Stage 4: fuse the unstructured case facts with structured business metrics.
--
-- Grain is one row per case, and every structured value attached here must belong to
-- THAT case. An earlier version aggregated orders and CSAT to the CUSTOMER and joined on
-- customer_id, which was invisible while each customer had exactly one case but wrong as
-- soon as customers recur: a customer's whole lifetime order value was attached to every
-- one of their unresolved cases, so summing revenue_at_risk counted the same money once
-- per case (it inflated the total by ~1.9x). Orders and surveys are now matched to a
-- single case by time, so each one is counted exactly once.
with cf as (
    select * from {{ ref('fct_case_fact') }}
),

-- The order a case is about: the customer's most recent order placed before the case
-- opened. Cases with no prior order for that customer simply get no order.
order_candidates as (
    select
        cf.case_id,
        cf.first_ts,
        o.order_id,
        o.order_value,
        o.placed_ts,
        row_number() over (partition by cf.case_id order by o.placed_ts desc) as order_rank
    from cf
    join {{ ref('stg_orders') }} o
      on o.customer_id = cf.customer_id
     and o.placed_ts <= cf.first_ts
),
-- One order must not fund two cases. If two cases both point at the same order, it
-- belongs to the one that opened soonest after it was placed.
case_order as (
    select case_id, order_id, order_value
    from (
        select
            oc.*,
            row_number() over (
                partition by oc.order_id
                order by datediff('second', oc.placed_ts, oc.first_ts)
            ) as case_rank
        from order_candidates oc
        where oc.order_rank = 1
    )
    where case_rank = 1
),

-- The survey a case is about: submitted inside the case window (allowing a day of lag
-- for a survey that lands just after the last record), nearest first, one per case.
case_csat as (
    select case_id, score as csat_score
    from (
        select
            cf.case_id,
            cs.score,
            row_number() over (
                partition by cf.case_id order by cs.submitted_ts
            ) as survey_rank,
            row_number() over (
                partition by cs.survey_id order by cf.first_ts
            ) as claim_rank
        from cf
        join {{ ref('stg_csat_scores') }} cs
          on cs.customer_id = cf.customer_id
         and cs.submitted_ts between cf.first_ts and dateadd('hour', 24, cf.last_ts)
    )
    where survey_rank = 1 and claim_rank = 1
),

-- Agent metrics stay a per-agent average across the period: they describe the agent who
-- handled the case, not the case itself, so averaging them is the intended reading.
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
    -- Money is only "at risk" while the case is open, and only the order this case is
    -- about counts toward it.
    case when cf.resolved = false then coalesce(co.order_value, 0) else 0 end as revenue_at_risk,
    cc.csat_score,
    ca.fcr,
    ca.aht
from cf
left join case_order co on co.case_id = cf.case_id
left join case_csat cc  on cc.case_id = cf.case_id
left join case_agent ca on ca.case_id = cf.case_id
