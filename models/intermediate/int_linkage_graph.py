"""
Stage 2 — identity resolution. The centerpiece: link records that share NO key into one
case_id, then assign each case a customer identity.

This model emits the whole linkage graph: the record -> case assignment AND the edges
that produced it. A dbt Python model can only return one relation, so both come back in
one tall relation tagged by `row_type`, and two thin SQL models (int_case_assignments,
int_case_edges) project them apart. The alternative -- a second Python model recomputing
the same thing -- would either duplicate every rule in this file or pay for the
embeddings twice, and the edges are the point: they are the evidence for *why* three
records in three formats are one case, and without them that claim can only be asserted.

Approach:
  1. Candidate blocking. Both passes below only ever link records that share something
     (an email, an order reference, a resolved customer, or a name token), so the
     candidates are generated from inverted indexes on exactly those keys instead of
     from a full pairwise scan. See _pairs_sharing_a_key.
  2. Deterministic pass: edges between candidate records that share a hard signal
     (same email, same order_ref, or both resolving to the same customer via orders)
     AND fall inside the same link window. The window matters: a returning customer is
     not one endless case, so a hard identifier only fuses records from the same episode.
  3. Semantic pass (the keyless / thesis tier): for candidate pairs close in time that
     share a fuzzy name token, add an edge when their issue-text embeddings are not
     unrelated (cosine >= SIM_FLOOR). A shared name token only counts if the orders table
     does not show that name belonging to two different customers.
  4. Connected components (Union-Find) over all edges, with two bounds on what a
     component is allowed to become: CONTRADICTION and EPISODE GAP, both below.
  5. Customer resolution: key-based first; fall back to a fuzzy name bridge to orders so
     keyless cases can still tie to structured metrics downstream.

Pure-Python (no pandas/numpy) so it runs in the Snowpark stored-proc sandbox.
Deterministic: candidate pairs are iterated in sorted order and components are labeled by
their smallest record_id, so case ids are stable across runs.

Scaling. Blocking takes the pair count from O(N^2) to O(sum of block^2), where a block is
the set of records sharing one key. Block size here is bounded by how often a name token
or an address repeats, which is small; a token that is not identifying (an extraction
artefact such as a literal "customer") would produce one large block and degrade toward
the old cost, which is why the cheap gates run before the cosine comparison. Beyond the
scale where the vectors fit in the sandbox's memory, the same rules express directly in
SQL: keep int_record_embeddings as a VECTOR column and score candidate pairs with
VECTOR_COSINE_SIMILARITY in a join over the same block keys.
"""

import json
import re

from snowflake.snowpark.types import (
    BooleanType,
    DoubleType,
    StringType,
    StructField,
    StructType,
)

# Similarity FLOOR, not a separator. Measured on the corpus, embedding the extracted
# issue_text:
#   within-case pairs        min 0.651, p05 0.743   (same issue across channel registers)
#   different-issue pairs    p95 0.808, p99 0.847   (different case, different problem)
# Those distributions overlap, so no cutoff separates them: raising the floor to 0.82
# drops 48 of 170 true cases, and lowering it far enough to catch them admits unrelated
# content. Cosine alone therefore cannot decide a link on this text. What does the
# separating work is the pairing of a shared surname token with the time window below;
# the floor's job is only to reject pairs whose content is plainly unrelated. Chosen at
# 0.62 to sit clear of the 0.675 worst-case connectivity bottleneck, so ordinary
# variation in Stage 1's extraction between builds cannot break linkage.
# Tried and rejected: embedding raw_content instead (channel formatting dominates the
# vector, within-case min collapses to 0.241) and issue_text + resolution_text (worse).
SIM_FLOOR = 0.62

# No edge may span more than this, however strong the identifier behind it.
TIME_WINDOW_HOURS = 72

