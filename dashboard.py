import streamlit as st
import pandas as pd
import json
import sqlite3
import os
import time
from datetime import datetime
import plotly.express as px

st.set_page_config(page_title="Stock Agent Dashboard", layout="wide")
st.title("🤖 Autonomous Stock Trading Agent")

# Sidebar Filters
st.sidebar.header("Filters")
symbol_filter = st.sidebar.text_input("Symbol", "").upper()
limit_rows = st.sidebar.slider("Rows to Load", 100, 1000, 500)

# Auto-Refresh
st.sidebar.markdown("---")
st.sidebar.header("Auto-Refresh")
auto_refresh = st.sidebar.toggle("Enable Auto-Refresh", value=True)
refresh_interval = st.sidebar.selectbox(
    "Refresh Interval",
    options=[30, 60, 90, 120],
    index=1,
    format_func=lambda x: f"{x} seconds",
    disabled=not auto_refresh
)

if st.sidebar.button("🔄 Refresh Now"):
    st.rerun()

# ──────────────────────────────────────────────
# DB Helpers
# ──────────────────────────────────────────────
TRADING_DB = "trading_agent.db"

def _current_activity_db() -> str:
    """Returns the path to the current month's activity DB."""
    month_key = datetime.now().strftime("%Y_%m")
    return f"activity_{month_key}.db"

def query_db(db_path: str, query: str, params=()):
    """Runs a read query against a SQLite file. Returns a DataFrame."""
    if not os.path.exists(db_path):
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df
    except Exception as e:
        st.error(f"DB Error ({db_path}): {e}")
        return pd.DataFrame()


# ──────────────────────────────────────────────
# 1. AI Strategy Signals  (trading_agent.db)
# ──────────────────────────────────────────────
st.subheader("🧠 AI Strategy Signals")
df_signals = query_db(TRADING_DB, "SELECT * FROM signals ORDER BY timestamp DESC LIMIT ?", (limit_rows,))

if not df_signals.empty:
    if symbol_filter:
        df_signals = df_signals[df_signals['symbol'] == symbol_filter]
    
    cols = ["timestamp", "symbol", "decision", "confidence", "recommended_option", "reasoning"]
    available = [c for c in cols if c in df_signals.columns]
    st.dataframe(df_signals[available], use_container_width=True)
else:
    st.info("No signals generated yet.")

# ──────────────────────────────────────────────
# 1b. Upcoming Earnings Calendar
# ──────────────────────────────────────────────
with st.expander("📅 Upcoming Earnings Calendar", expanded=False):
    try:
        from strategy.earnings import get_bulk_earnings
        from agent_config import settings as agent_settings
        
        all_tickers = agent_settings.all_tickers
        if symbol_filter:
            all_tickers = [t for t in all_tickers if t == symbol_filter]
        
        earnings_data = get_bulk_earnings(all_tickers)
        
        # Build a display table
        earnings_rows = []
        for e in earnings_data:
            if e.earnings_date:
                warning = "⚠️" if e.is_within_warning_window else ""
                earnings_rows.append({
                    "Symbol": e.symbol,
                    "Earnings Date": e.earnings_date,
                    "Days Until": e.days_until_earnings,
                    "EPS Estimate": e.eps_estimate or "N/A",
                    "Alert": warning,
                })
        
        if earnings_rows:
            df_earnings = pd.DataFrame(earnings_rows).sort_values("Days Until", ascending=True)
            st.dataframe(df_earnings, use_container_width=True)
        else:
            st.info("No upcoming earnings dates found for monitored tickers.")
    except Exception as e:
        st.warning(f"Could not load earnings data: {e}")

# ──────────────────────────────────────────────
# 2. Devil's Advocate Reviews  (activity_YYYY_MM.db)
# ──────────────────────────────────────────────
st.subheader("😈 Devil's Advocate Reviews")
activity_db = _current_activity_db()
df_reviews = query_db(activity_db, "SELECT * FROM risk_reviews ORDER BY timestamp DESC LIMIT ?", (limit_rows,))

