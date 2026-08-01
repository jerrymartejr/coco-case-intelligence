"""
Case Intelligence — demo UI.

The order of the page is the argument. It opens on a case that was assembled out of
records sharing no key, with the evidence for every link shown, because that inference is
the product. The rollups and the recommended action come after, as what the inference is
worth once you have it.

Runs three ways, in this order: inside Snowflake (Streamlit-in-Snowflake, active session),
against a named connections.toml entry, or against key-pair credentials from the
environment. The key may be given as a PEM *string* (`SNOWFLAKE_PRIVATE_KEY`, or
`st.secrets`) or as a path (`SNOWFLAKE_PRIVATE_KEY_PATH`); the string wins when both are
set, because a hosting provider has a secret store but no filesystem to put a key on.

A note on the named-connection path: a connection authenticating with
OAUTH_AUTHORIZATION_CODE (what the `cortex` CLI creates for itself) cannot be reused here.
The CLI holds that token, and Snowpark will try to start its own browser flow and fail on
a missing client_id.
"""

import json
import os
import re
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Case Intelligence", page_icon="🧩", layout="wide")

# The schema is an SQL identifier, which cannot be passed as a bind parameter, so it is
# validated against a strict pattern instead. Values always go through bind parameters.
DB = os.environ.get("CASE_INTEL_SCHEMA", "CASE_INTEL.ANALYTICS")
if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*", DB):
    raise ValueError(f"CASE_INTEL_SCHEMA is not a valid Snowflake identifier: {DB!r}")

# The Cortex text model, mirroring the `cortex_text_model` dbt variable so a regional
# substitution reaches the app too. Validated the same way the schema is, because it is
# interpolated into SQL rather than bound.
TEXT_MODEL = os.environ.get("CASE_INTEL_TEXT_MODEL", "mistral-large2")
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", TEXT_MODEL):
    raise ValueError(f"CASE_INTEL_TEXT_MODEL is not a valid Cortex model name: {TEXT_MODEL!r}")

CHANNEL_LABEL = {"chat": "Chat", "email": "Email", "qa_note": "QA note",
                 "survey": "CSAT survey", "document": "PDF escalation form"}
EDGE_LABEL = {"email": "the same email address",
              "order_ref": "the same order reference",
              "resolved_customer": "an order resolving to the same customer",
              "semantic": "a shared name, close in time, same problem"}