# And no CASE may contain a silence longer than this. The window above bounds one edge;
# it does not bound a component, because Union-Find chains transitively: A-B at 60h and
# B-C at 60h puts A and C in one case 120h apart. That chaining is usually right -- an
# episode does run on -- but unbounded it lets a busy customer's separate problems fuse
# into a single case through a shared address. So a component is cut wherever consecutive
# records fall silent for longer than this.
#
# This is a stated modelling assumption, not a number fitted to the corpus: a support
# episode is contiguous, and a working day of silence ends it. Tier D measures what the
# assumption costs, by planting repeat episodes on both sides of it.
MAX_EPISODE_GAP_HOURS = 24

_DETERMINISTIC_EDGES = ("email", "order_ref", "resolved_customer")


def _tokens(name):
    if not name:
        return set()
    return set(re.findall(r"[a-z]{3,}", str(name).lower()))


def _to_vec(v):
    if v is None:
        return None
    # An ARRAY column comes back from Snowpark as a JSON string or as a sequence
    # depending on context, and a malformed embedding must degrade to "no vector"
    # rather than fail the whole build.
    if isinstance(v, str):
        try:
            return [float(x) for x in json.loads(v)]
        except (ValueError, TypeError):
            return None
    try:
        return [float(x) for x in v]
    except (ValueError, TypeError):
        return None


def _cosine(a, b):
    if not a or not b:
        return 0.0
    # strict: two vectors of different width mean the embedding model changed under us,
    # which must fail loudly here rather than silently truncate to the shorter one and
    # return a plausible number. _to_vec is the layer that degrades gracefully.
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / ((na * nb) + 1e-9)


def _index(values):
    """key -> the records carrying it. Keys that are None are not keys."""
    index = {}
    for record_id, key in values.items():
        if key:
            index.setdefault(key, []).append(record_id)
    return index


def _index_tokens(tokens_by_record):
    """token -> the records whose customer name carries it."""
    index = {}
    for record_id, tokens in tokens_by_record.items():
        for token in tokens:
            index.setdefault(token, []).append(record_id)
    return index


def _pairs_sharing_a_key(*indexes):
    """Candidate pairs: every unordered pair of records that share at least one key.

    This is the whole of the blocking step. Both passes below already require the pair to
    share one of these keys before they will link it, so every pair the old full pairwise
    scan could have linked shares a key, sits in that key's bucket, and is generated here.
    Blocking therefore only removes pairs that could never have linked.
    """
    pairs = set()
    for index in indexes:
        for members in index.values():
            if len(members) < 2:
                continue
            ordered = sorted(members)
            for i, a in enumerate(ordered):
                for b in ordered[i + 1:]:
                    pairs.add((a, b))
    return sorted(pairs)


