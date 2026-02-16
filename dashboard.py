import streamlit as st
import pandas as pd
import json
import sqlite3
import asyncio
from datetime import datetime
import plotly.express as px
import time

st.set_page_config(page_title="Stock Agent Dashboard", layout="wide")
st.title("🤖 Autonomous Stock Trading Agent")

# Sidebar Filters
st.sidebar.header("Filters")
symbol_filter = st.sidebar.text_input("Symbol", "").upper()
limit_rows = st.sidebar.slider("Rows to Load", 100, 1000, 500)

# Auto-Refresh
if st.sidebar.button("Refresh Code"):
    st.rerun()

# 1. Live Logs (Tail)
st.subheader("📝 Live Agent Activity")
log_file = "agent_activity.log"

try:
    with open(log_file, "r") as f:
        lines = f.readlines()
        
        # Parse JSON logs
        parsed_logs = []
        for line in lines[-limit_rows:]:
            try:
                log_entry = json.loads(line)
                
                # Apply Symbol Filter to Logs if possible (if 'symbol' key exists)
                if symbol_filter and log_entry.get("symbol") != symbol_filter:
                    continue
                    
                parsed_logs.append(log_entry)
            except json.JSONDecodeError:
                continue
                
        # To DataFrame
        if parsed_logs:
            df_logs = pd.DataFrame(parsed_logs)
            
            # Reorder columns for readability
            cols = ["timestamp", "level", "event", "symbol", "decision", "confidence"]
            available_cols = [c for c in cols if c in df_logs.columns]
            other_cols = [c for c in df_logs.columns if c not in available_cols]
            
            st.dataframe(df_logs[available_cols + other_cols], height=300)
        else:
            st.info("No logs found matching criteria.")
            
except FileNotFoundError:
    st.warning("Log file not found. Run the agent first!")

# 2. Database Connection
DB_PATH = "trading_agent.db"

def get_db_data(query, params=()):
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df
    except Exception as e:
        st.error(f"DB Error: {e}")
        return pd.DataFrame()

# 3. Signals Review
st.subheader("🧠 AI Strategy Signals")
signals_query = "SELECT * FROM signals ORDER BY timestamp DESC LIMIT ?"
df_signals = get_db_data(signals_query, (limit_rows,))

if not df_signals.empty:
    if symbol_filter:
        df_signals = df_signals[df_signals['symbol'] == symbol_filter]
    
    # Reorder for better visibility
    cols = ["timestamp", "symbol", "decision", "confidence", "recommended_option", "reasoning"]
    available = [c for c in cols if c in df_signals.columns]
    st.dataframe(df_signals[available])
else:
    st.info("No signals generated yet.")

# 4. Trades & Performance
st.subheader("💰 Portfolio & Trades")
col1, col2 = st.columns(2)

trades_query = "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?"
df_trades = get_db_data(trades_query, (limit_rows,))

if not df_trades.empty:
    if symbol_filter:
        df_trades = df_trades[df_trades['symbol'] == symbol_filter]

    with col1:
        st.write("Recent Trades")
        st.dataframe(df_trades)
    
    with col2:
        st.write("PnL Visualization")
        # Calc PnL (Simplified: Sell Price - Buy Price)
        # In reality, need to match Buy/Sell orders. 
        # For now, just show a histogram of Trade Prices or similar if PnL col missing
        if 'pnl' in df_trades.columns:
             fig = px.bar(df_trades, x='timestamp', y='pnl', color='symbol', title="Realized PnL over Time")
             st.plotly_chart(fig)
             
             total_pnl = df_trades['pnl'].sum()
             st.metric("Total Realized PnL", f"${total_pnl:.2f}")
        else:
             st.info("PnL column not yet populated in DB.")

else:
    st.info("No trades executed yet.")

# 5. Market Trends
st.subheader("📈 AI Market Scanner Trends")
trends_query = "SELECT * FROM market_trends ORDER BY timestamp DESC LIMIT 10"
df_trends = get_db_data(trends_query)
if not df_trends.empty:
    st.dataframe(df_trends)