def _secret(name):
    """Look in st.secrets first, then the environment. Hosting providers populate the
    former; a local shell populates the latter."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except (FileNotFoundError, KeyError):
        pass  # no secrets.toml present, which is normal locally
    return os.environ.get(name)


def _private_key_der():
    """Snowpark wants the key as DER bytes. Accept it as PEM text or as a path to a file.

    Text takes precedence: it is how a deployed app receives a key, and if someone has
    gone to the trouble of putting one in the secret store it is the one they mean.
    """
    from cryptography.hazmat.primitives import serialization

    pem = _secret("SNOWFLAKE_PRIVATE_KEY")
    if pem:
        pem_bytes = pem.encode() if isinstance(pem, str) else pem
    else:
        path = _secret("SNOWFLAKE_PRIVATE_KEY_PATH")
        if not path:
            return None
        pem_bytes = Path(path).expanduser().read_bytes()

    passphrase = _secret("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    key = serialization.load_pem_private_key(
        pem_bytes, password=passphrase.encode() if passphrase else None)
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


@st.cache_resource
def get_session():
    from snowflake.snowpark import Session
    from snowflake.snowpark.exceptions import SnowparkSessionException

    # 1. Running inside Snowflake: the session already exists.
    try:
        from snowflake.snowpark.context import get_active_session
        return get_active_session()
    except SnowparkSessionException:
        pass  # not running in Snowflake, fall through to a local session

    # 2. An explicitly named connection, if the user asked for one.
    named = _secret("SNOWFLAKE_CONNECTION")
    if named:
        return Session.builder.config("connection_name", named).create()

    # 3. Otherwise key-pair credentials, from the secret store or the environment.
    account, user = _secret("SNOWFLAKE_ACCOUNT"), _secret("SNOWFLAKE_USER")
    der = _private_key_der()
    if not (account and user and der):
        raise RuntimeError(
            "Missing Snowflake credentials. Set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER and "
            "either SNOWFLAKE_PRIVATE_KEY (PEM text) or SNOWFLAKE_PRIVATE_KEY_PATH. "
            "Locally: copy .env.example to .env, fill it in, and `source .env`. "
            "See docs/SETUP.md."
        )
    return Session.builder.configs({
        "account": account,
        "user": user,
        "private_key": der,
        "role": _secret("SNOWFLAKE_ROLE") or "CASE_INTEL_APP_ROLE",
        "database": _secret("SNOWFLAKE_DATABASE") or "CASE_INTEL",
        "schema": _secret("SNOWFLAKE_SCHEMA") or "ANALYTICS",
        "warehouse": _secret("SNOWFLAKE_WAREHOUSE") or "COMPUTE_WH",
    }).create()


st.title("🧩 Case Intelligence")
st.caption(
    "Five formats, no shared key. The case ids below exist in none of the source records — "
    "they are inferred from what the records mean, who they name, and when they arrived. "
    "This page is the evidence view; the conversational interface is **CoCo**, through the "
    "six agent skills in [the repo](https://github.com/jerrymartejr/coco-case-intelligence) "
    "— ask it *\"why are these records one case?\"* and it narrates the same edges shown here."
)

try:
    session = get_session()
except Exception as exc:  # noqa: BLE001 - the whole point is to catch anything and explain it
    st.error(
        "Could not connect to Snowflake, so there is nothing to show. This is usually a "
        "credentials problem or a warehouse that has been suspended or expired."
    )
    st.caption(f"{type(exc).__name__}: {exc}")
    st.stop()


@st.cache_data(ttl=300)
def q(sql, params=None):
    """Run a query. Values are always passed as bind parameters, never interpolated:
    only the schema identifier is templated in, and it is pattern-validated at import."""
    return session.sql(sql, params=params).to_pandas()


def try_q(sql, params=None, *, failure):
    """Run a query, and if it fails say so in words and carry on.

    A suspended warehouse, a lapsed trial or a missing table are all things a visitor to
    a deployed demo can plausibly arrive to, and none of them should produce a stack
    trace on the page. Sections that lose their data explain themselves; the rest of the
    page still renders.
    """
    try:
        return q(sql, params)
    except Exception as exc:  # noqa: BLE001 - anything here is a page-level message, not a crash
        st.error(failure)
        st.caption(f"{type(exc).__name__}: {exc}")
        return None


cases = try_q(
    f"select * from {DB}.fct_case_enriched",
    failure=(f"Connected, but could not read {DB}.fct_case_enriched. The pipeline may not "
             "have been built on this account yet, the warehouse may be suspended, or this "
             "role may not be able to see it."),
)
if cases is None:
    st.stop()

# --- KPIs -------------------------------------------------------------------------------
multi = cases[cases["RECORD_COUNT"] > 1]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Cases", len(cases), help="One row per case. Assembled from records that share no key.")
c2.metric("Assembled from 2+ records", len(multi),
          help="Cases the resolver built by linking several records across formats.")
c3.metric("Unresolved", int((~cases["RESOLVED"].fillna(False)).sum()),
          help="Judged case by case in Stage 3 from the records themselves.")
c4.metric("Revenue at risk", f"${cases['REVENUE_AT_RISK'].fillna(0).sum():,.0f}",
          help="Open cases only, each counting the one order that case is about.")

# --- Case anatomy: the linking, made visible ---------------------------------------------
st.header("Case anatomy — why are these records one case?")
st.write(
    "This is the part that is not a join. Each case below was assembled from records in "
    "different formats that shared **no identifier**, and every link is shown with the "
    "evidence behind it."
)

candidates = try_q(f"""
    with members as (
        select a.case_id,
               count(*)                                                     as n_records,
               sum(case when r.source_type = 'document' then 1 else 0 end)  as n_documents,
               count(distinct r.channel)                                    as n_channels
        from {DB}.int_case_assignments a
        join {DB}.stg_records r on r.record_id = a.record_id
        group by 1
    ),
    evidence as (
        select case_id,
               count(*)                                                     as n_edges,
               sum(case when edge_type = 'semantic' then 1 else 0 end)      as n_semantic
        from {DB}.int_case_edges
        where same_case
        group by 1
    )
    select m.case_id, m.n_records, m.n_documents, m.n_channels,
           e.n_edges = e.n_semantic as keyless
    from members m
    join evidence e on e.case_id = m.case_id
    where m.n_records > 1
    -- Default to the most demonstrative case: linked with no identifier at all, containing
    -- a binary document, spanning the most formats. Ordering is total, so the app opens on
    -- the same case every time.
    order by keyless desc, m.n_documents desc, m.n_channels desc, m.n_records desc, m.case_id
