"""
Stock Correlations & Cross-Impact Analysis

Maps relationships between stocks so the AI can factor in:
- Competitor earnings/news (MSFT results → affects GOOGL, META, AMZN)
- Supply chain impacts (NVDA guidance → affects AMD, cloud/AI companies)
- Sector contagion (banking crisis → all bank stocks)
- Political/regulatory events (antitrust vs Big Tech → all FAANG)
- Indian market cross-links (TCS results → affects INFY, WIPRO)

The correlation map is a combination of:
1. Hardcoded known relationships (well-established peer groups)
2. Dynamic sector detection via yfinance (for stocks not in the map)
"""

import yfinance as yf
import structlog
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from pydantic import BaseModel

logger = structlog.get_logger()


class StockRelation(BaseModel):
    """A related stock with the nature of its relationship."""
    symbol: str
    relationship: str  # "competitor", "supplier", "customer", "sector_peer", "index_component"
    impact_weight: float = 0.5  # 0.0-1.0 how strongly this stock's events affect the target


class CrossImpact(BaseModel):
    """Cross-impact context for a target stock, built from its correlated peers."""
    target_symbol: str
    related_earnings: list = []    # Peers with upcoming/recent earnings
    related_moves: list = []       # Peers with significant recent price moves
    related_news_context: str = "" # Summary of notable peer activity
    political_context: str = ""    # Relevant political/regulatory context


# ──────────────────────────────────────────────
# Known Correlation Map
# ──────────────────────────────────────────────
# This captures well-known, high-impact relationships that pure sector
# classification wouldn't fully capture (e.g., NVDA→cloud companies).

