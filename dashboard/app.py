"""
Financial Restatement Monitor (Streamlit).

    make dashboard                                         # warehouse.duckdb
    WAREHOUSE_DB_PATH=demo.duckdb make dashboard           # after `make demo`

Read-only view over the gold layer: the scored alert queue, restatements,
other anomalies, one company at a time, and pipeline health (lineage and
row counts). It never writes to the warehouse.
"""

import os
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "warehouse.duckdb"
if not DEFAULT_DB.exists() and (ROOT / "demo.duckdb").exists():
    DEFAULT_DB = ROOT / "demo.duckdb"
DB_PATH = os.getenv("WAREHOUSE_DB_PATH", str(DEFAULT_DB))

st.set_page_config(page_title="Restatement Monitor", layout="wide")


@st.cache_data(ttl=300)
def query(sql: str) -> pd.DataFrame:
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
    except duckdb.Error as exc:
        st.error(f"Can't open {DB_PATH}: {exc}")
        return pd.DataFrame()
    try:
        return con.execute(sql).fetchdf()
    except duckdb.Error:
        return pd.DataFrame()
    finally:
        con.close()


st.title("Financial Restatement Monitor")
st.caption(f"Warehouse: `{DB_PATH}` · read-only")

alerts = query(
    """
    select priority_score, ticker, company_name, anomaly_type, metric, period_end,
           actual_value, expected_value, pct_change, severity, detected_date,
           recommended_action, risk_factors
    from gold.alerts order by priority_score desc
"""
)
restatements = query(
    """
    select r.*, c.ticker, c.company_name
    from gold.fct_restatements r left join gold.dim_companies c using (cik)
"""
)
companies = query("select * from gold.dim_companies order by ticker")

if alerts.empty and restatements.empty:
    st.warning(
        "No gold data yet. Run `make demo` (sample data) or `make pipeline` (live)."
    )
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Companies", len(companies))
c2.metric("Restatements", len(restatements))
c3.metric(
    "Material",
    int((restatements.get("severity") == "MATERIAL").sum())
    if not restatements.empty
    else 0,
)
c4.metric(
    "Immediate review",
    int((alerts["priority_score"] >= 70).sum()) if not alerts.empty else 0,
)

tab_queue, tab_rest, tab_company, tab_health = st.tabs(
    ["Alert queue", "Restatements", "Company", "Pipeline health"]
)

with tab_queue:
    st.subheader("What to review first")
    types = sorted(alerts["anomaly_type"].unique()) if not alerts.empty else []
    chosen = st.multiselect("Anomaly types", types, default=types)
    view = alerts[alerts["anomaly_type"].isin(chosen)] if chosen else alerts
    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "priority_score": st.column_config.ProgressColumn(
                "Priority", min_value=0, max_value=100, format="%d"
            )
        },
    )

with tab_rest:
    if restatements.empty:
        st.info("No restatements detected.")
    else:
        left, right = st.columns(2)
        left.plotly_chart(
            px.histogram(
                restatements,
                x="severity",
                color="restatement_type",
                title="Restatements by severity and type",
            ),
            use_container_width=True,
        )
        right.plotly_chart(
            px.scatter(
                restatements,
                x="restatement_filed_date",
                y="pct_change",
                color="severity",
                hover_data=["ticker", "metric", "period_end"],
                title="When they were filed, and how big",
            ),
            use_container_width=True,
        )
        st.dataframe(
            restatements[
                [
                    "ticker",
                    "metric",
                    "period_start",
                    "period_end",
                    "original_value",
                    "restated_value",
                    "pct_change",
                    "severity",
                    "restatement_type",
                    "restatement_form_type",
                    "days_to_restatement",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

with tab_company:
    if companies.empty:
        st.info("No companies loaded.")
    else:
        ticker = st.selectbox("Company", companies["ticker"].tolist())
        row = companies[companies["ticker"] == ticker].iloc[0]
        st.write(
            f"**{row['company_name']}** · CIK {row['cik']} · {row['sic_description']} · "
            f"{row['total_filings']} filings ({row['amendment_filings']} amendments)"
        )
        rev = query(
            f"""
            select period_end, revenue, is_derived from silver.int_quarterly_revenue
            where cik = '{row['cik']}' order by period_end
        """
        )
        if not rev.empty:
            st.plotly_chart(
                px.bar(
                    rev,
                    x="period_end",
                    y="revenue",
                    color="is_derived",
                    title="Quarterly revenue (latest filed version; Q4 derived if untagged)",
                ),
                use_container_width=True,
            )
        val = query(
            f"""
            select period_end, price_to_sales, robust_z, is_outlier from silver.int_market_valuation
            where cik = '{row['cik']}' order by period_end
        """
        )
        if not val.empty:
            st.plotly_chart(
                px.line(
                    val,
                    x="period_end",
                    y="price_to_sales",
                    markers=True,
                    log_y=True,
                    title="Price-to-sales (log scale)",
                ),
                use_container_width=True,
            )
        st.dataframe(
            alerts[alerts["ticker"] == ticker],
            use_container_width=True,
            hide_index=True,
        )

with tab_health:
    st.subheader("Lineage: what was loaded, from which exact file")
    st.dataframe(
        query(
            """
        select source, cik, status, rows_loaded, sha256, landed_path, finished_at, error
        from bronze.ingestion_runs order by finished_at desc limit 200
    """
        ),
        use_container_width=True,
        hide_index=True,
    )
    counts = query(
        """
        select 'bronze.raw_financial_facts' as table_name, count(*) as row_count from bronze.raw_financial_facts
        union all select 'bronze.raw_filings', count(*) from bronze.raw_filings
        union all select 'bronze.raw_market_data', count(*) from bronze.raw_market_data
        union all select 'gold.fct_restatements', count(*) from gold.fct_restatements
        union all select 'gold.fct_anomalies', count(*) from gold.fct_anomalies
        union all select 'gold.alerts', count(*) from gold.alerts
    """
    )
    st.dataframe(counts, hide_index=True)