""", failure="Could not load the case list, so the anatomy view is unavailable.")

if candidates is None or candidates.empty:
    st.info("No multi-record cases in this build, so there is no linking to show.")
else:
    labels = {}
    for row in candidates.itertuples():
        mark = "no shared identifier" if row.KEYLESS else "shared identifier present"
        docs = ", includes a PDF" if row.N_DOCUMENTS else ""
        labels[row.CASE_ID] = (
            f"{row.CASE_ID} — {row.N_RECORDS} records, {row.N_CHANNELS} formats ({mark}{docs})"
        )

    picked = st.selectbox("Case", list(labels), format_func=lambda c: labels[c], index=0)

    members = try_q(f"""
        select r.record_id, r.source_type, r.channel, r.occurred_ts, r.customer_name,
               r.issue_text, s.searchable_text
        from {DB}.int_case_assignments a
        join {DB}.stg_records r  on r.record_id = a.record_id
        left join {DB}.search_corpus s on s.record_id = r.record_id
        where a.case_id = ?
        order by r.occurred_ts
    """, params=[picked], failure="Could not load this case's records.")

    edges = try_q(f"""
        select record_a, record_b, edge_type, cosine_sim, hours_apart
        from {DB}.int_case_edges
        where case_id = ? and same_case
        order by record_a, record_b
    """, params=[picked], failure="Could not load this case's linking evidence.")

    if members is None or edges is None:
        st.stop()

    left, right = st.columns([3, 2])

    with left:
        st.subheader("The records")
        st.caption(
            f"{len(members)} records, "
            f"{members['SOURCE_TYPE'].nunique()} different formats, verbatim as they arrived."
        )
        for row in members.itertuples():
            label = CHANNEL_LABEL.get(row.SOURCE_TYPE, row.SOURCE_TYPE)
            with st.expander(f"{label} · {row.RECORD_ID} · {row.OCCURRED_TS} · {row.CUSTOMER_NAME}"):
                st.markdown(f"**Extracted issue:** {row.ISSUE_TEXT or '(none extracted)'}")
                verbatim = (row.SEARCHABLE_TEXT or "").split("\n", 1)
                st.text(verbatim[1] if len(verbatim) > 1 else (row.SEARCHABLE_TEXT or ""))

    with right:
        st.subheader("The evidence")
        if edges.empty:
            st.caption("A single record. Nothing was linked, so there is nothing to justify.")
        else:
            st.caption("Every link the resolver made, and what it was made on.")
            for row in edges.itertuples():
                why = EDGE_LABEL.get(row.EDGE_TYPE, row.EDGE_TYPE)
                detail = f"{row.HOURS_APART:.1f}h apart" if row.HOURS_APART is not None else "time unknown"
                if row.COSINE_SIM is not None:
                    detail += f", issue similarity {row.COSINE_SIM:.3f}"
                st.markdown(f"- **{row.RECORD_A} ↔ {row.RECORD_B}** — {why} ({detail})")

            dot = ["graph G {", "  rankdir=LR; node [shape=box, style=rounded, fontsize=10];"]
            for row in members.itertuples():
                short = CHANNEL_LABEL.get(row.SOURCE_TYPE, row.SOURCE_TYPE)
                dot.append(f'  "{row.RECORD_ID}" [label="{short}\\n{row.RECORD_ID}"];')
            for row in edges.itertuples():
                tag = row.EDGE_TYPE if row.COSINE_SIM is None else f"{row.EDGE_TYPE} {row.COSINE_SIM:.2f}"
                dot.append(f'  "{row.RECORD_A}" -- "{row.RECORD_B}" [label="{tag}", fontsize=8];')
            dot.append("}")
            try:
                st.graphviz_chart("\n".join(dot))
                st.caption(
                    "The same links as the list above, drawn as a graph. The list is the "
                    "accessible version; nothing here is shown only in the picture."
                )
            except Exception:  # noqa: BLE001 - graph rendering is a nicety, the list is the content
                st.caption("(Graph rendering unavailable here; the list above is the same information.)")

# --- How do we know the linking is right? ------------------------------------------------
st.header("How do we know the linking is right?")
accuracy = try_q(f"""
    select tier, shape, true_cases, fully_linked, predicted_cases, false_merges,
           recall, precision
    from {DB}.agg_linkage_accuracy