CORRELATION_MAP: Dict[str, List[StockRelation]] = {
    # ── US Big Tech / "Magnificent 7" ──
    "AAPL": [
        StockRelation(symbol="MSFT", relationship="competitor", impact_weight=0.6),
        StockRelation(symbol="GOOGL", relationship="competitor", impact_weight=0.5),
        StockRelation(symbol="AMZN", relationship="competitor", impact_weight=0.4),
        StockRelation(symbol="META", relationship="sector_peer", impact_weight=0.4),
        StockRelation(symbol="QCOM", relationship="supplier", impact_weight=0.5),
        StockRelation(symbol="TSM", relationship="supplier", impact_weight=0.6),
    ],
    "MSFT": [
        StockRelation(symbol="GOOGL", relationship="competitor", impact_weight=0.7),
        StockRelation(symbol="AMZN", relationship="competitor", impact_weight=0.6),  # AWS vs Azure
        StockRelation(symbol="META", relationship="sector_peer", impact_weight=0.5),
        StockRelation(symbol="AAPL", relationship="competitor", impact_weight=0.5),
        StockRelation(symbol="CRM", relationship="competitor", impact_weight=0.5),
        StockRelation(symbol="NVDA", relationship="supplier", impact_weight=0.5),
    ],
    "GOOGL": [
        StockRelation(symbol="META", relationship="competitor", impact_weight=0.7),  # Ad revenue
        StockRelation(symbol="MSFT", relationship="competitor", impact_weight=0.6),
        StockRelation(symbol="AMZN", relationship="competitor", impact_weight=0.5),
        StockRelation(symbol="SNAP", relationship="competitor", impact_weight=0.4),
        StockRelation(symbol="NVDA", relationship="supplier", impact_weight=0.5),
    ],
    "AMZN": [
        StockRelation(symbol="MSFT", relationship="competitor", impact_weight=0.6),  # AWS vs Azure
        StockRelation(symbol="GOOGL", relationship="competitor", impact_weight=0.5),  # Cloud
        StockRelation(symbol="WMT", relationship="competitor", impact_weight=0.5),  # Retail
        StockRelation(symbol="SHOP", relationship="sector_peer", impact_weight=0.4),
    ],
    "META": [
        StockRelation(symbol="GOOGL", relationship="competitor", impact_weight=0.7),  # Ad revenue
        StockRelation(symbol="SNAP", relationship="competitor", impact_weight=0.6),
        StockRelation(symbol="PINS", relationship="competitor", impact_weight=0.4),
        StockRelation(symbol="MSFT", relationship="sector_peer", impact_weight=0.4),
        StockRelation(symbol="NVDA", relationship="supplier", impact_weight=0.5),  # AI hardware
    ],
    "NVDA": [
        StockRelation(symbol="AMD", relationship="competitor", impact_weight=0.8),
        StockRelation(symbol="INTC", relationship="competitor", impact_weight=0.5),
        StockRelation(symbol="TSM", relationship="supplier", impact_weight=0.7),  # Fab
        StockRelation(symbol="MSFT", relationship="customer", impact_weight=0.6),  # AI infra
        StockRelation(symbol="GOOGL", relationship="customer", impact_weight=0.5),
        StockRelation(symbol="META", relationship="customer", impact_weight=0.5),
        StockRelation(symbol="AMZN", relationship="customer", impact_weight=0.5),
        StockRelation(symbol="AVGO", relationship="competitor", impact_weight=0.5),
    ],
    "TSLA": [
        StockRelation(symbol="RIVN", relationship="competitor", impact_weight=0.5),
        StockRelation(symbol="F", relationship="competitor", impact_weight=0.4),
        StockRelation(symbol="GM", relationship="competitor", impact_weight=0.4),
        StockRelation(symbol="NIO", relationship="competitor", impact_weight=0.4),
        StockRelation(symbol="NVDA", relationship="supplier", impact_weight=0.4),  # Self-driving chips
    ],
    "AMD": [
        StockRelation(symbol="NVDA", relationship="competitor", impact_weight=0.8),
        StockRelation(symbol="INTC", relationship="competitor", impact_weight=0.7),
        StockRelation(symbol="TSM", relationship="supplier", impact_weight=0.6),
        StockRelation(symbol="AVGO", relationship="sector_peer", impact_weight=0.4),
    ],

    # ── US ETFs ──
    "SPY": [
        StockRelation(symbol="QQQ", relationship="sector_peer", impact_weight=0.8),
        StockRelation(symbol="DIA", relationship="sector_peer", impact_weight=0.7),
        StockRelation(symbol="IWM", relationship="sector_peer", impact_weight=0.6),
    ],
    "QQQ": [
        StockRelation(symbol="SPY", relationship="sector_peer", impact_weight=0.7),
        StockRelation(symbol="AAPL", relationship="index_component", impact_weight=0.6),
        StockRelation(symbol="MSFT", relationship="index_component", impact_weight=0.6),
        StockRelation(symbol="NVDA", relationship="index_component", impact_weight=0.6),
    ],

    # ── Indian IT Sector ──
    "RELIANCE.NS": [
        StockRelation(symbol="TCS.NS", relationship="sector_peer", impact_weight=0.3),
        StockRelation(symbol="HDFCBANK.NS", relationship="sector_peer", impact_weight=0.4),
        StockRelation(symbol="ITC.NS", relationship="sector_peer", impact_weight=0.3),
    ],
    "TCS.NS": [
        StockRelation(symbol="INFY.NS", relationship="competitor", impact_weight=0.8),
        StockRelation(symbol="WIPRO.NS", relationship="competitor", impact_weight=0.6),
        StockRelation(symbol="HCLTECH.NS", relationship="competitor", impact_weight=0.6),
        StockRelation(symbol="TECHM.NS", relationship="competitor", impact_weight=0.5),
    ],
    "INFY.NS": [
        StockRelation(symbol="TCS.NS", relationship="competitor", impact_weight=0.8),
        StockRelation(symbol="WIPRO.NS", relationship="competitor", impact_weight=0.6),
        StockRelation(symbol="HCLTECH.NS", relationship="competitor", impact_weight=0.6),
        StockRelation(symbol="TECHM.NS", relationship="competitor", impact_weight=0.5),
    ],
    "HDFCBANK.NS": [
        StockRelation(symbol="ICICIBANK.NS", relationship="competitor", impact_weight=0.7),
        StockRelation(symbol="SBIN.NS", relationship="competitor", impact_weight=0.6),
        StockRelation(symbol="KOTAKBANK.NS", relationship="competitor", impact_weight=0.6),
        StockRelation(symbol="AXISBANK.NS", relationship="competitor", impact_weight=0.5),
    ],
    "TATASTEEL.NS": [
        StockRelation(symbol="JSWSTEEL.NS", relationship="competitor", impact_weight=0.7),
        StockRelation(symbol="SAIL.NS", relationship="competitor", impact_weight=0.6),
        StockRelation(symbol="HINDALCO.NS", relationship="sector_peer", impact_weight=0.5),
    ],
}


