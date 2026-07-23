-- Structured: clean orders. Also the email <-> order bridge used in Stage 2.
select
    order_id,
    customer_id,
    customer_name,
    lower(email)                          as email,
    value::float                          as order_value,
    placed_ts,
    status
from {{ ref('orders') }}
