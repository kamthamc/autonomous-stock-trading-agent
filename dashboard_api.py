"""
QUANTUM Dashboard — FastAPI Backend
Serves REST API + static frontend from dashboard/ directory.
Run: python dashboard_api.py   (uvicorn on :8050)
"""

import os
import sys
import json
import ast
import sqlite3
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent_config import settings

# ── Paths ──
TRADING_DB = settings.trading_db_path
DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), "dashboard")

# Add strategy dir to path so we can import fx module
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategy"))
try:
    from strategy.fx import get_usd_inr_rate
except ImportError:
    # Fallback if strategy module not fully available yet
    def get_usd_inr_rate(): return 83.5

# Valid trade statuses (exclude failed/error/rejected)
VALID_TRADE_STATUSES = ("placed", "FILLED", "filled", "COMPLETED", "completed")


def _activity_db() -> str:
    month_key = datetime.now().strftime("%Y_%m")
    return settings.get_activity_db_path(month_key)


def _query(db_path: str, sql: str, params=()):
    """Run a read query and return list of dicts."""
    if not os.path.exists(db_path):
        return []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _execute(db_path: str, sql: str, params=()):
    if not os.path.exists(db_path):
        return False
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(sql, params)
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def _get_config(key: str, default: str = "") -> str:
    rows = _query(TRADING_DB, "SELECT value FROM app_config WHERE key = ?", (key,))
    return rows[0]["value"] if rows else default


def _read_logs(limit: int = 200):
    log_path = settings.log_file_path
    if not os.path.exists(log_path):
        return []
    data = []
    try:
        with open(log_path, "r") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size > 1_048_576:
                f.seek(max(size - 102_400, 0))
                lines = f.readlines()
                if len(lines) > 1:
                    lines = lines[1:]
            else:
                f.seek(0)
                lines = f.readlines()
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            entry = None
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                try:
                    p = ast.literal_eval(line)
                    if isinstance(p, dict):
                        entry = p
                except Exception:
                    pass
            if entry:
                if "message" not in entry and "event" in entry:
                    entry["message"] = entry["event"]
                data.append(entry)
    except Exception:
        pass
    return sorted(data, key=lambda x: x.get("timestamp", ""), reverse=True)


# ── FastAPI App ──
app = FastAPI(title="QUANTUM Dashboard API")


# ── API Routes ──