# ──────────────────────────────────────────────
# Macro / Geopolitical Sensitivity Map
# ──────────────────────────────────────────────
# Tags stocks with macro themes they're sensitive to.
# When any of these themes appear in news, the AI should
# weigh that information more heavily for these stocks.
#
# This captures things like:
#   - Tariffs → steel, manufacturing, imports
#   - AI regulation/product launches → all AI companies
#   - Interest rates → banks, real estate, growth stocks
#   - Oil prices → energy, transportation, airlines
#   - Currency (USD/INR) → Indian IT (revenue in USD)

MACRO_SENSITIVITIES: Dict[str, List[str]] = {
    # ── US Tech — AI & regulation ──
    "AAPL":  ["tariffs_china", "antitrust_big_tech", "consumer_spending", "usd_strength"],
    "MSFT":  ["ai_industry", "antitrust_big_tech", "cloud_spending", "enterprise_it_budgets"],
    "GOOGL": ["ai_industry", "antitrust_big_tech", "digital_ad_spending", "ai_regulation"],
    "AMZN":  ["tariffs_china", "consumer_spending", "cloud_spending", "labor_regulation"],
    "META":  ["ai_industry", "digital_ad_spending", "ai_regulation", "antitrust_big_tech"],
    "NVDA":  ["ai_industry", "tariffs_china", "chip_export_controls", "data_center_spending"],
    "AMD":   ["ai_industry", "tariffs_china", "chip_export_controls", "data_center_spending"],
    "TSLA":  ["ev_policy", "tariffs_china", "interest_rates", "autonomous_driving_regulation"],
    "INTC":  ["chip_export_controls", "us_chips_act", "tariffs_china"],
    "TSM":   ["chip_export_controls", "taiwan_geopolitics", "tariffs_china"],

    # ── US ETFs & Indices ──
    "SPY":   ["interest_rates", "fed_policy", "recession_risk", "geopolitics"],
    "QQQ":   ["interest_rates", "ai_industry", "antitrust_big_tech"],

    # ── India — IT Services ──
    "TCS.NS":       ["us_visa_h1b", "usd_inr_currency", "enterprise_it_budgets", "us_recession_risk"],
    "INFY.NS":      ["us_visa_h1b", "usd_inr_currency", "enterprise_it_budgets", "us_recession_risk"],
    "WIPRO.NS":     ["us_visa_h1b", "usd_inr_currency", "enterprise_it_budgets"],
    "HCLTECH.NS":   ["us_visa_h1b", "usd_inr_currency", "enterprise_it_budgets"],
    "TECHM.NS":     ["us_visa_h1b", "usd_inr_currency", "enterprise_it_budgets"],

    # ── India — Banks ──
    "HDFCBANK.NS":  ["rbi_interest_rates", "india_gdp", "india_inflation", "npa_asset_quality"],
    "ICICIBANK.NS": ["rbi_interest_rates", "india_gdp", "india_inflation", "npa_asset_quality"],
    "SBIN.NS":      ["rbi_interest_rates", "india_gdp", "india_government_policy", "npa_asset_quality"],
    "KOTAKBANK.NS": ["rbi_interest_rates", "india_gdp", "india_inflation"],
    "AXISBANK.NS":  ["rbi_interest_rates", "india_gdp", "india_inflation"],

    # ── India — Conglomerates & Commodities ──
    "RELIANCE.NS":  ["oil_prices", "india_telecom_policy", "india_retail", "india_gdp"],
    "TATASTEEL.NS": ["tariffs_steel", "china_steel_dumping", "india_infrastructure_spending"],
    "JSWSTEEL.NS":  ["tariffs_steel", "china_steel_dumping", "india_infrastructure_spending"],
    "HINDALCO.NS":  ["tariffs_aluminum", "china_commodity_prices", "india_infrastructure_spending"],
    "ITC.NS":       ["india_tobacco_regulation", "india_fmcg", "india_gst_policy"],
}

