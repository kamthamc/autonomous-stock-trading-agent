import streamlit as st
import pandas as pd
import plotly.express as px
import time
import os
from datetime import datetime
import yfinance as yf

# Use local utils
from dashboard_utils import (
    apply_styles, query_db, execute_db, get_config, save_config, 
    read_logs, _current_activity_db, TRADING_DB
)
from agent_config import settings

# ──────────────────────────────────────────────
# Page Config & Styles
# ──────────────────────────────────────────────
st.set_page_config(page_title="QUANTUM | Autonomous Agent", page_icon="🤖", layout="wide")
apply_styles() # Hides menu/footer

# ──────────────────────────────────────────────
# SESSION STATE & REFRESH
# ──────────────────────────────────────────────
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = time.time()

# ──────────────────────────────────────────────
# COMPACT HEADER (With Status)
# ──────────────────────────────────────────────
st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    h3 { margin-top: 0; padding-top: 0; }
    .stRadio [role=radiogroup] { padding-top: 10px; }
</style>
""", unsafe_allow_html=True)

c_title, c_ctrl = st.columns([3, 2])

with c_title:
    # Check Status from Logs
    logs = read_logs(limit=5)
    latest = logs[0] if logs else {}
    
    # Default
    status_text = "Active"
    status_bg = "#2ecc71" # Green
    status_pulse = "" # CSS pulse animation could be added here
    
    if not latest:
        status_text = "Offline"
        status_bg = "#95a5a6"
    else:
        evt = str(latest.get("event","")).lower()
        lvl = str(latest.get("level","")).lower()
        
        if "market_closed" in evt or "no_active_markets" in evt or "sleeping" in str(latest):
            status_text = "Markets Closed"
            status_bg = "#7f8c8d" # Gray
        elif "error" in lvl:
            status_text = "Error"
            status_bg = "#e74c3c" # Red
        elif "analyzing" in evt or "scan" in evt:
            status_text = "Analyzing"
            status_bg = "#f1c40f" # Yellow
            
    st.markdown(f"""
        <div style="display: flex; align-items: center;">
            <h3 style="margin: 0; padding: 0;">🤖 QUANTUM</h3>
            <span style="font-size: 0.8em; color: gray; margin-left: 10px;">| {settings.trading_mode.upper()}</span>
            <span style="background-color: {status_bg}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.7em; margin-left: 15px; font-weight: bold; box-shadow: 0 1px 2px rgba(0,0,0,0.1);">{status_text}</span>
        </div>
    """, unsafe_allow_html=True)

with c_ctrl:
    # Controls in a single tight row
    cc1, cc2, cc3 = st.columns([1.5, 1.5, 1])
    
    with cc1:
        # Kill Switch
        curr_status = get_config("TRADING_STATUS", "ACTIVE")
        is_active = curr_status == "ACTIVE"
        new_state = st.toggle("Trading Active", value=is_active)
        if new_state != is_active:
            new_status = "ACTIVE" if new_state else "PAUSED"
            save_config("TRADING_STATUS", new_status)
            st.rerun()
            
    with cc2:
        # Refresh Slider
        refresh_rate = st.select_slider("Refresh", options=[0, 30, 60, 300, 600], value=60, format_func=lambda x: "Off" if x==0 else f"{x}s", label_visibility="collapsed")
        
    with cc3:
        if st.button("🔄", use_container_width=True):
            st.session_state.last_refresh = time.time()
            st.rerun()

# ──────────────────────────────────────────────
# NAVIGATION (URL-BASED)
# ──────────────────────────────────────────────
TABS = ["Portfolio", "Activity", "Discovery", "System", "Settings"]
query_params = st.query_params
active_tab_param = query_params.get("tab", "portfolio").title()

if active_tab_param not in TABS:
    active_tab_param = "Portfolio"

st.write("") # Spacer
selected_tab = st.radio(
    "Navigation", 
    TABS, 
    horizontal=True, 
    label_visibility="collapsed", 
    index=TABS.index(active_tab_param),
    key="nav_radio"
)

if selected_tab != active_tab_param:
    st.query_params["tab"] = selected_tab.lower()
    st.rerun()

st.divider()

# ──────────────────────────────────────────────
# MAIN CONTENT FRAGMENT (PARTIAL REFRESH)
# ──────────────────────────────────────────────

@st.fragment(run_every=refresh_rate if refresh_rate > 0 else None)
def render_content(selected_tab):
    
    # 1. PORTFOLIO
    if selected_tab == "Portfolio":
        # Filter out failed trades to prevent phantom positions
        df_trades = query_db(TRADING_DB, "SELECT * FROM trades WHERE status NOT IN ('failed', 'error', 'rejected', 'REJECTED', 'CANCELLED') ORDER BY timestamp ASC", format_dates=False)
        
        # 1. METRICS & HOLDINGS
        if not df_trades.empty:
            df_trades['timestamp'] = pd.to_datetime(df_trades['timestamp'])
            
            # --- CALC HOLDINGS ---
            holdings = {}
            cumulative_pnl = []
            running_pnl_us = 0.0
            running_pnl_in = 0.0
            
            for _, row in df_trades.iterrows():
                sym = row['symbol']
                qty = float(row['quantity'])
                price = float(row['price'])
                action = row['action'].upper()
                region = "IN" if (".NS" in sym or ".BO" in sym) else "US"
                ts = row['timestamp']
                
                if sym not in holdings:
                    holdings[sym] = {"qty": 0, "avg": 0.0, "region": region, "realized": 0.0}
                
                h = holdings[sym]
                if action == "BUY":
                    cost = (h['qty'] * h['avg']) + (qty * price)
                    h['qty'] += qty
                    h['avg'] = cost / h['qty'] if h['qty'] > 0 else 0.0
                elif action == "SELL":
                    pnl = (price - h['avg']) * qty
                    h['realized'] += pnl
                    if region == "US": running_pnl_us += pnl
                    else: running_pnl_in += pnl
                    h['qty'] -= qty
                    
                    cumulative_pnl.append({"Time": ts, "US PnL": running_pnl_us, "IN PnL": running_pnl_in})

            # --- ACTIVE VALUES ---
            active_syms = [s for s, h in holdings.items() if h['qty'] > 0]
            live_prices = {}
            if active_syms:
                try:
                    tickers = yf.Tickers(" ".join(active_syms))
                    for s in active_syms:
                        try:
                            info = tickers.tickers[s].fast_info
                            if info and info.last_price: live_prices[s] = info.last_price
                            else: 
                                hist = tickers.tickers[s].history(period="1d")
                                live_prices[s] = hist['Close'].iloc[-1] if not hist.empty else 0.0
                        except: live_prices[s] = 0.0
                except: pass

            val_us = sum(holdings[s]['qty'] * live_prices.get(s, holdings[s]['avg']) for s in active_syms if holdings[s]['region']=="US")
            val_in = sum(holdings[s]['qty'] * live_prices.get(s, holdings[s]['avg']) for s in active_syms if holdings[s]['region']=="IN")

            # --- TOP METRICS ---
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("🇺🇸 Active Holdings", f"${val_us:,.2f}")
            m2.metric("🇮🇳 Active Holdings", f"₹{val_in:,.2f}")
            m3.metric("🇺🇸 Realized PnL", f"${running_pnl_us:,.2f}")
            m4.metric("🇮🇳 Realized PnL", f"₹{running_pnl_in:,.2f}")
            
        else:
            st.info("No trading data available yet. Check Activity tab for Market Status.")
            cumulative_pnl = []
            holdings = {}
            active_syms = []
            df_trades = pd.DataFrame() 

        # 2. CHARTS & ANALYTICS
        c_chart, c_active = st.columns([2, 1])
        
        with c_chart:
            st.subheader("📈 Performance Analytics")
            tab_perf1, tab_perf2 = st.tabs(["Equity Curve", "PnL by Symbol"])
            
            with tab_perf1:
                if cumulative_pnl:
                    df_chart = pd.DataFrame(cumulative_pnl)
                    df_melt = df_chart.melt('Time', var_name='Market', value_name='Cumulative PnL')
                    fig = px.line(df_melt, x='Time', y='Cumulative PnL', color='Market', markers=True, height=300)
                    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), xaxis_title=None, legend_title="")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.caption("Waiting for closed trades...")
                    
            with tab_perf2:
                if not df_trades.empty:
                    pnl_data = [{"Symbol": s, "Realized PnL": h['realized']} 
                                for s, h in holdings.items() if h['realized'] != 0]
                    
                    if pnl_data:
                        df_pnl = pd.DataFrame(pnl_data).sort_values("Realized PnL", ascending=True)
                        fig_bar = px.bar(df_pnl, y="Symbol", x="Realized PnL", orientation='h', 
                                         color="Realized PnL", color_continuous_scale="RdGn", height=300)
                        fig_bar.update_layout(yaxis_title=None, showlegend=False)
                        st.plotly_chart(fig_bar, use_container_width=True)
                    else:
                        st.info("No realized PnL yet.")
                else:
                    st.info("No trades.")

        with c_active:
            st.subheader("Active Positions")
            if not df_trades.empty and active_syms:
                rows = []
                for s in active_syms:
                    h = holdings[s]
                    p = live_prices.get(s, h['avg'])
                    rows.append({
                        "Symbol": s,
                        "Qty": h['qty'],
                        "Value": h['qty'] * p,
                        "Unrealized": (p - h['avg']) * h['qty']
                    })
                st.dataframe(
                    pd.DataFrame(rows).style.format({"Value": "{:,.2f}", "Unrealized": "{:+,.2f}"}), 
                    use_container_width=True, hide_index=True
                )
            else:
                st.caption("No active positions.")

    # 2. ACTIVITY
    elif selected_tab == "Activity":
        st.markdown("### 🧠 Strategies & Risk Review")
        st.caption("Integrated timeline showing why the AI picked a stock (Strategy) and the Risk Manager's verdict.")
        
        # Fetch Data
        df_sig = query_db(TRADING_DB, "SELECT timestamp, symbol, decision, confidence, reasoning as signal_reasoning FROM signals ORDER BY timestamp DESC LIMIT 100", format_dates=False)
        adb = _current_activity_db()
        df_rev = query_db(adb, "SELECT timestamp, symbol, review_decision, review_reasoning FROM risk_reviews ORDER BY timestamp DESC LIMIT 100", format_dates=False)
        
        if not df_sig.empty:
            df_sig['timestamp'] = pd.to_datetime(df_sig['timestamp'])
            
            if not df_rev.empty:
                df_rev['timestamp'] = pd.to_datetime(df_rev['timestamp'])
                df_sig = df_sig.sort_values('timestamp')
                df_rev = df_rev.sort_values('timestamp')
                
                try:
                    df_merged = pd.merge_asof(
                        df_sig, df_rev, on='timestamp', by='symbol', direction='forward', tolerance=pd.Timedelta(seconds=60), suffixes=('', '_rev')
                    )
                except:
                    df_merged = df_sig.copy()
                    df_merged['review_reasoning'] = "Pending or Missing"
                    df_merged['review_decision'] = "N/A"
            else:
                df_merged = df_sig.copy()
                df_merged['review_decision'] = "PENDING"
                df_merged['review_reasoning'] = "No review found"

            # Explicitly fill NaNs to avoid Streamlit serialization errors
            if 'review_decision' in df_merged.columns:
                df_merged['review_decision'] = df_merged['review_decision'].fillna("PENDING")
            if 'review_reasoning' in df_merged.columns:
                df_merged['review_reasoning'] = df_merged['review_reasoning'].fillna("Pending review...")

            # Display
            df_display = df_merged.sort_values('timestamp', ascending=False)
            st.dataframe(
                df_display[['timestamp', 'symbol', 'decision', 'signal_reasoning', 'confidence', 'review_decision', 'review_reasoning']],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "timestamp": st.column_config.DatetimeColumn("Time", format="MM-DD HH:mm"),
                    "symbol": st.column_config.TextColumn("Ticker", width="small"),
                    "decision": st.column_config.TextColumn("Signal", width="small"),
                    "signal_reasoning": st.column_config.TextColumn("Strategy Logic", width="large"),
                    "confidence": st.column_config.NumberColumn("Conf", format="%.2f"),
                    "review_decision": st.column_config.TextColumn("Risk Status", width="small"),
                    "review_reasoning": st.column_config.TextColumn("Risk Critique", width="large")
                }
            )
        else:
            # User-friendly Empty State
            msg = "No AI Signals generated yet."
            logs = read_logs(limit=5)
            if logs and ("market_closed" in str(logs[0].get('event','')) or "no_active_markets" in str(logs[0].get('event',''))):
                msg += " Markets appear to be closed. AI is sleeping."
            st.info(msg)

    # 3. DISCOVERY
    elif selected_tab == "Discovery":
        st.markdown("### 🔎 Market Discovery")
        
        # Predefined Lists
        DISCOVERY_LISTS = {
            "🇺🇸 US Tech Giants": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "AMD", "CRM"],
            "🇺🇸 US Semiconductors": ["NVDA", "AMD", "INTC", "QCOM", "TXN", "MU", "AVGO"],
            "🇺🇸 US Finance": ["JPM", "BAC", "WFC", "C", "GS", "MS", "BLK", "AXP"],
            "🇺🇸 Crypto Proxies": ["MSTR", "COIN", "MARA", "RIOT", "CLSK"],
            "🇮🇳 Nifty IT": ["INFY.NS", "TCS.NS", "HCLTECH.NS", "WIPRO.NS", "TECHM.NS"],
            "🇮🇳 Nifty Bank": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS"],
            "🇮🇳 Nifty Pharma": ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS"],
            "🇮🇳 Nifty Auto": ["TATAMOTORS.NS", "M&M.NS", "MARUTI.NS", "BAJAJ-AUTO.NS"],
        }
        
        c_sel, c_btn = st.columns([3, 1])
        with c_sel:
            def_idx = 0
            if 'scan_key' in st.session_state and st.session_state['scan_key'] in DISCOVERY_LISTS:
                def_idx = list(DISCOVERY_LISTS.keys()).index(st.session_state['scan_key'])
            
            sel_list = st.selectbox("Select Sector / Index", list(DISCOVERY_LISTS.keys()), index=def_idx)
        
        scan_syms = DISCOVERY_LISTS[sel_list]
        
        if c_btn.button("🚀 Scan Sector", use_container_width=True):
            with st.spinner(f"Scanning {len(scan_syms)} assets..."):
                data = []
                try:
                    tickers = yf.Tickers(" ".join(scan_syms))
                    for s in scan_syms:
                        try:
                            fi = tickers.tickers[s].fast_info
                            last = fi.last_price
                            prev = fi.previous_close
                            if last and prev:
                                chg = ((last - prev) / prev) * 100
                                data.append({
                                    "Symbol": s, "Price": last, "Change %": chg, 
                                    "Volume": fi.last_volume, "Mkt Cap": fi.market_cap
                                })
                        except: pass
                except: pass
                
                if data:
                    df_scan = pd.DataFrame(data).sort_values("Change %", ascending=False)
                    df_scan['Add'] = False # Checkbox col
                    st.session_state['scan_results'] = df_scan
                    st.session_state['scan_key'] = sel_list
                else:
                    st.warning("Failed to fetch data.")

        if 'scan_results' in st.session_state and not st.session_state['scan_results'].empty:
            st.divider()
            st.write(f"### Results: {st.session_state.get('scan_key', 'Custom')}")
            
            edited_df = st.data_editor(
                st.session_state['scan_results'], 
                column_config={
                    "Add": st.column_config.CheckboxColumn(required=True),
                    "Price": st.column_config.NumberColumn(format="%.2f"),
                    "Change %": st.column_config.NumberColumn(format="%.2f%%"),
                    "Mkt Cap": st.column_config.NumberColumn(format="$%.0e"),
                },
                use_container_width=True,
                hide_index=True,
                key="editor_scan"
            )
            
            to_add = edited_df[edited_df['Add']]['Symbol'].tolist()
            if to_add:
                if st.button(f"Add {len(to_add)} to Watchlist"):
                    key_ctx = st.session_state.get('scan_key', sel_list)
                    is_us = "🇺🇸" in key_ctx
                    cfg_key = "US_TICKERS" if is_us else "INDIA_TICKERS"
                    curr_list = settings.us_tickers if is_us else settings.india_tickers
                    updated_list = list(set(curr_list + to_add))
                    save_config(cfg_key, ",".join(updated_list))
                    st.success(f"Added to {cfg_key}! Restart Agent to apply.")

    # 4. SYSTEM
    elif selected_tab == "System":
        st.markdown("### 🔌 System Health & Cache Intelligence")
        
        logs = read_logs(1000)
        
        # API Stats
        adb = _current_activity_db()
        q_api = "SELECT * FROM api_call_logs ORDER BY timestamp DESC LIMIT 2000"
        df_api = query_db(adb, q_api, format_dates=False)
        
        m1, m2, m3, m4 = st.columns(4)
        if not df_api.empty:
             # Ensure Token Cols exist
            for col in ['total_tokens', 'prompt_tokens', 'completion_tokens', 'latency_ms']:
                if col not in df_api.columns: df_api[col] = 0
                
            m1.metric("Total Calls", len(df_api))
            m2.metric("Total Tokens", f"{int(df_api['total_tokens'].sum()):,}")
            m3.metric("Avg Latency", f"{df_api['latency_ms'].mean():.0f} ms")
            
            # Cache Hit Rate
            hits = 0
            total_checks = 0
            # Better: calculate from ALL cache hit events? 
            # Actually the log says "hit_rate": "46.5%" in the entry.
            last_hit_rate = "0%"
            for entry in logs:
                if "cache_stats" in entry:
                    last_hit_rate = entry["cache_stats"].get("hit_rate", "0%")
                    break
            
            m4.metric("Cache Hit Rate", last_hit_rate)
            
            st.divider()
            
            # Charts
            c_chart1, c_chart2 = st.columns(2)
            
            with c_chart1:
                st.subheader("📊 Token Usage Profile")
                in_tok = df_api['prompt_tokens'].sum()
                out_tok = df_api['completion_tokens'].sum()
                
                df_tok = pd.DataFrame([
                    {"Type": "Prompt (Input)", "Tokens": in_tok},
                    {"Type": "Completion (Output)", "Tokens": out_tok}
                ])
                
                fig_pie = px.pie(df_tok, names='Type', values='Tokens', hole=0.4, 
                                 title="Token Usage Breakdown", color_discrete_sequence=['#36a2eb', '#ff6384'])
                st.plotly_chart(fig_pie, use_container_width=True)
                
            with c_chart2:
                st.subheader("🚀 Cache Efficiency Trend")
                cache_trend = []
                for entry in logs:
                     if "cache_stats" in entry:
                         cache_trend.append({
                             "Time": entry.get("timestamp"), 
                             "Hit Rate": float(str(entry["cache_stats"].get("hit_rate", "0")).strip('%'))
                         })
                
                if cache_trend:
                    df_cache = pd.DataFrame(cache_trend).head(50).iloc[::-1]
                    fig_cache = px.line(df_cache, x='Time', y='Hit Rate', markers=True, title="LLM Cache Hit Rate %")
                    fig_cache.update_traces(line_color='#4bc0c0')
                    st.plotly_chart(fig_cache, use_container_width=True)
                else:
                    st.info("No cache stats found.")
        else:
            st.info("No API activity yet.")

    # 5. CONFIG
    elif selected_tab == "Settings":
        st.markdown("### ⚙️ Configuration")
        
        curr_us = get_config("US_TICKERS", ",".join(settings.us_tickers))
        curr_in = get_config("INDIA_TICKERS", ",".join(settings.india_tickers))
        def_alloc = get_config("RISK_MAX_ALLOC_PCT", "20")
        def_risk = get_config("RISK_MAX_RISK_PCT", "2")
        
        with st.form("conf"):
            st.write("#### 📝 Watchlists")
            c1, c2 = st.columns(2)
            with c1: new_us = st.text_area("🇺🇸 US Tickers", curr_us, height=100)
            with c2: new_in = st.text_area("🇮🇳 India Tickers", curr_in, height=100)
            
            st.divider()
            st.write("#### 🛡️ Risk & Capital")
            c3, c4 = st.columns(2)
            with c3: alloc_pct = st.number_input("Max Allocation (%)", 1, 100, int(float(def_alloc)))
            with c4: risk_pct = st.number_input("Max Risk Cost (%)", 1, 100, int(float(def_risk)))
                
            if st.form_submit_button("Save Configuration", type="primary"):
                clean_us = ",".join([t.strip().upper() for t in new_us.replace('\n', ',').split(',') if t.strip()])
                clean_in = ",".join([t.strip().upper() for t in new_in.replace('\n', ',').split(',') if t.strip()])
                
                save_config("US_TICKERS", clean_us)
                save_config("INDIA_TICKERS", clean_in)
                save_config("RISK_MAX_ALLOC_PCT", str(alloc_pct))
                save_config("RISK_MAX_RISK_PCT", str(risk_pct))
                
                st.success("Configuration Saved! Restart Agent to apply risk changes.")
                time.sleep(1)
                st.rerun()

        st.divider()
        st.subheader("⚠️ Danger Zone")
        c_del1, c_del2, c_del3 = st.columns(3)
        if c_del1.button("🗑️ Clear Trades"):
            execute_db(TRADING_DB, "DELETE FROM trades")
            st.success("Trades Cleared")
            time.sleep(1)
            st.rerun()
            
        if c_del2.button("🗑️ Clear Logs"):
            adb = _current_activity_db()
            execute_db(adb, "DELETE FROM api_call_logs")
            execute_db(adb, "DELETE FROM risk_reviews")
            st.success("Logs Cleared")
            time.sleep(1)
            st.rerun()
            
        if c_del3.button("🔥 Factory Reset"):
             execute_db(TRADING_DB, "DELETE FROM trades")
             execute_db(TRADING_DB, "DELETE FROM signals")
             execute_db(TRADING_DB, "DELETE FROM market_trends")
             st.error("System Reset")
             time.sleep(1)
             st.rerun()

# Call the fragmented renderer
render_content(selected_tab)
