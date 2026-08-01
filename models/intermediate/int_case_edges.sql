-- Stage 2 output, half two: the evidence. One row per link the resolver made, naming the
-- two records, why they were joined, and how far apart they were.
--
-- This is the relationship graph the whole thesis rests on. Without it, "these five
-- records across five formats are one case" is an assertion; with it, every case can be
-- taken apart and shown: linked to esc_0007 by a shared surname token, 14 hours apart,
-- issue similarity 0.71, and no identifier in sight.
--
-- Edges are not a clean partition of the cases. A pair can be linked by two independent
-- signals and appear twice, once as `email` and once as `semantic`, which is exactly the
-- corroboration worth seeing. And an edge whose endpoints ended up in different cases
-- (same_case = false) is one the episode-gap cut severed after the fact: the records were
-- close enough to link but the case they were heading for had a silence in the middle.
select
    record_a,
    record_b,
    -- email | order_ref | resolved_customer | semantic
    edge_type,
    -- Populated for semantic edges only; the deterministic signals do not score.
    cosine_sim,
    hours_apart,
    case_id,
    same_case
from {{ ref('int_linkage_graph') }}
where row_type = 'edge'