# Human-readable labels for macro themes (used in AI prompt)
MACRO_THEME_LABELS: Dict[str, str] = {
    "tariffs_china":               "US-China tariffs and trade war",
    "tariffs_steel":               "Steel import tariffs / anti-dumping duties",
    "tariffs_aluminum":            "Aluminum tariffs and commodity trade policy",
    "antitrust_big_tech":          "Big Tech antitrust regulation and lawsuits",
    "ai_industry":                 "AI industry developments (new models, tools, partnerships)",
    "ai_regulation":               "AI regulation and safety legislation",
    "chip_export_controls":        "Semiconductor export controls (US-China)",
    "us_chips_act":                "US CHIPS Act funding and domestic semiconductor policy",
    "taiwan_geopolitics":          "Taiwan geopolitical tensions",
    "interest_rates":              "Federal Reserve interest rate decisions",
    "fed_policy":                  "Federal Reserve monetary policy and guidance",
    "rbi_interest_rates":          "RBI interest rate decisions",
    "consumer_spending":           "US consumer spending and retail data",
    "digital_ad_spending":         "Digital advertising market trends",
    "cloud_spending":              "Cloud infrastructure and enterprise spending",
    "data_center_spending":        "Data center and AI infrastructure capex",
    "enterprise_it_budgets":       "Enterprise IT spending and outsourcing trends",
    "ev_policy":                   "EV subsidies, regulation, and adoption trends",
    "autonomous_driving_regulation": "Self-driving car regulation and approvals",
    "usd_strength":                "US dollar strength and forex impact",
    "usd_inr_currency":            "USD/INR exchange rate movements",
    "us_visa_h1b":                 "US H-1B visa policy changes (affects Indian IT outsourcing)",
    "us_recession_risk":           "US economic slowdown / recession indicators",
    "recession_risk":              "Global recession risk indicators",
    "geopolitics":                 "Major geopolitical events (wars, sanctions, elections)",
    "oil_prices":                  "Crude oil price movements",
    "china_steel_dumping":         "Chinese steel overproduction and dumping",
    "china_commodity_prices":      "Chinese commodity demand and pricing",
    "india_gdp":                   "India GDP growth and economic data",
    "india_inflation":             "India CPI/WPI inflation data",
    "india_government_policy":     "Indian government fiscal/policy decisions",
    "india_infrastructure_spending": "India infrastructure and capex spending",
    "india_telecom_policy":        "India telecom spectrum and regulation",
    "india_retail":                "India retail and e-commerce market",
    "india_tobacco_regulation":    "India tobacco taxation and regulation",
    "india_fmcg":                  "India FMCG and consumer staples market",
    "india_gst_policy":            "India GST rate changes",
    "npa_asset_quality":           "Bank NPA and asset quality concerns",
    "labor_regulation":            "Labor and employment regulation changes",
}


# ──────────────────────────────────────────────
# Dynamic sector detection (fallback)
# ──────────────────────────────────────────────
_sector_cache: Dict[str, dict] = {}
_sector_cache_expiry: Dict[str, datetime] = {}
SECTOR_CACHE_TTL_HOURS = 24


def _get_stock_sector(symbol: str) -> Optional[dict]:
    """Get sector/industry info from yfinance, cached for 24h."""
    now = datetime.now()
    if symbol in _sector_cache and now < _sector_cache_expiry.get(symbol, now):
        return _sector_cache[symbol]
    
    try:
        ticker = yf.Ticker(symbol)
        # yfinance info property can trigger API calls that may fail
        try:
            info = ticker.info
        except Exception:
            # Fallback or specific error handling (e.g. 404 Not Found)
            info = None
            
        if not info:
            logger.debug("sector_fetch_empty", symbol=symbol)
            return None

        result = {
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "market_cap": info.get("marketCap"),
        }
        _sector_cache[symbol] = result
        _sector_cache_expiry[symbol] = now + timedelta(hours=SECTOR_CACHE_TTL_HOURS)
        return result
    except Exception as e:
        logger.debug("sector_fetch_error", symbol=symbol, error=str(e))
        return None


