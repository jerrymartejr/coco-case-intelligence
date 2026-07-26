"""
Stage 2 — identity resolution. The centerpiece: link records that share NO key into
one case_id, then assign each case a customer identity.

Approach (per the CoCo review):
  1. Deterministic pass: edges between records that share a hard signal
     (same email, same order_ref, or both resolving to the same customer via orders)
     AND fall inside the same link window. The window matters: a returning customer is
     not one endless case, so a hard identifier only fuses records from the same episode.
  2. Semantic pass (the keyless / thesis tier): for record pairs close in time that
     share a fuzzy name token, add an edge when their issue-text embeddings are highly
     similar (cosine >= threshold). Embeddings are computed once, then compared in-memory.
  3. Connected components (Union-Find) over all edges -> case_id.
  4. Customer resolution: key-based first; fall back to a fuzzy name bridge to orders so
     keyless cases can still tie to structured metrics downstream.

Pure-Python (no pandas/numpy) so it runs in the Snowpark stored-proc sandbox. The
dataset is small, so the O(N^2) pair scan is trivial; embeddings are computed once.
Deterministic: components are labeled by their smallest record_id, so case ids are stable.
"""

import re
import json
from snowflake.snowpark.functions import call_function, col, lit
from snowflake.snowpark.types import StructType, StructField, StringType

# Similarity FLOOR, not a separator. Measured on the current corpus (518 records,
# 170 planted cases), embedding the extracted issue_text:
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
TIME_WINDOW_HOURS = 72
EMBED_MODEL = "snowflake-arctic-embed-m-v1.5"


def _tokens(name):
    if not name:
        return set()
    return {t for t in re.findall(r"[a-z]{3,}", str(name).lower())}


def _to_vec(v):
    if v is None:
        return None
    if isinstance(v, str):
        try:
            return [float(x) for x in json.loads(v)]
        except Exception:
            return None
    try:
        return [float(x) for x in v]
    except Exception:
        return None


def _cosine(a, b):
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / ((na * nb) + 1e-9)


class _UF:
    def __init__(self, items):
        self.p = {i: i for i in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            lo, hi = sorted([ra, rb])
            self.p[hi] = lo


def model(dbt, session):
    dbt.config(materialized="table", packages=["snowflake-snowpark-python"])

    # Embed issue_text once (precompute), then pull rows via collect() (no pandas).
    ent = dbt.ref("int_record_entities").with_column(
        "EMB", call_function("SNOWFLAKE.CORTEX.EMBED_TEXT_768", lit(EMBED_MODEL), col("ISSUE_TEXT"))
    ).select("RECORD_ID", "OCCURRED_TS", "CUSTOMER_NAME", "EMAIL", "ORDER_REF", "EMB")
    rows = ent.collect()

    orders = dbt.ref("stg_orders").select("ORDER_ID", "CUSTOMER_ID", "CUSTOMER_NAME", "EMAIL").collect()

    email_to_cid, order_to_cid, orders_name_index = {}, {}, []
    for o in orders:
        cid = o["CUSTOMER_ID"]
        if o["EMAIL"]:
            email_to_cid[str(o["EMAIL"]).lower()] = cid
        if o["ORDER_ID"]:
            order_to_cid[str(o["ORDER_ID"]).upper()] = cid
        orders_name_index.append((_tokens(o["CUSTOMER_NAME"]), cid))

    ids = [r["RECORD_ID"] for r in rows]
    ts = {r["RECORD_ID"]: r["OCCURRED_TS"] for r in rows}
    tok = {r["RECORD_ID"]: _tokens(r["CUSTOMER_NAME"]) for r in rows}
    emb = {r["RECORD_ID"]: _to_vec(r["EMB"]) for r in rows}
    email = {r["RECORD_ID"]: (str(r["EMAIL"]).lower() if r["EMAIL"] else None) for r in rows}
    oref = {r["RECORD_ID"]: (str(r["ORDER_REF"]).upper() if r["ORDER_REF"] else None) for r in rows}

    key_cid = {}
    for rid in ids:
        cid = None
        if email[rid] and email[rid] in email_to_cid:
            cid = email_to_cid[email[rid]]
        elif oref[rid] and oref[rid] in order_to_cid:
            cid = order_to_cid[oref[rid]]
        key_cid[rid] = cid

    uf = _UF(ids)

    def _within_window(a, b):
        """A case is a bounded episode. Two records only belong to the same one if they
        are close in time, however strong the identifier they share."""
        ta, tb = ts[a], ts[b]
        if ta is None or tb is None:
            return True
        return abs((ta - tb).total_seconds()) <= TIME_WINDOW_HOURS * 3600

    # 1. deterministic edges, gated by the link window. Without the gate a customer who
    # contacts support twice in a quarter collapses into a single case: the shared email
    # (or the shared resolved customer_id) would bridge two unrelated episodes.
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            if not _within_window(a, b):
                continue
            if email[a] and email[a] == email[b]:
                uf.union(a, b); continue
            if oref[a] and oref[a] == oref[b]:
                uf.union(a, b); continue
            if key_cid[a] and key_cid[a] == key_cid[b]:
                uf.union(a, b); continue

    # 2. semantic edges: keyless linking. All three signals are required together, which
    # is what AGENTS.md's Tier B describes: a fuzzy name token, temporal proximity, and
    # issue content that is not unrelated. The name token is never dropped -- same-issue
    # pairs from DIFFERENT customers sit at a median cosine of 0.897, so content alone
    # would happily merge two strangers with the same complaint.
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            if uf.find(a) == uf.find(b):
                continue
            if not (tok[a] & tok[b]):
                continue
            ta, tb = ts[a], ts[b]
            if ta is not None and tb is not None:
                if abs((ta - tb).total_seconds()) > TIME_WINDOW_HOURS * 3600:
                    continue
            if _cosine(emb[a], emb[b]) >= SIM_FLOOR:
                uf.union(a, b)

    # 3. components -> stable case ids
    comps = {}
    for rid in ids:
        comps.setdefault(uf.find(rid), []).append(rid)
    root_to_case = {}
    for n, root in enumerate(sorted(comps.keys()), 1):
        root_to_case[root] = f"CASE_G{n:03d}"
    case_members = {root_to_case[root]: members for root, members in comps.items()}

    # 4. resolve customer per case
    case_customer = {}
    for case_id, members in case_members.items():
        cid = next((key_cid[r] for r in members if key_cid[r]), None)
        if cid is None:
            case_tokens = set()
            for r in members:
                case_tokens |= tok[r]
            cid = next((ocid for otok, ocid in orders_name_index if case_tokens & otok), None)
        case_customer[case_id] = cid

    out = []
    for rid in ids:
        case_id = root_to_case[uf.find(rid)]
        method = "key" if key_cid[rid] else ("semantic" if len(case_members[case_id]) > 1 else "singleton")
        out.append([rid, case_id, case_customer[case_id], method])

    schema = StructType([
        StructField("RECORD_ID", StringType()),
        StructField("CASE_ID", StringType()),
        StructField("CUSTOMER_ID", StringType()),
        StructField("MATCH_METHOD", StringType()),
    ])
    return session.create_dataframe(out, schema)