@app.get("/api/system-status")
def system_status():
    """Smarter status detection — looks at recent activity, not just last log level."""
    logs = _read_logs(20)
    trading_status = _get_config("TRADING_STATUS", "ACTIVE")

    status = "Active"
    if not logs:
        status = "Offline"
    else:
        # Check recent events (not just the very last line)
        recent_events = [str(l.get("event", "")).lower() for l in logs[:10]]

        if any("market_closed" in e or "no_active_markets" in e for e in recent_events):
            status = "Markets Closed"
        elif any("analyzing" in e or "scan" in e or "cycle_start" in e for e in recent_events):
            status = "Analyzing"
        elif any("ai_signal" in e or "trade" in e for e in recent_events):
            status = "Active"
        else:
            # Fallback: check if last event was recent (within 5 min)
            latest_ts = logs[0].get("timestamp", "")
            try:
                last_dt = datetime.fromisoformat(str(latest_ts).replace("Z", "+00:00").replace(" ", "T"))
                diff = (datetime.now() - last_dt.replace(tzinfo=None)).total_seconds()
                if diff > 300:
                    status = "Idle"
                else:
                    status = "Active"
            except Exception:
                status = "Active"

    return {
        "status": status,
        "trading_active": trading_status == "ACTIVE",
        "trading_mode": settings.trading_mode,
        "trading_style": settings.trading_style,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/portfolio")
def portfolio():
    """Portfolio with valid trades only, portfolio value timeline, and position data."""
    # FX Rate
    usd_inr_rate = get_usd_inr_rate()
    
    # Only count valid (non-failed) trades
    trades = _query(
        TRADING_DB,
        """SELECT * FROM trades
           WHERE status IN ('placed','FILLED','filled','COMPLETED','completed')
           ORDER BY timestamp ASC""",
    )
    
    # Try fetching True Account Equity tracking from db
    equity_snapshots = _query(
        TRADING_DB,
        "SELECT * FROM account_equity_snapshots ORDER BY timestamp ASC"
    )
    holdings: dict = {}
    running_pnl_us = 0.0
    running_pnl_in = 0.0
    total_fees_us = 0.0
    total_fees_in = 0.0

    # Build portfolio value over time (cumulative invested value)
    value_timeline = []
    running_invested_us = 0.0
    running_invested_in = 0.0
    
    # Advanced Metrics
    winning_trades = 0
    losing_trades = 0
    gross_profit_us = 0.0
    gross_loss_us = 0.0
    gross_profit_in = 0.0
    gross_loss_in = 0.0
    
    peak_global_pnl = 0.0
    max_pnl_drawdown_usd = 0.0

    for t in trades:
        sym = t["symbol"]
        qty = float(t["quantity"])
        price = float(t["price"])
        action = t["action"].upper()
        region = "IN" if (".NS" in sym or ".BO" in sym) else "US"
        fees = float(t.get("estimated_fees") or 0)

        if region == "US":
            total_fees_us += fees
        else:
            total_fees_in += fees

        if sym not in holdings:
            holdings[sym] = {"qty": 0, "avg": 0.0, "region": region, "realized": 0.0}

        h = holdings[sym]
        if action == "BUY":
            cost = (h["qty"] * h["avg"]) + (qty * price)
            h["qty"] += qty
            h["avg"] = cost / h["qty"] if h["qty"] > 0 else 0.0
            if region == "US":
                running_invested_us += qty * price
            else:
                running_invested_in += qty * price
        elif action in ("SELL", "PARTIAL_SELL"):
            pnl = (price - h["avg"]) * qty
            h["realized"] += pnl
            if region == "US":
                running_pnl_us += pnl
                running_invested_us -= qty * h["avg"]
                if pnl > 0:
                    winning_trades += 1
                    gross_profit_us += pnl
                elif pnl < 0:
                    losing_trades += 1
                    gross_loss_us += abs(pnl)
            else:
                running_pnl_in += pnl
                running_invested_in -= qty * h["avg"]
                if pnl > 0:
                    winning_trades += 1
                    gross_profit_in += pnl
                elif pnl < 0:
                    losing_trades += 1
                    gross_loss_in += abs(pnl)
            h["qty"] -= qty
            
            # Drawdown (calculated on realized PNL Curve)
            current_global_pnl = running_pnl_us + (running_pnl_in / usd_inr_rate)
            if current_global_pnl > peak_global_pnl:
                peak_global_pnl = current_global_pnl
            drawdown = peak_global_pnl - current_global_pnl
            if drawdown > max_pnl_drawdown_usd:
                max_pnl_drawdown_usd = drawdown

        value_timeline.append({
            "time": t["timestamp"],
            "us_value": round(running_invested_us, 2),
            "in_value": round(running_invested_in, 2),
            "us_pnl": round(running_pnl_us, 2),
            "in_pnl": round(running_pnl_in, 2),
        })

    active = []
    for sym, h in holdings.items():
        if h["qty"] > 0:
            active.append({
                "symbol": sym,
                "quantity": h["qty"],
                "avg_price": round(h["avg"], 2),
                "region": h["region"],
                "realized": round(h["realized"], 2),
            })

    total_closed = winning_trades + losing_trades
    global_gross_profit = gross_profit_us + (gross_profit_in / usd_inr_rate)
    global_gross_loss = gross_loss_us + (gross_loss_in / usd_inr_rate)
    
    advanced_metrics = {
        "win_rate": round((winning_trades / total_closed * 100) if total_closed > 0 else 0.0, 1),
        "profit_factor": round((global_gross_profit / global_gross_loss) if global_gross_loss > 0 else (99.9 if global_gross_profit > 0 else 0.0), 2),
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "max_drawdown_usd": round(max_pnl_drawdown_usd, 2)
    }

    return {
        "active_positions": active,
        "value_timeline": value_timeline,
        "true_equity_timeline": equity_snapshots,  # If empty, frontend uses value_timeline as fallback
        "live_usd_inr": usd_inr_rate,
        "us_realized_pnl": round(running_pnl_us, 2),
        "in_realized_pnl": round(running_pnl_in, 2),
        "us_fees": round(total_fees_us, 2),
        "in_fees": round(total_fees_in, 2),
        "total_trades": len(trades),
        "advanced_metrics": advanced_metrics,
    }


@app.get("/api/trades")
def trades(limit: int = Query(100, ge=1, le=1000)):
    """Only return valid (non-failed) trades, deduped by order_id."""
    rows = _query(
        TRADING_DB,
        """SELECT * FROM trades
           WHERE status IN ('placed','FILLED','filled','COMPLETED','completed')
             AND (order_id IS NULL OR order_id != 'error')
           ORDER BY timestamp DESC LIMIT ?""",
        (limit,),
    )
    # Deduplicate by order_id (keep the latest entry for each)
    seen_ids = set()
    deduped = []
    for r in rows:
        oid = r.get("order_id")
        if oid and oid in seen_ids:
            continue
        if oid:
            seen_ids.add(oid)
        deduped.append(r)
    return deduped


class ManualTradeRequest(BaseModel):
    symbol: str
    action: str
    quantity: float
    price: float
    order_type: str = "MARKET"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    asset_type: str = "STOCK"
    option_strike: Optional[float] = None
    option_expiry: Optional[str] = None
    region: str = "US"


@app.post("/api/manual-trade")
def execute_manual_trade(trade: ManualTradeRequest):
    """
    Endpoint for dashboard to record a manual trade directly.
    In a fully integrated setup, this would also call the Broker API.
    For now, we record it in the DB to ensure dashboard tracking is accurate.
    """
    # Create required tables if missing (for legacy or robust starts)
    _execute(TRADING_DB, "CREATE TABLE IF NOT EXISTS trades (...)") # Rely on Alembic/migrations in production
    
    timestamp = datetime.now().isoformat()
    order_id = f"manual_{int(datetime.now().timestamp())}"
    
    sql = """
        INSERT INTO trades (
            timestamp, symbol, action, quantity, price, status, order_id, 
            region, strategy, pnl, estimated_fees, net_pnl, fee_currency,
            is_manual, order_type, limit_price, stop_price, asset_type, 
            option_strike, option_expiry
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        timestamp, trade.symbol.upper(), trade.action.upper(), trade.quantity, trade.price, 
        "FILLED" if trade.order_type == "MARKET" else "PENDING", 
        order_id, trade.region, "MANUAL_DASHBOARD", 0.0, 0.0, 0.0, 
        "USD" if trade.region == "US" else "INR",
        True, trade.order_type, trade.limit_price, trade.stop_price, trade.asset_type,
        trade.option_strike, trade.option_expiry
    )
    
    success = _execute(TRADING_DB, sql, params)
    if success:
        return {"ok": True, "order_id": order_id, "message": f"Manual {trade.action} logged."}
    return JSONResponse(status_code=500, content={"error": "Database insert failed."})


class WatchTickerRequest(BaseModel):
    symbol: str
    region: str
    notes: Optional[str] = None


@app.post("/api/watched-tickers")
def add_watched_ticker(req: WatchTickerRequest):
    timestamp = datetime.now().isoformat()
    sql = "INSERT INTO watched_tickers (added_at, symbol, region, notes) VALUES (?, ?, ?, ?)"
    success = _execute(TRADING_DB, sql, (timestamp, req.symbol.upper(), req.region, req.notes))
    if success:
        return {"ok": True, "symbol": req.symbol}
    return JSONResponse(status_code=500, content={"error": "Database insert failed."})


@app.get("/api/watched-tickers")
def get_watched_tickers():
    return _query(TRADING_DB, "SELECT * FROM watched_tickers ORDER BY added_at DESC")


@app.delete("/api/watched-tickers/{symbol}")
def delete_watched_ticker(symbol: str):
    success = _execute(TRADING_DB, "DELETE FROM watched_tickers WHERE symbol = ?", (symbol.upper(),))
    return {"ok": success}


@app.get("/api/ai-decisions")
def ai_decisions(
    limit: int = Query(100, ge=1, le=500),
    symbol: Optional[str] = None,
    decision: Optional[str] = None,
):
    """
    Tries to get full logs from ai_decision_logs (activity DB).
    Falls back to signals (trading DB) if activity logs are missing.
    """
    adb = _activity_db()
    
    # Try fetching full Decision Logs first (has technicals, news, etc.)
    full_logs = _query(
        adb, 
        f"SELECT * FROM ai_decision_logs {'WHERE symbol=?' if symbol else ''} ORDER BY timestamp DESC LIMIT ?", 
        (symbol, limit) if symbol else (limit,)
    )
    
    # If we have full logs, enrich them and return
    if full_logs:
        # Filter by decision if needed
        if decision:
            full_logs = [l for l in full_logs if decision.upper() in (l["decision"] or "").upper()]
            
        enriched = []
        for log in full_logs:
            # Parse JSON fields for frontend
            try: log["technical_summary"] = json.loads(log["technical_summary"]) if log["technical_summary"] else None
            except: pass
            try: log["macro_factors"] = json.loads(log["macro_factors"]) if log["macro_factors"] else None
            except: pass
            try: log["news_headlines"] = json.loads(log["news_headlines"]) if log["news_headlines"] else None
            except: pass
            
            enriched.append(log)
        return enriched

    # Fallback: Use signals table (trading DB)
    sql = "SELECT * FROM signals WHERE 1=1"
    params = []
    if symbol:
        sql += " AND symbol = ?"
        params.append(symbol.upper())
    if decision:
        sql += " AND decision LIKE ?"
        params.append(f"%{decision.upper()}%")
    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    signals = _query(TRADING_DB, sql, tuple(params))

    # Enrich with risk reviews from activity DB
    reviews = _query(adb, "SELECT * FROM risk_reviews ORDER BY timestamp DESC LIMIT 500")
    review_map = {}
    for r in reviews:
        # Best effort matching: symbol + timestamp proximity or just symbol + decision
        # Since we don't have exact ID link, we map by symbol
        if r['symbol'] not in review_map:
            review_map[r['symbol']] = []
        review_map[r['symbol']].append(r)

    enriched = []
    for s in signals:
        # Find closest risk review?
        # For simple fallback, just attach the latest review for this symbol if it matches decision
        # This is imperfect but better than nothing for fallback
        relevant_reviews = review_map.get(s['symbol'], [])
        matching_review = next((r for r in relevant_reviews if r.get('original_decision') == s['decision']), None)
        
        enriched.append({
            "timestamp": s["timestamp"],
            "symbol": s["symbol"],
            "decision": s["decision"],
            "confidence": s["confidence"],
            "reasoning": s["reasoning"],
            "target_buy_price": s.get("target_buy_price"),
            "target_sell_price": s.get("target_sell_price"),
            "stop_loss_suggestion": s.get("stop_loss"),
            "option_strike": s.get("option_strike"),
            "option_expiry": s.get("option_expiry"),
            "review_decision": matching_review.get("review_decision") if matching_review else None,
            "review_reasoning": matching_review.get("review_reasoning") if matching_review else None,
            "was_overridden": matching_review.get("was_overridden", False) if matching_review else False,
            "fallback_mode": True # Frontend can hide technical section
        })

    return enriched


@app.get("/api/signals")
def signals(limit: int = Query(100, ge=1, le=500)):
    sigs = _query(
        TRADING_DB,
        "SELECT * FROM signals ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    adb = _activity_db()
    reviews = _query(
        adb,
        "SELECT * FROM risk_reviews ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    return {"signals": sigs, "reviews": reviews}


@app.get("/api/news")
def news(limit: int = Query(100, ge=1, le=500)):
    adb = _activity_db()
    rows = _query(
        adb,
        "SELECT * FROM news_fingerprints ORDER BY first_seen DESC LIMIT ?",
        (limit,),
    )
    # If news_fingerprints table doesn't exist, return empty
    return rows


@app.get("/api/metrics")
def metrics():
    adb = _activity_db()
    api_calls = _query(adb, "SELECT * FROM api_call_logs ORDER BY timestamp DESC LIMIT 2000")

    total_calls = len(api_calls)
    total_tokens = sum(int(c.get("total_tokens") or 0) for c in api_calls)
    prompt_tokens = sum(int(c.get("prompt_tokens") or 0) for c in api_calls)
    completion_tokens = sum(int(c.get("completion_tokens") or 0) for c in api_calls)
    avg_latency = (
        sum(int(c.get("latency_ms") or 0) for c in api_calls) / total_calls
        if total_calls
        else 0
    )
    success_calls = sum(1 for c in api_calls if c.get("success", True))

    # Source breakdown
    source_counts = {}
    for c in api_calls:
        src = c.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1

    # Latency trend (last 50 calls)
    latency_trend = []
    for c in api_calls[:50]:
        latency_trend.append({
            "time": c.get("timestamp", ""),
            "latency_ms": int(c.get("latency_ms") or 0),
            "source": c.get("source", ""),
        })

    # Signal decision distribution from signals table
    signal_dist = _query(
        TRADING_DB,
        "SELECT decision, COUNT(*) as count FROM signals GROUP BY decision",
    )

    return {
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "avg_latency_ms": round(avg_latency),
        "success_rate": round((success_calls / total_calls * 100) if total_calls else 0, 1),
        "source_breakdown": [{"source": k, "count": v} for k, v in sorted(source_counts.items(), key=lambda x: -x[1])],
        "decision_distribution": signal_dist,
        "latency_trend": latency_trend,
    }


@app.get("/api/config")
def get_config():
    rows = _query(TRADING_DB, "SELECT * FROM app_config ORDER BY key")
    return {
        "config": {r["key"]: r["value"] for r in rows},
        "defaults": {
            "us_tickers": ",".join(settings.us_tickers),
            "india_tickers": ",".join(settings.india_tickers),
            "trading_mode": settings.trading_mode,
            "trading_style": settings.trading_style,
            "us_max_capital": settings.us_max_capital,
            "india_max_capital": settings.india_max_capital,
        },
    }


class ConfigUpdate(BaseModel):
    key: str
    value: str


@app.post("/api/config")
def save_config(update: ConfigUpdate):
    _execute(
        TRADING_DB,
        "CREATE TABLE IF NOT EXISTS app_config (key TEXT PRIMARY KEY, value TEXT, description TEXT, updated_at TIMESTAMP)",
    )
    _execute(
        TRADING_DB,
        "INSERT OR REPLACE INTO app_config (key, value, updated_at) VALUES (?, ?, ?)",
        (update.key, update.value, datetime.now().isoformat()),
    )
    return {"ok": True, "key": update.key}


@app.post("/api/config/clear-trades")
def clear_trades():
    _execute(TRADING_DB, "DELETE FROM trades")
    return {"ok": True, "cleared": "trades"}


@app.post("/api/config/clear-logs")
def clear_logs():
    adb = _activity_db()
    _execute(adb, "DELETE FROM api_call_logs")
    _execute(adb, "DELETE FROM risk_reviews")
    _execute(adb, "DELETE FROM ai_decision_logs")
    _execute(adb, "DELETE FROM news_fingerprints")
    return {"ok": True, "cleared": "activity_logs"}


@app.post("/api/config/factory-reset")
def factory_reset():
    _execute(TRADING_DB, "DELETE FROM trades")
    _execute(TRADING_DB, "DELETE FROM signals")
    _execute(TRADING_DB, "DELETE FROM market_trends")
    adb = _activity_db()
    _execute(adb, "DELETE FROM api_call_logs")
    _execute(adb, "DELETE FROM risk_reviews")
    _execute(adb, "DELETE FROM ai_decision_logs")
    _execute(adb, "DELETE FROM news_fingerprints")
    return {"ok": True, "cleared": "all"}


@app.get("/api/chart/{symbol}")
def chart_data(symbol: str, days: int = Query(90)):
    """Fetch recent price history for a symbol and any recorded trades to plot execution."""
    import yfinance as yf
    try:
        # Fetch OHLC data
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=f"{days}d")
        
        prices = []
        if not df.empty:
            for index, row in df.iterrows():
                prices.append({
                    "date": index.strftime("%Y-%m-%d"),
                    "close": round(row['Close'], 2)
                })
                
        # Fetch execution trades for this symbol
        trades = _query(
            TRADING_DB,
            "SELECT timestamp, action, price, quantity FROM trades WHERE symbol = ? AND status IN ('placed','FILLED','filled','COMPLETED','completed') ORDER BY timestamp ASC",
            (symbol.upper(),)
        )
        
        return {
            "symbol": symbol.upper(),
            "prices": prices,
            "trades": trades
        }
    except Exception as e:
        return {"error": str(e)}


class AnalyzeRequest(BaseModel):
    symbol: str
    asset_type: str = "STOCK"
    option_strike: Optional[float] = None
    option_expiry: Optional[str] = None

@app.post("/api/analyze")
async def analyze_symbol_api(req: AnalyzeRequest):
    import asyncio
    from trader.market_data import MarketDataFetcher
    from strategy.news import NewsFetcher
    from strategy.technical import TechAnalyzer
    from strategy.ai import AIAnalyzer
    from strategy.earnings import get_earnings_info
    from strategy.correlations import get_cross_impact
    
    market_data = MarketDataFetcher()
    news_fetcher = NewsFetcher()
    tech_analyzer = TechAnalyzer()
    ai_analyzer = AIAnalyzer()
    
    symbol = req.symbol.upper()
    
    try:
        price_snapshot, history, options, specific_news = await asyncio.gather(
            market_data.get_current_price(symbol),
            market_data.get_history(symbol, period="1y"),
            market_data.get_option_chain(symbol),
            news_fetcher.get_news(f"{symbol} stock market news", dedup_symbol=symbol)
        )
        
        if not price_snapshot or history.empty:
            return JSONResponse(status_code=400, content={"error": "Insufficient market data for symbol."})
            
        tech = tech_analyzer.analyze(history)
        earnings = get_earnings_info(symbol)
        cross_impact = get_cross_impact(symbol)
        
        # If user explicitly provided an option, we inject it as a prioritized option visually for the AI
        if req.asset_type in ["CALL", "PUT"] and req.option_strike and req.option_expiry:
            tgt_opt = {
                "contractSymbol": f"USER_TARGET_{req.asset_type}",
                "strike": req.option_strike,
                "type": req.asset_type,
                "expiration": req.option_expiry,
                "lastPrice": 0.0,
                "impliedVolatility": 0.0
            }
            options.insert(0, tgt_opt)
            
        signal = await ai_analyzer.analyze(
            symbol=symbol,
            price=price_snapshot.price,
            tech=tech.__dict__ if tech else {},
            news=specific_news,
            options=options,
            earnings=earnings.__dict__ if earnings else None,
            cross_impact=cross_impact
        )
        # Extract bid/ask for the recommended option if possible
        rec_bid, rec_ask = 0.0, 0.0
        if signal.recommended_option and signal.recommended_option != "null" and isinstance(options, list):
            for opt in options:
                # Options can be dicts (if injected) or OptionData objects
                if isinstance(opt, dict):
                    continue # Injected options don't have real bid/ask
                if opt.strike == signal.option_strike and opt.expiry == signal.option_expiry:
                    rec_bid = opt.bid
                    rec_ask = opt.ask
                    break

        return {
            "ok": True,
            "current_price": price_snapshot.price,
            "decision": signal.decision,
            "confidence": signal.confidence,
            "reasoning": signal.reasoning,
            "recommended_option": signal.recommended_option,
            "option_strike": signal.option_strike,
            "option_expiry": signal.option_expiry,
            "option_bid": rec_bid,
            "option_ask": rec_ask,
            "target_buy_price": signal.target_buy_price,
            "target_sell_price": signal.target_sell_price,
            "stop_loss": signal.stop_loss_suggestion,
            "allocation_pct": getattr(signal, "allocation_pct", None)
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Static Files + SPA Fallback ──
if os.path.isdir(DASHBOARD_DIR):
    app.mount("/assets", StaticFiles(directory=DASHBOARD_DIR), name="static")

    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        file_path = os.path.join(DASHBOARD_DIR, path)
        if path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(DASHBOARD_DIR, "index.html"))
else:
    @app.get("/")
    def no_dashboard():
        return {"error": "dashboard/ directory not found. Create it with index.html."}


if __name__ == "__main__":
    import uvicorn
    print("🚀 QUANTUM Dashboard → http://localhost:8050")
    uvicorn.run(app, host="0.0.0.0", port=8050, log_level="info")