def get_related_stocks(symbol: str) -> List[StockRelation]:
    """
    Returns the list of stocks correlated to the given symbol.
    
    1. Checks the hardcoded CORRELATION_MAP first (most reliable)
    2. Reverse lookup — if SNAP is in META's map, META is related to SNAP
    3. Dynamic discovery — uses yfinance sector/industry to find peers
       from the watchlist and known stocks
    """
    # 1. Hardcoded map (captures nuanced supplier/customer/competitor relationships)
    if symbol in CORRELATION_MAP:
        return CORRELATION_MAP[symbol]
    
    # 2. Reverse lookup
    reverse_relations = []
    for parent_symbol, relations in CORRELATION_MAP.items():
        for rel in relations:
            if rel.symbol == symbol:
                reverse_relations.append(StockRelation(
                    symbol=parent_symbol,
                    relationship=_reverse_relationship(rel.relationship),
                    impact_weight=rel.impact_weight * 0.8,
                ))
    if reverse_relations:
        return reverse_relations
    
    # 3. Dynamic sector/industry-based peer discovery via yfinance
    dynamic_peers = _discover_sector_peers(symbol)
    if dynamic_peers:
        return dynamic_peers
    
    logger.debug("no_peer_correlations", symbol=symbol)
    return []


# Cache for dynamically discovered peers
_dynamic_peer_cache: Dict[str, List[StockRelation]] = {}
_dynamic_peer_cache_expiry: Dict[str, datetime] = {}


def _discover_sector_peers(symbol: str) -> List[StockRelation]:
    """
    Dynamically find peer stocks by matching sector and industry via yfinance.
    Searches against all known stocks (CORRELATION_MAP keys + user watchlist).
    Results are cached for 24 hours.
    """
    now = datetime.now()
    if symbol in _dynamic_peer_cache and now < _dynamic_peer_cache_expiry.get(symbol, now):
        return _dynamic_peer_cache[symbol]
    
    target_info = _get_stock_sector(symbol)
    if not target_info or not target_info.get("sector"):
        return []
    
    target_sector = target_info["sector"]
    target_industry = target_info.get("industry")
    
    # Build candidate pool: all known symbols from the correlation map + watchlist
    candidates: Set[str] = set()
    candidates.update(CORRELATION_MAP.keys())
    for relations in CORRELATION_MAP.values():
        for rel in relations:
            candidates.add(rel.symbol)
    
    # Also add watchlist symbols if available
    try:
        from agent_config import settings
        if hasattr(settings, 'all_tickers'):
            candidates.update(settings.all_tickers)
    except Exception:
        pass
    
    candidates.discard(symbol)  # Don't compare to self
    
    peers = []
    for candidate in candidates:
        try:
            candidate_info = _get_stock_sector(candidate)
            if not candidate_info or not candidate_info.get("sector"):
                continue
            
            if candidate_info["sector"] == target_sector:
                # Same industry = stronger relationship
                if target_industry and candidate_info.get("industry") == target_industry:
                    peers.append(StockRelation(
                        symbol=candidate,
                        relationship="competitor",
                        impact_weight=0.6,
                    ))
                else:
                    # Same sector, different industry = weaker
                    peers.append(StockRelation(
                        symbol=candidate,
                        relationship="sector_peer",
                        impact_weight=0.3,
                    ))
        except Exception:
            continue
    
    # Sort by impact weight, limit to top 6 peers
    peers.sort(key=lambda x: x.impact_weight, reverse=True)
    peers = peers[:6]
    
    if peers:
        logger.info("dynamic_peers_discovered", symbol=symbol,
                    sector=target_sector, industry=target_industry,
                    peer_count=len(peers),
                    peers=[p.symbol for p in peers])
    
    # Cache result
    _dynamic_peer_cache[symbol] = peers
    _dynamic_peer_cache_expiry[symbol] = now + timedelta(hours=SECTOR_CACHE_TTL_HOURS)
    
    return peers


def _reverse_relationship(rel: str) -> str:
    """Reverses a relationship direction."""
    reverse_map = {
        "supplier": "customer",
        "customer": "supplier",
        "competitor": "competitor",
        "sector_peer": "sector_peer",
        "index_component": "index_component",
    }
    return reverse_map.get(rel, rel)


