-- Stage 2 output, half one: the record -> case map, with the resolved customer.
--
-- The resolver (int_linkage_graph) returns its assignments and the edges behind them in
-- one relation, because a dbt Python model can only return one. This projects out the
-- assignments; int_case_edges projects out the evidence. Everything downstream of
-- Stage 2 reads this model and is unaffected by that packaging.
select
    record_id,
    case_id,
    customer_id,
    -- What actually linked this record, read off its surviving edges:
    --   entity            a shared address, order reference or resolved customer
    --   semantic          a shared name token, proximity in time, and issue meaning
    --   entity+semantic   both, independently
    --   singleton         nothing; the record stands alone
    match_method
from {{ ref('int_linkage_graph') }}
where row_type = 'assignment'
