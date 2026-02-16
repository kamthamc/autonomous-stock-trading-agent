import streamlit as st
import pandas as pd
import sqlite3
import os
import json
import ast
from datetime import datetime
from agent_config import settings

# ──────────────────────────────────────────────
# Global Constants & Styles
# ──────────────────────────────────────────────
TRADING_DB = settings.trading_db_path

def apply_styles():
    st.markdown("""
    <style>
        /* Hide Streamlit Menu and Footer */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        
        /* Compact Metrics */
        div[data-testid="stMetricValue"] {
            font-size: 20px;
        }
        
        /* Danger Zone Style */
        .danger-zone {
            border: 1px solid #ff4b4b;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 10px;
        }
    </style>
    """, unsafe_allow_html=True)

# ──────────────────────────────────────────────
# DB Helpers
# ──────────────────────────────────────────────
def _current_activity_db() -> str:
    month_key = datetime.now().strftime("%Y_%m")
    return settings.get_activity_db_path(month_key)

@st.cache_data(ttl=3, show_spinner=False)
def query_db(db_path: str, query: str, params=(), format_dates=False):
    if not os.path.exists(db_path): return pd.DataFrame()
    try:
        # Use context manager for auto-close
        with sqlite3.connect(db_path) as conn:
            df = pd.read_sql_query(query, conn, params=params)
            
        if format_dates and not df.empty:
            # Vectorized optimization if possible, else robust loop
            for col in df.columns:
                if 'time' in col.lower():
                     # try safe conversion
                     try:
                         df[col] = pd.to_datetime(df[col]).dt.strftime('%d-%b-%Y %H:%M')
                     except: pass
        return df
    except: return pd.DataFrame()

def execute_db(db_path: str, query: str, params=()):
    if not os.path.exists(db_path): return False
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(query, params)
            conn.commit()
        # Invalidate cache if needed? Streamlit handles TTL.
        return True
    except: return False

def get_config(key: str, default: str) -> str:
    # We don't cache config aggressively to ensure toggle responsiveness
    # But usually query_db handles it. 
    # For critical config, maybe bypass cache? 
    # Actually, 3s lag on toggle state in dashboard is noticeable.
    # We should use a separate non-cached query for config or just accept 3s delay.
    # Check if we can override cache?
    # query_db.clear() clears ALL.
    # Let's use a direct non-cached call for config to ensure UI responsiveness.
    try:
        with sqlite3.connect(TRADING_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM app_config WHERE key = ?", (key,))
            res = cursor.fetchone()
            return res[0] if res else default
    except: return default

def save_config(key: str, value: str):
    execute_db(TRADING_DB, "CREATE TABLE IF NOT EXISTS app_config (key TEXT PRIMARY KEY, value TEXT, description TEXT, updated_at TIMESTAMP)")
    execute_db(TRADING_DB, "INSERT OR REPLACE INTO app_config (key, value, updated_at) VALUES (?, ?, ?)", (key, str(value), datetime.now()))
    # Clear data cache so UI updates immediately
    query_db.clear()

# ──────────────────────────────────────────────
# Log Readers
# ──────────────────────────────────────────────
@st.cache_data(ttl=5, show_spinner=False)
def read_logs(limit=200):
    log_path = settings.log_file_path
    if not os.path.exists(log_path): return []
    
    data = []
    try:
        with open(log_path, 'r') as f:
            # Read last N lines efficiently(ish)
            # Seeking to end implementation for large files would be better
            # But for <100MB simple readlines logic usually suffices if not frequent.
            # Caching protects us.
            try:
                f.seek(0, os.SEEK_END)
                file_size = f.tell()
                if file_size > 1024 * 1024: # If > 1MB, read only tail
                    # Rough estimation: 200 lines * 200 chars = 40KB. 
                    # Read last 100KB to be safe.
                    f.seek(max(file_size - 102400, 0))
                    lines = f.readlines()
                    # First line might be partial if we stood in middle
                    if len(lines) > 1: lines = lines[1:]
                else:
                    f.seek(0)
                    lines = f.readlines()
            except Exception:
                # Fallback
                return []
                
            lines = lines[-limit:]
            
            for line in lines:
                line = line.strip()
                if not line: continue
                
                entry = None
                # Try JSON first (New format)
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    # Fallback to ast.literal_eval (Old format: single quoted dicts)
                    try:
                        potential_dict = ast.literal_eval(line)
                        if isinstance(potential_dict, dict):
                            entry = potential_dict
                    except:
                        pass
                
                if entry:
                    # Normalize structlog 'event' to 'message' for dashboard compatibility
                    if 'message' not in entry and 'event' in entry:
                        entry['message'] = entry['event']
                        
                    # Format timestamp if present
                    if 'timestamp' in entry:
                        ts = str(entry['timestamp'])
                        try:
                            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            entry['timestamp'] = dt.strftime('%d-%b-%Y %H:%M')
                        except: pass
                    data.append(entry)
                    
    except Exception: return []
    
    return sorted(data, key=lambda x: x.get('timestamp', ''), reverse=True)
