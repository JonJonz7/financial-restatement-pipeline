"""
Financial Restatement Monitor — Streamlit Dashboard
=====================================================
Interactive monitoring dashboard for the Financial Restatement &
Anomaly Detection Pipeline.  Connects to the DuckDB warehouse to
display detected restatements, anomaly scores, and data-quality
status across the bronze/silver/gold medallion layers.
"""

import os

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Financial Restatement Monitor",
    page_icon="$",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom dark theme styling
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .metric-card {
        background-color: #1e1e2e;
        border: 1px solid #313244;
        border-radius: 8px;
        padding: 20px;
        text-align: center;
    }
    .metric-value {
        font-size: 2.4rem;
        font-weight: 700;
        color: #cdd6f4;
        margin: 0;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #a6adc8;
        margin-top: 4px;
    }
    .section-header {
        border-bottom: 2px solid #313244;
        padding-bottom: 8px;
        margin-bottom: 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("Configuration")
db_path = st.sidebar.text_input(
    "DuckDB Path",
    value=os.getenv("DUCKDB_PATH", "warehouse.duckdb"),
)
refresh = st.sidebar.button("Refresh Data")

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Financial Restatement Monitor**\n\n"
    "Monitors SEC EDGAR filings for value changes across "
    "reporting periods and flags anomalies for review."
)


# ---------------------------------------------------------------------------
# Database connection helpers
# ---------------------------------------------------------------------------


@st.cache_resource(ttl=300)
def get_connection(path: str):
    """Return a read-only DuckDB connection (cached for 5 minutes)."""
    return duckdb.connect(path, read_only=True)


def table_exists(con, schema: str, table: str) -> bool:
    """Check if a table exists in the given schema."""
    try:
        result = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name = ?",
            [schema, table],
        ).fetchone()
        return result[0] > 0
    except Exception:
        return False


def safe_query(con, sql: str) -> pd.DataFrame:
    """Execute a query and return a DataFrame; return empty on error."""
    try:
        return con.execute(sql).fetchdf()
    except Exception:
        return pd.DataFrame()


def get_row_count(con, schema: str, table: str) -> int:
    """Get the row count for a schema.table."""
    try:
        result = con.execute(f"SELECT COUNT(*) FROM {schema}.{table}").fetchone()
        return result[0]
    except Exception:
        return 0


def get_freshness(con, schema: str, table: str) -> str:
    """Get the latest ingested_at timestamp for a table."""
    try:
        result = con.execute(
            f"SELECT MAX(ingested_at) FROM {schema}.{table}"
        ).fetchone()
        return str(result[0]) if result[0] else "N/A"
    except Exception:
        return "N/A"


# ---------------------------------------------------------------------------
# Main dashboard
# ---------------------------------------------------------------------------
if refresh:
    st.cache_resource.clear()

st.title("Financial Restatement Monitor")

try:
    con = get_connection(db_path)
except Exception as e:
    st.error(f"Cannot connect to DuckDB at `{db_path}`: {e}")
    st.info("Run the pipeline first:  `make pipeline`")
    st.stop()

# Check if the gold layer tables exist
has_restatements = table_exists(con, "gold", "fct_restatements")
has_anomalies = table_exists(con, "gold", "fct_anomalies")
has_bronze = table_exists(con, "bronze", "raw_financial_facts")

if not has_bronze:
    st.warning(
        "No data found in the warehouse. Run the pipeline first to ingest data."
    )
    st.code("make setup\nmake ingest\nmake transform\nmake detect", language="bash")
    st.stop()


# ===================================================================
# a. KPI Strip
# ===================================================================
st.markdown('<div class="section-header"><h2>Overview</h2></div>', unsafe_allow_html=True)

kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)

# Total companies monitored
companies_count = 0
try:
    result = con.execute(
        "SELECT COUNT(DISTINCT cik) FROM bronze.raw_financial_facts"
    ).fetchone()
    companies_count = result[0]
except Exception:
    pass

# Total restatements detected
restatements_count = 0
if has_restatements:
    try:
        result = con.execute("SELECT COUNT(*) FROM gold.fct_restatements").fetchone()
        restatements_count = result[0]
    except Exception:
        pass