if not df_reviews.empty:
    if symbol_filter:
        df_reviews = df_reviews[df_reviews['symbol'] == symbol_filter]

    # Color-code by decision
    def highlight_decision(row):
        if row.get('review_decision') == 'APPROVE':
            return ['background-color: rgba(0, 180, 80, 0.15)'] * len(row)
        elif row.get('was_overridden'):
            return ['background-color: rgba(255, 165, 0, 0.15)'] * len(row)
        else:
            return ['background-color: rgba(255, 60, 60, 0.15)'] * len(row)

    cols = ["timestamp", "symbol", "original_decision", "original_confidence",
            "review_decision", "was_overridden", "review_reasoning"]
    available = [c for c in cols if c in df_reviews.columns]
    
    styled = df_reviews[available].style.apply(highlight_decision, axis=1)
    st.dataframe(styled, use_container_width=True)
    
    # Summary metrics
    col1, col2, col3 = st.columns(3)
    total = len(df_reviews)
    approved = len(df_reviews[df_reviews['review_decision'] == 'APPROVE']) if 'review_decision' in df_reviews.columns else 0
    rejected = total - approved
    overridden = len(df_reviews[df_reviews['was_overridden'] == 1]) if 'was_overridden' in df_reviews.columns else 0
    
    col1.metric("Total Reviews", total)
    col2.metric("Approved / Rejected", f"{approved} / {rejected}")
    col3.metric("Overridden (Paper)", overridden)
else:
    st.info(f"No risk reviews yet. (Looking in {activity_db})")

# ──────────────────────────────────────────────
# 3. Trades & Performance  (trading_agent.db)
# ──────────────────────────────────────────────
st.subheader("💰 Portfolio & Trades")
col1, col2 = st.columns(2)

