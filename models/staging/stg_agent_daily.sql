-- Structured: clean agent daily metrics (AHT, FCR, occupancy, CSAT).
select
    agent_id,
    metric_date,
    aht::float                as aht,
    fcr::float                as fcr,
    occupancy::float          as occupancy,
    avg_csat::float           as avg_csat
from {{ ref('agent_daily_metrics') }}