""", failure="Could not load the linkage scoreboard.")
if accuracy is not None:
    st.dataframe(accuracy, width="stretch", hide_index=True)
st.caption(
    "Scored against a ground-truth key that is generator output and is never read by the "
    "pipeline — it enters as a seed, is joined to the predictions here, and is used nowhere "
    "upstream. Tiers A-C are generated under conditions the resolver needs, so their 100% "
    "is a regression floor rather than a result. **Tier D breaks those conditions on "
    "purpose and is the real measurement:** where a colliding surname comes with identity "
    "evidence the resolver separates the two people perfectly, and where it comes with no "
    "identifier at all the resolver fails every time. That 0.000 is the honest limit of "
    "keyless linking."
)

# --- Drivers: the structured fusion ------------------------------------------------------
st.header("What it costs")
drivers = try_q(f"""
    select root_cause_category as root_cause,
           sum(revenue_at_risk) as revenue_at_risk,
           sum(case_count) as cases,
           sum(unresolved_count) as unresolved,
           round(avg(avg_csat),2) as avg_csat
    from {DB}.agg_root_cause_daily
    group by root_cause_category
    order by revenue_at_risk desc
""", failure="Could not load the root-cause rollup.")
if drivers is not None and not drivers.empty:
    st.bar_chart(drivers.set_index("ROOT_CAUSE")["REVENUE_AT_RISK"])
    top_row = drivers.iloc[0]
    st.caption(
        f"Revenue at risk by root cause. The largest is **{top_row['ROOT_CAUSE']}** at "
        f"${top_row['REVENUE_AT_RISK']:,.0f} across {int(top_row['CASES'])} cases. "
        "Every figure in the chart is also in the table below, so nothing depends on "
        "reading the bars or telling colours apart."
    )
    st.dataframe(drivers, width="stretch", hide_index=True)

    # --- Recommended action (agentic, inline) --------------------------------------------
    st.subheader("Recommended action")
    top = top_row["ROOT_CAUSE"]
    # Compute the impact figures in SQL and pass them explicitly, so the model states
    # them rather than inventing its own arithmetic.
    rec = try_q(f"""
        with d as (
            select
                root_cause_category as root_cause,
                count(*)                                        as case_count,
                sum(case when not resolved then 1 else 0 end)   as unresolved,
                sum(coalesce(revenue_at_risk, 0))               as revenue_at_risk,
                round(avg(csat_score), 1)                       as avg_csat,
                listagg(case_id, ', ')                          as case_ids
            from {DB}.fct_case_enriched
            where root_cause_category = ?
            group by root_cause_category
        )
        select snowflake.cortex.ai_complete('{TEXT_MODEL}',
            'You are a support operations analyst. Write a short recommended action with exactly these '
            || 'sections: Problem, Impact, Owning team, Ask, Affected cases. Use ONLY the figures given '
            || 'below verbatim. Do NOT invent, multiply, or estimate any numbers.' || chr(10)
            || 'Driver: ' || root_cause || chr(10)
            || 'Total cases: ' || case_count || chr(10)
            || 'Unresolved: ' || unresolved || chr(10)
            || 'Revenue at risk (USD): ' || revenue_at_risk || chr(10)
            || 'Avg CSAT: ' || coalesce(to_varchar(avg_csat), 'n/a') || chr(10)
            || 'Affected case ids: ' || case_ids
        ) as recommendation
        from d
    """, params=[top], failure=("Could not generate the recommended action. This one needs a "
                                "running warehouse and a Cortex call, so it is the first thing "
                                "to fail if either is unavailable."))
    if rec is not None and not rec.empty:
        text = rec.iloc[0]["RECOMMENDATION"]
        # ai_complete can arrive JSON-encoded — a quoted string with \n escape
        # sequences — depending on the driver's type mapping, and those escapes
        # would otherwise render literally on the page.
        if isinstance(text, str):
            stripped = text.strip()
            if stripped.startswith('"') and stripped.endswith('"'):
                try:
                    text = json.loads(stripped)
                except ValueError:
                    text = stripped
        st.info(text)

# --- Case explorer -----------------------------------------------------------------------
st.header("Every case")
only_multi = st.checkbox("Only cases assembled from more than one record", value=True)
view = multi if only_multi else cases
cols = ["CASE_ID", "CUSTOMER_ID", "ISSUE", "RESOLVED", "ROOT_CAUSE", "SENTIMENT",
        "RECORD_COUNT", "CHANNELS", "REVENUE_AT_RISK", "CSAT_SCORE"]
st.dataframe(view[[c for c in cols if c in view.columns]].sort_values("REVENUE_AT_RISK", ascending=False),
             width="stretch", hide_index=True)

with st.expander("Timeline for a case"):
    cid = st.selectbox("Case", view["CASE_ID"].tolist(), key="timeline_case")
    if cid:
        row = view[view["CASE_ID"] == cid].iloc[0]
        st.write(row["TIMELINE"])
        st.caption(f"Root cause: {row['ROOT_CAUSE']}  ·  Resolution: {row['RESOLUTION_PATH']}")