def get_macro_sensitivities(symbol: str) -> List[str]:
    """
    Returns human-readable macro themes this stock is sensitive to.
    E.g., for NVDA → ["AI industry developments", "US-China tariffs", ...]
    """
    themes = MACRO_SENSITIVITIES.get(symbol, [])
    return [MACRO_THEME_LABELS.get(t, t) for t in themes]


# ──────────────────────────────────────────────
# Cross-Impact Analysis
# ──────────────────────────────────────────────

def get_cross_impact(symbol: str, watchlist: List[str] = None) -> CrossImpact:
    """
    Builds cross-impact context for a stock by checking:
    1. Correlated peers for earnings and significant price moves
    2. Macro/geopolitical themes this stock is sensitive to
    
    This context is injected into the AI analysis prompt.
    """
    from strategy.earnings import get_earnings_info
    
    impact = CrossImpact(target_symbol=symbol)
    context_parts = []
    
    # ── Part 1: Peer stock impacts ──
    related = get_related_stocks(symbol)
    earnings_alerts = []
    price_moves = []
    
    for rel in related:
        # 1a. Check peer earnings
        try:
            peer_earnings = get_earnings_info(rel.symbol)
            if peer_earnings.earnings_date and peer_earnings.days_until_earnings is not None:
                if -3 <= peer_earnings.days_until_earnings <= 14:
                    # Peer has earnings upcoming (within 14 days) or just reported (within 3 days)
                    timing = "just reported" if peer_earnings.days_until_earnings < 0 else f"in {peer_earnings.days_until_earnings} days"
                    earnings_alerts.append({
                        "peer": rel.symbol,
                        "relationship": rel.relationship,
                        "earnings_date": peer_earnings.earnings_date,
                        "timing": timing,
                        "eps_estimate": peer_earnings.eps_estimate,
                        "impact_weight": rel.impact_weight,
                    })
        except Exception:
            pass
        
        # 1b. Check peer price moves (last 5 days)
        try:
            peer_ticker = yf.Ticker(rel.symbol)
            hist = peer_ticker.history(period="5d")
            if not hist.empty and len(hist) >= 2:
                latest_close = hist['Close'].iloc[-1]
                prev_close = hist['Close'].iloc[-2]
                pct_change = ((latest_close - prev_close) / prev_close) * 100
                
                # Only flag significant moves (> 3%)
                if abs(pct_change) > 3.0:
                    direction = "up" if pct_change > 0 else "down"
                    price_moves.append({
                        "peer": rel.symbol,
                        "relationship": rel.relationship,
                        "change_pct": round(pct_change, 2),
                        "direction": direction,
                        "impact_weight": rel.impact_weight,
                    })
        except Exception:
            pass
    
    impact.related_earnings = earnings_alerts
    impact.related_moves = price_moves
    
    # Format peer impacts for the AI
    if earnings_alerts:
        context_parts.append("Peer Earnings Activity:")
        for ea in sorted(earnings_alerts, key=lambda x: x["impact_weight"], reverse=True):
            context_parts.append(
                f"  - {ea['peer']} ({ea['relationship']}) has earnings {ea['timing']} "
                f"(EPS est: {ea.get('eps_estimate', 'N/A')})"
            )
    
    if price_moves:
        context_parts.append("Significant Peer Price Moves:")
        for pm in sorted(price_moves, key=lambda x: abs(x["change_pct"]), reverse=True):
            context_parts.append(
                f"  - {pm['peer']} ({pm['relationship']}) moved {pm['change_pct']:+.1f}% "
                f"({pm['direction']}) in last session"
            )
    
    # ── Part 2: Macro / geopolitical sensitivities ──
    macro_themes = get_macro_sensitivities(symbol)
    if macro_themes:
        context_parts.append("Macro/Political Sensitivities (scan news for these):")
        for theme in macro_themes:
            context_parts.append(f"  - {theme}")
        impact.political_context = "; ".join(macro_themes)
    
    # Combine everything
    if context_parts:
        impact.related_news_context = "\n".join(context_parts)
    
    logger.info("cross_impact_analyzed", symbol=symbol,
               peer_count=len(related),
               earnings_alerts=len(earnings_alerts),
               price_moves=len(price_moves),
               macro_themes=len(macro_themes))
    
    return impact