# Material restatements
material_count = 0
if has_restatements:
    try:
        result = con.execute(
            "SELECT COUNT(*) FROM gold.fct_restatements WHERE severity = 'MATERIAL'"
        ).fetchone()
        material_count = result[0]
    except Exception:
        pass

# Avg days to detect
avg_days = 0
if has_restatements:
    try:
        result = con.execute(
            "SELECT AVG(days_to_restatement) FROM gold.fct_restatements "
            "WHERE days_to_restatement IS NOT NULL"
        ).fetchone()
        avg_days = round(result[0]) if result[0] else 0
    except Exception:
        pass

with kpi_col1:
    st.markdown(
        f'<div class="metric-card">'
        f'<p class="metric-value">{companies_count:,}</p>'
        f'<p class="metric-label">Companies Monitored</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

with kpi_col2:
    st.markdown(
        f'<div class="metric-card">'
        f'<p class="metric-value">{restatements_count:,}</p>'
        f'<p class="metric-label">Restatements Detected</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

with kpi_col3:
    st.markdown(
        f'<div class="metric-card">'
        f'<p class="metric-value">{material_count:,}</p>'
        f'<p class="metric-label">Material Restatements</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

with kpi_col4:
    st.markdown(
        f'<div class="metric-card">'
        f'<p class="metric-value">{avg_days:,}</p>'
        f'<p class="metric-label">Avg Days to Detect</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# ===================================================================
# b. Restatement Timeline + c. Severity Distribution
# ===================================================================
if has_restatements and restatements_count > 0:
    chart_col, pie_col = st.columns([2, 1])

    restatement_df = safe_query(
        con,
        """
        SELECT
            cik,
            metric,
            period_end,
            original_value,
            restated_value,
            restatement_filed_date,
            absolute_change,
            pct_change,
            severity,
            days_to_restatement
        FROM gold.fct_restatements
        ORDER BY restatement_filed_date DESC
        """,
    )

    with chart_col:
        st.subheader("Restatement Timeline")
        if not restatement_df.empty:
            fig_timeline = px.scatter(
                restatement_df,
                x="restatement_filed_date",
                y="pct_change",
                color="severity",
                size="absolute_change",
                hover_data=["cik", "metric", "original_value", "restated_value"],
                color_discrete_map={
                    "MATERIAL": "#f38ba8",
                    "NOTABLE": "#fab387",
                    "MINOR": "#a6e3a1",
                },
                labels={
                    "restatement_filed_date": "Restatement Filed Date",
                    "pct_change": "Percentage Change (%)",
                    "severity": "Severity",
                },
            )
            fig_timeline.update_layout(
                template="plotly_dark",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                height=400,
            )
            st.plotly_chart(fig_timeline, use_container_width=True)
        else:
            st.info("No restatement data to display.")

    with pie_col:
        st.subheader("Severity Distribution")
        if not restatement_df.empty:
            severity_counts = restatement_df["severity"].value_counts().reset_index()
            severity_counts.columns = ["severity", "count"]
            fig_pie = px.pie(
                severity_counts,
                values="count",
                names="severity",
                color="severity",
                color_discrete_map={
                    "MATERIAL": "#f38ba8",
                    "NOTABLE": "#fab387",
                    "MINOR": "#a6e3a1",
                },
            )
            fig_pie.update_layout(
                template="plotly_dark",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                height=400,
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("No severity data to display.")
else:
    st.info(
        "No restatements detected yet. Run `make transform` and `make detect` "
        "after ingesting data."
    )

# ===================================================================
# d. Top Anomalies
# ===================================================================
st.markdown("---")
st.subheader("Top Anomalies")

if has_anomalies:
    anomalies_df = safe_query(
        con,
        """
        SELECT
            anomaly_id,
            anomaly_type,
            cik,
            metric,
            period_end,
            expected_value,
            actual_value,
            absolute_change,
            pct_change,
            severity,
            severity_score,
            detected_date
        FROM gold.fct_anomalies
        ORDER BY severity_score DESC
        LIMIT 20
        """,
    )
    if not anomalies_df.empty:
        st.dataframe(
            anomalies_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "severity_score": st.column_config.ProgressColumn(
                    "Severity Score",
                    min_value=0,
                    max_value=100,
                    format="%d",
                ),
                "expected_value": st.column_config.NumberColumn(format="$%,.0f"),
                "actual_value": st.column_config.NumberColumn(format="$%,.0f"),
                "absolute_change": st.column_config.NumberColumn(format="$%,.0f"),
                "pct_change": st.column_config.NumberColumn(format="%.2f%%"),
            },
        )
    else:
        st.info("No anomalies found in the gold layer.")
else:
    st.info("Anomalies table not yet created. Run `make transform` to build gold layer models.")

# ===================================================================
# e. Company Deep Dive
# ===================================================================
st.markdown("---")
st.subheader("Company Deep Dive")

# Get list of companies with data
company_df = safe_query(
    con,
    "SELECT DISTINCT cik FROM bronze.raw_financial_facts ORDER BY cik",
)

if not company_df.empty:
    selected_cik = st.selectbox(
        "Select a Company (CIK)",
        options=company_df["cik"].tolist(),
    )

    if selected_cik:
        dive_col1, dive_col2 = st.columns(2)

        with dive_col1:
            st.markdown("**Restatements**")
            if has_restatements:
                company_restatements = safe_query(
                    con,
                    f"""
                    SELECT
                        metric,
                        period_end,
                        original_value,
                        restated_value,
                        pct_change,
                        severity,
                        restatement_filed_date,
                        days_to_restatement
                    FROM gold.fct_restatements
                    WHERE cik = '{selected_cik}'
                    ORDER BY restatement_filed_date DESC
                    """,
                )
                if not company_restatements.empty:
                    st.dataframe(company_restatements, use_container_width=True, hide_index=True)
                else:
                    st.info("No restatements found for this company.")
            else:
                st.info("Restatements table not available.")

        with dive_col2:
            st.markdown("**Filing History**")
            company_filings = safe_query(
                con,
                f"""
                SELECT
                    form_type,
                    filing_date,
                    period_of_report,
                    accession_number
                FROM bronze.raw_filings
                WHERE cik = '{selected_cik}'
                ORDER BY filing_date DESC
                LIMIT 20
                """,
            )
            if not company_filings.empty:
                st.dataframe(company_filings, use_container_width=True, hide_index=True)
            else:
                st.info("No filings found for this company.")
else:
    st.info("No company data available.")

# ===================================================================
# f. Data Quality Status
# ===================================================================
st.markdown("---")
st.subheader("Data Quality Status")

qual_col1, qual_col2, qual_col3 = st.columns(3)

with qual_col1:
    st.markdown("**Bronze Layer (Raw)**")
    bronze_tables = ["raw_filings", "raw_financial_facts", "raw_market_data"]
    for tbl in bronze_tables:
        count = get_row_count(con, "bronze", tbl)
        freshness = get_freshness(con, "bronze", tbl)
        st.metric(label=f"bronze.{tbl}", value=f"{count:,} rows")
        st.caption(f"Last ingested: {freshness}")

with qual_col2:
    st.markdown("**Silver Layer (Cleaned)**")
    silver_tables = ["stg_filings", "stg_financial_facts", "stg_market_data"]
    for tbl in silver_tables:
        if table_exists(con, "silver", tbl):
            count = get_row_count(con, "silver", tbl)
            st.metric(label=f"silver.{tbl}", value=f"{count:,} rows")
        else:
            st.metric(label=f"silver.{tbl}", value="Not built")
            st.caption("Run `make transform`")

with qual_col3:
    st.markdown("**Gold Layer (Analytics)**")
    gold_tables = [
        "fct_restatements",
        "fct_anomalies",
        "dim_companies",
        "dim_filing_periods",
    ]
    for tbl in gold_tables:
        if table_exists(con, "gold", tbl):
            count = get_row_count(con, "gold", tbl)
            st.metric(label=f"gold.{tbl}", value=f"{count:,} rows")
        else:
            st.metric(label=f"gold.{tbl}", value="Not built")
            st.caption("Run `make transform`")
