"""
Case Intelligence — demo UI.

Runs locally (Snowpark session from the `coco_trial` connection) or as a Streamlit-in-
Snowflake app (active session). Surfaces the case-intelligence marts: KPIs, a root-cause
rollup, a case explorer, and an inline recommended action generated with Cortex.
"""

import streamlit as st

DB = "CASE_INTEL.ANALYTICS"


@st.cache_resource
def get_session():
    try:
        from snowflake.snowpark.context import get_active_session
        return get_active_session()
    except Exception:
        from snowflake.snowpark import Session
        return Session.builder.config("connection_name", "coco_trial").create()


session = get_session()


@st.cache_data(ttl=300)
def q(sql):
    return session.sql(sql).to_pandas()


st.set_page_config(page_title="Case Intelligence", page_icon="🧩", layout="wide")
st.title("🧩 Case Intelligence")
st.caption("Unstructured support records → linked cases → diagnosed drivers → a recommended action.")

# --- KPIs ---
cases = q(f"select * from {DB}.fct_case_enriched")
multi = cases[cases["RECORD_COUNT"] > 1]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Cases", len(cases))
c2.metric("Multi-record cases", len(multi))
c3.metric("Unresolved", int((~cases["RESOLVED"].fillna(False)).sum()))
c4.metric("Revenue at risk", f"${cases['REVENUE_AT_RISK'].fillna(0).sum():,.0f}")

# --- Root-cause rollup ---
st.subheader("Revenue at risk by root cause")
drivers = q(f"""
    select root_cause_category as root_cause,
           sum(revenue_at_risk) as revenue_at_risk,
           sum(case_count) as cases,
           sum(unresolved_count) as unresolved,
           round(avg(avg_csat),2) as avg_csat
    from {DB}.agg_root_cause_daily
    group by root_cause_category
    order by revenue_at_risk desc
""")
if not drivers.empty:
    st.bar_chart(drivers.set_index("ROOT_CAUSE")["REVENUE_AT_RISK"])
    st.dataframe(drivers, use_container_width=True, hide_index=True)

# --- Recommended action (agentic, inline) ---
st.subheader("🎯 Recommended action")
if not drivers.empty:
    top = drivers.iloc[0]["ROOT_CAUSE"].replace("'", "''")
    # Compute the impact figures in SQL and pass them explicitly, so the model states
    # them rather than inventing its own arithmetic.
    rec = q(f"""
        with d as (
            select
                root_cause_category as root_cause,
                count(*)                                        as case_count,
                sum(case when not resolved then 1 else 0 end)   as unresolved,
                sum(coalesce(revenue_at_risk, 0))               as revenue_at_risk,
                round(avg(csat_score), 1)                       as avg_csat,
                listagg(case_id, ', ')                          as case_ids
            from {DB}.fct_case_enriched
            where root_cause_category = '{top}'
            group by root_cause_category
        )
        select snowflake.cortex.ai_complete('mistral-large2',
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
    """)
    st.info(rec.iloc[0]["RECOMMENDATION"])

# --- Case explorer ---
st.subheader("Case explorer")
only_multi = st.checkbox("Only multi-record (linked) cases", value=True)
view = multi if only_multi else cases
cols = ["CASE_ID", "CUSTOMER_ID", "ISSUE", "RESOLVED", "ROOT_CAUSE", "SENTIMENT",
        "RECORD_COUNT", "CHANNELS", "REVENUE_AT_RISK", "CSAT_SCORE"]
st.dataframe(view[[c for c in cols if c in view.columns]].sort_values("REVENUE_AT_RISK", ascending=False),
             use_container_width=True, hide_index=True)

with st.expander("Timeline for a case"):
    cid = st.selectbox("Case", view["CASE_ID"].tolist())
    if cid:
        row = view[view["CASE_ID"] == cid].iloc[0]
        st.write(f"**Issue:** {row.get('ISSUE')}")
        st.write(f"**Timeline:** {row.get('TIMELINE')}")
        st.write(f"**Root cause:** {row.get('ROOT_CAUSE')}")
        st.write(f"**Resolution:** {row.get('RESOLUTION_PATH')}")