class _UF:
    """Union-Find that refuses to merge components which disagree about who the customer
    is. A record whose email or order reference resolves to CUST_012 cannot end up in the
    same case as one that resolves to CUST_047, however similar the text or however close
    in time -- and that stays true through chains, because the identity is tracked on the
    component rather than on the record. This is the only thing that separates two people
    who share a surname, contact support in the same week, and complain about the same
    thing: the structured side is the evidence, not decoration."""

    def __init__(self, items, identity):
        self.p = {i: i for i in items}
        self.cid = {i: identity.get(i) for i in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        """Merge unless the two components name different customers. Returns whether the
        pair is allowed to be in one case, which is true for an already-merged pair."""
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return True
        ca, cb = self.cid[ra], self.cid[rb]
        if ca and cb and ca != cb:
            return False
        lo, hi = sorted([ra, rb])
        self.p[hi] = lo
        self.cid[lo] = ca or cb
        return True


def model(dbt, session):
    dbt.config(materialized="table", packages=["snowflake-snowpark-python"])

    ent = dbt.ref("int_record_entities").select(
        "RECORD_ID", "OCCURRED_TS", "CUSTOMER_NAME", "EMAIL", "ORDER_REF"
    ).collect()
    vectors = dbt.ref("int_record_embeddings").select("RECORD_ID", "EMBEDDING").collect()
    orders = dbt.ref("stg_orders").select("ORDER_ID", "CUSTOMER_ID", "CUSTOMER_NAME", "EMAIL").collect()

    email_to_cid, order_to_cid, orders_name_index = {}, {}, []
    for o in orders:
        cid = o["CUSTOMER_ID"]
        if o["EMAIL"]:
            email_to_cid[str(o["EMAIL"]).lower()] = cid
        if o["ORDER_ID"]:
            order_to_cid[str(o["ORDER_ID"]).upper()] = cid
        orders_name_index.append((_tokens(o["CUSTOMER_NAME"]), cid))

    ids = sorted(r["RECORD_ID"] for r in ent)
    ts = {r["RECORD_ID"]: r["OCCURRED_TS"] for r in ent}
    tok = {r["RECORD_ID"]: _tokens(r["CUSTOMER_NAME"]) for r in ent}
    email = {r["RECORD_ID"]: (str(r["EMAIL"]).lower() if r["EMAIL"] else None) for r in ent}
    oref = {r["RECORD_ID"]: (str(r["ORDER_REF"]).upper() if r["ORDER_REF"] else None) for r in ent}
    emb = {r["RECORD_ID"]: _to_vec(r["EMBEDDING"]) for r in vectors}

    # Who each record says the customer is, where it says so at all. Both a positive
    # signal (two records naming one customer belong together) and, in _UF, a negative
    # one (two records naming different customers cannot).
    key_cid = {}
    for rid in ids:
        cid = None
        if email[rid] and email[rid] in email_to_cid:
            cid = email_to_cid[email[rid]]
        elif oref[rid] and oref[rid] in order_to_cid:
            cid = order_to_cid[oref[rid]]
        key_cid[rid] = cid

    def hours_apart(a, b):
        ta, tb = ts[a], ts[b]
        if ta is None or tb is None:
            return None
        return abs((ta - tb).total_seconds()) / 3600.0

    def within_window(a, b):
        """A case is a bounded episode. Two records only belong to the same one if they
        are close in time, however strong the identifier they share.

        A record with no timestamp is not held apart by the window: staging coalesces
        occurred_ts to the record's arrival time, so this only fires if both were absent,
        and orphaning such a record is worse than admitting it. stg_records tests
        occurred_ts for null so the case stays hypothetical."""
        gap = hours_apart(a, b)
        return gap is None or gap <= TIME_WINDOW_HOURS

    # Which name tokens are worth anything. A surname the orders table shows belongs to
    # two different customers is not identifying, whatever the text says -- so a pair whose
    # only shared name is one of those cannot be linked on the name alone. The structured
    # side is what knows this; the records themselves never do. Measured on this corpus,
    # adding the rule left tiers A, B, C and noise exactly where they were and took
    # precision on tier D's corrupted-identity shape from 0.33 to 1.00.
    token_owners = {}
    for order_tokens, cid in orders_name_index:
        for token in order_tokens:
            token_owners.setdefault(token, set()).add(cid)
    ambiguous_tokens = {t for t, owners in token_owners.items() if len(owners) > 1}

    def hard_signal(a, b):
        """The identifier two records share, if any. Named in priority order."""
        if email[a] and email[a] == email[b]:
            return "email"
        if oref[a] and oref[a] == oref[b]:
            return "order_ref"
        if key_cid[a] and key_cid[a] == key_cid[b]:
            return "resolved_customer"
        return None

    uf = _UF(ids, key_cid)
    edges = []

    def link(a, b, edge_type, cosine):
        if uf.union(a, b):
            edges.append((a, b, edge_type, cosine, hours_apart(a, b)))

    # 1. deterministic edges, gated by the link window. Without the gate a customer who
    # contacts support twice in a quarter collapses into a single case: the shared email
    # (or the shared resolved customer_id) would bridge two unrelated episodes.
    for a, b in _pairs_sharing_a_key(_index(email), _index(oref), _index(key_cid)):
        if not within_window(a, b):
            continue
        edge_type = hard_signal(a, b)
        if edge_type is None:
            continue  # shared a bucket without sharing that bucket's value
        link(a, b, edge_type, None)

    # 2. semantic edges: keyless linking. All three signals are required together, which
    # is what AGENTS.md's Tier B describes: a fuzzy name token, temporal proximity, and
    # issue content that is not unrelated. The name token is never dropped -- same-issue
    # pairs from DIFFERENT customers sit at a median cosine of 0.897, so content alone
    # would happily merge two strangers with the same complaint. Pairs already linked
    # deterministically are still scored, because a second, independent reason for a link
    # is evidence worth keeping rather than an edge worth skipping.
    for a, b in _pairs_sharing_a_key(_index_tokens(tok)):
        if not within_window(a, b):
            continue
        if hard_signal(a, b) is None and (tok[a] & tok[b]) <= ambiguous_tokens:
            continue  # nothing shared but a surname two customers are known to share
        cosine = _cosine(emb.get(a), emb.get(b))
        if cosine >= SIM_FLOOR:
            link(a, b, "semantic", cosine)

    # 3. components, cut wherever the episode falls silent -> stable case ids
    comps = {}
    for rid in ids:
        comps.setdefault(uf.find(rid), []).append(rid)

    groups = []
    for members in comps.values():
        dated = sorted((m for m in members if ts[m] is not None), key=lambda m: (ts[m], m))
        undated = sorted(m for m in members if ts[m] is None)
        if not dated:
            groups.append(undated)
            continue
        runs = [[dated[0]]]
        for i in range(1, len(dated)):
            gap = (ts[dated[i]] - ts[dated[i - 1]]).total_seconds() / 3600.0
            if gap > MAX_EPISODE_GAP_HOURS:
                runs.append([])
            runs[-1].append(dated[i])
        # A record with no timestamp cannot be placed on the timeline, so it stays with
        # the earliest episode rather than becoming a singleton of its own.
        runs[0].extend(undated)
        groups.extend(runs)

    case_of = {}
    for n, members in enumerate(sorted(groups, key=min), 1):
        for rid in members:
            case_of[rid] = f"CASE_G{n:03d}"

    case_members = {}
    for rid in ids:
        case_members.setdefault(case_of[rid], []).append(rid)

    # 4. resolve customer per case
    case_customer = {}
    for case_id, members in case_members.items():
        cid = next((key_cid[r] for r in sorted(members) if key_cid[r]), None)
        if cid is None:
            case_tokens = set()
            for r in members:
                case_tokens |= tok[r]
            cid = next((ocid for otok, ocid in orders_name_index if case_tokens & otok), None)
        case_customer[case_id] = cid

    # match_method is read off the evidence rather than guessed from whether an identity
    # happened to resolve. The old rule called a record "semantic" whenever its email was
    # absent from orders, even when a shared address was exactly what linked it.
    evidence = {rid: set() for rid in ids}
    for a, b, edge_type, _cos, _gap in edges:
        if case_of[a] != case_of[b]:
            continue  # the episode cut severed this edge; it explains nothing now
        kind = "entity" if edge_type in _DETERMINISTIC_EDGES else "semantic"
        evidence[a].add(kind)
        evidence[b].add(kind)

    out = []
    for rid in ids:
        kinds = evidence[rid]
        if not kinds:
            method = "singleton"
        elif kinds == {"entity"}:
            method = "entity"
        elif kinds == {"semantic"}:
            method = "semantic"
        else:
            method = "entity+semantic"
        out.append(["assignment", rid, case_of[rid], case_customer[case_of[rid]], method,
                    None, None, None, None, None, None])

    for a, b, edge_type, cosine, gap in edges:
        out.append(["edge", None, case_of[a], None, None,
                    a, b, edge_type, cosine, gap, case_of[a] == case_of[b]])

    schema = StructType([
        StructField("ROW_TYPE", StringType()),
        StructField("RECORD_ID", StringType()),
        StructField("CASE_ID", StringType()),
        StructField("CUSTOMER_ID", StringType()),
        StructField("MATCH_METHOD", StringType()),
        StructField("RECORD_A", StringType()),
        StructField("RECORD_B", StringType()),
        StructField("EDGE_TYPE", StringType()),
        StructField("COSINE_SIM", DoubleType()),
        StructField("HOURS_APART", DoubleType()),
        StructField("SAME_CASE", BooleanType()),
    ])
    return session.create_dataframe(out, schema)