df_trades = query_db(TRADING_DB, "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit_rows,))

if not df_trades.empty:
    if symbol_filter:
        df_trades = df_trades[df_trades['symbol'] == symbol_filter]

    with col1:
        st.write("Recent Trades")
        st.dataframe(df_trades, use_container_width=True)
    
    with col2:
        st.write("PnL Visualization")
        if 'pnl' in df_trades.columns:
            fig = px.bar(df_trades, x='timestamp', y='pnl', color='symbol', title="Realized PnL over Time")
            st.plotly_chart(fig, use_container_width=True)
            
            total_pnl = df_trades['pnl'].sum()
            st.metric("Total Realized PnL", f"${total_pnl:.2f}")
        else:
            st.info("PnL column not yet populated in DB.")
else:
    st.info("No trades executed yet.")

# ──────────────────────────────────────────────
# 4. Market Trends  (trading_agent.db)
# ──────────────────────────────────────────────
st.subheader("📈 AI Market Scanner Trends")
df_trends = query_db(TRADING_DB, "SELECT * FROM market_trends ORDER BY timestamp DESC LIMIT 10")
if not df_trends.empty:
    st.dataframe(df_trends, use_container_width=True)
else:
    st.info("No market scan results yet.")

# ──────────────────────────────────────────────
# 5. API Usage & Performance  (activity_YYYY_MM.db)
# ──────────────────────────────────────────────
st.subheader("📊 API Usage & Performance")

# Time range filter
from datetime import timedelta
api_time_range = st.selectbox(
    "Time Range",
    ["Today", "Last 6 hours", "Last 1 hour", "All (this month)"],
    index=0,
    key="api_time_range"
)

time_filter = ""
if api_time_range == "Today":
    today_start = datetime.now().replace(hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
    time_filter = f" WHERE timestamp >= '{today_start}'"
elif api_time_range == "Last 6 hours":
    since = (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")
    time_filter = f" WHERE timestamp >= '{since}'"
elif api_time_range == "Last 1 hour":
    since = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    time_filter = f" WHERE timestamp >= '{since}'"

df_api = query_db(activity_db, f"SELECT * FROM api_call_logs{time_filter} ORDER BY timestamp DESC LIMIT ?", (limit_rows,))

if not df_api.empty:
    # Summary metrics
    m1, m2, m3, m4 = st.columns(4)
    total_calls = len(df_api)
    success_count = len(df_api[df_api['success'] == 1]) if 'success' in df_api.columns else total_calls
    avg_latency = df_api['latency_ms'].mean() if 'latency_ms' in df_api.columns else 0
    
    total_prompt = df_api['prompt_tokens'].sum() if 'prompt_tokens' in df_api.columns else 0
    total_completion = df_api['completion_tokens'].sum() if 'completion_tokens' in df_api.columns else 0
    total_tok = df_api['total_tokens'].sum() if 'total_tokens' in df_api.columns else 0
    
    m1.metric("Total API Calls", total_calls)
    m2.metric("Success Rate", f"{(success_count / total_calls * 100):.0f}%")
    m3.metric("Avg Latency", f"{avg_latency:.0f} ms")
    m4.metric("Total Tokens", f"{int(total_tok):,}" if total_tok else "N/A")
    
    # Token breakdown
    if total_tok and total_tok > 0:
        t1, t2 = st.columns(2)
        t1.metric("Prompt Tokens", f"{int(total_prompt):,}" if total_prompt else "0")
        t2.metric("Completion Tokens", f"{int(total_completion):,}" if total_completion else "0")
    
    # Breakdown charts
    c1, c2 = st.columns(2)
    
    with c1:
        if 'source' in df_api.columns:
            source_counts = df_api['source'].value_counts().reset_index()
            source_counts.columns = ['source', 'count']
            fig_source = px.pie(source_counts, values='count', names='source', title="Calls by Source")
            st.plotly_chart(fig_source, use_container_width=True)
    
    with c2:
        if 'provider' in df_api.columns:
            provider_counts = df_api['provider'].value_counts().reset_index()
            provider_counts.columns = ['provider', 'count']
            fig_provider = px.pie(provider_counts, values='count', names='provider', title="Calls by Provider")
            st.plotly_chart(fig_provider, use_container_width=True)
    
    # Detailed table
    with st.expander("Detailed API Call Log", expanded=False):
        display_cols = ["timestamp", "source", "provider", "symbol", "latency_ms", 
                       "success", "prompt_tokens", "completion_tokens", "total_tokens", "error_message"]
        available = [c for c in display_cols if c in df_api.columns]
        st.dataframe(df_api[available], use_container_width=True)
else:
    st.info(f"No API calls logged yet. (Looking in {activity_db})")

# ──────────────────────────────────────────────
# 5. Live Logs  (agent_activity.log)
# ──────────────────────────────────────────────
with st.expander("📝 Live Agent Logs", expanded=False):
    log_file = "agent_activity.log"
    try:
        with open(log_file, "r") as f:
            lines = f.readlines()
            
            parsed_logs = []
            for line in lines[-limit_rows:]:
                try:
                    log_entry = json.loads(line)
                    if symbol_filter and log_entry.get("symbol") != symbol_filter:
                        continue
                    parsed_logs.append(log_entry)
                except json.JSONDecodeError:
                    continue
                    
            if parsed_logs:
                df_logs = pd.DataFrame(parsed_logs)
                cols = ["timestamp", "level", "event", "symbol", "decision", "confidence"]
                available_cols = [c for c in cols if c in df_logs.columns]
                other_cols = [c for c in df_logs.columns if c not in available_cols]
                st.dataframe(df_logs[available_cols + other_cols], height=300, use_container_width=True)
            else:
                st.info("No logs found matching criteria.")
    except FileNotFoundError:
        st.warning("Log file not found. Run the agent first!")

# Footer — Market Status & DB paths
st.sidebar.markdown("---")
st.sidebar.subheader("🌐 Market Status")
try:
    from strategy.market_hours import get_market_status
    mkt = get_market_status()
    
    # US Market
    us = mkt['us']
    if us['is_holiday']:
        us_icon = f"🔴 Closed ({us.get('holiday_name', 'Holiday')})"
    elif us.get('is_early_close'):
        us_icon = f"🟡 Early Close (until {us.get('close_time', '?')})"
    elif us.get('is_open'):
        us_icon = "🟢 Open"
    elif us.get('in_analysis_window'):
        us_icon = "🟡 Pre-Market"
    else:
        us_icon = "⚫ Closed"
    st.sidebar.caption(f"US ({us['time']} ET): {us_icon}")
    
    # India Market
    india = mkt['india']
    if india['is_holiday']:
        in_icon = f"🔴 Closed ({india.get('holiday_name', 'Holiday')})"
    elif india.get('is_early_close'):
        in_icon = f"🟡 Early Close (until {india.get('close_time', '?')})"
    elif india.get('is_open'):
        in_icon = "🟢 Open"
    elif india.get('in_analysis_window'):
        in_icon = "🟡 Pre-Market"
    else:
        in_icon = "⚫ Closed"
    st.sidebar.caption(f"India ({india['time']} IST): {in_icon}")
except Exception as e:
    st.sidebar.caption(f"Market status unavailable: {e}")

st.sidebar.markdown("---")
st.sidebar.caption(f"Trading DB: `{TRADING_DB}`")
st.sidebar.caption(f"Activity DB: `{activity_db}`")

# Auto-refresh trigger (must be at the very end)
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()
