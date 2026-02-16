"""
Database layer — split into two databases:

1. trading_agent.db  — Core business data (signals, trades, market trends)
   Single file, low volume, critical for business logic and dashboard.

2. activity_YYYY_MM.db  — Operational data (risk reviews, agent events)
   Month-based rotation. Each month gets its own file to keep size manageable.
   e.g. activity_2026_02.db, activity_2026_03.db, ...
"""

from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from typing import List, Optional
from datetime import datetime
import structlog

from .models import Trade, Signal, MarketTrend, RiskReview, AgentEvent, APICallLog

logger = structlog.get_logger()

# ──────────────────────────────────────────────
# Trading DB  (single file, low-volume)
# ──────────────────────────────────────────────
TRADING_DB_URL = "sqlite+aiosqlite:///trading_agent.db"
trading_engine = create_async_engine(TRADING_DB_URL, echo=False)
trading_session = sessionmaker(trading_engine, class_=AsyncSession, expire_on_commit=False)

# ──────────────────────────────────────────────
# Activity DB  (monthly rotation, high-volume)
# ──────────────────────────────────────────────
_ACTIVITY_TABLES = {"risk_reviews", "agent_events", "api_call_logs"}

# Cache: we keep one engine+session per month string to avoid re-creating them
_activity_engines: dict = {}
_activity_sessions: dict = {}


def _get_activity_month_key() -> str:
    """Returns the current month key, e.g. '2026_02'."""
    return datetime.now().strftime("%Y_%m")


def _get_activity_session() -> sessionmaker:
    """
    Returns the async session factory for the current month's activity DB.
    Creates the engine on first access for a new month.
    """
    month_key = _get_activity_month_key()

    if month_key not in _activity_sessions:
        db_url = f"sqlite+aiosqlite:///activity_{month_key}.db"
        engine = create_async_engine(db_url, echo=False)
        _activity_engines[month_key] = engine
        _activity_sessions[month_key] = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        logger.info("activity_db_created", month=month_key, path=f"activity_{month_key}.db")

    return _activity_sessions[month_key]


async def _ensure_activity_tables():
    """Creates activity tables in the current month's DB if they don't exist yet."""
    month_key = _get_activity_month_key()
    engine = _activity_engines.get(month_key)
    if engine is None:
        _get_activity_session()  # This creates the engine
        engine = _activity_engines[month_key]

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: SQLModel.metadata.create_all(
                sync_conn,
                tables=[t for t in SQLModel.metadata.sorted_tables if t.name in _ACTIVITY_TABLES]
            )
        )


# ──────────────────────────────────────────────
# Initialization
# ──────────────────────────────────────────────

_TRADING_TABLES = {"signals", "trades", "market_trends"}


async def init_db():
    """Initialize both databases, creating tables as needed."""
    # Trading DB
    async with trading_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: SQLModel.metadata.create_all(
                sync_conn,
                tables=[t for t in SQLModel.metadata.sorted_tables if t.name in _TRADING_TABLES]
            )
        )

    # Activity DB (current month)
    await _ensure_activity_tables()

    logger.info("databases_initialized",
                trading="trading_agent.db",
                activity=f"activity_{_get_activity_month_key()}.db")


# ──────────────────────────────────────────────
# Trading DB Operations
# ──────────────────────────────────────────────

async def save_signal(signal: Signal) -> Signal:
    async with trading_session() as session:
        session.add(signal)
        await session.commit()
        await session.refresh(signal)
        return signal


async def save_trade(trade: Trade) -> Trade:
    async with trading_session() as session:
        session.add(trade)
        await session.commit()
        await session.refresh(trade)
        return trade


async def get_recent_signals(limit: int = 50) -> List[Signal]:
    async with trading_session() as session:
        statement = select(Signal).order_by(Signal.timestamp.desc()).limit(limit)
        results = await session.execute(statement)
        return results.scalars().all()


async def get_recent_trades(limit: int = 50) -> List[Trade]:
    async with trading_session() as session:
        statement = select(Trade).order_by(Trade.timestamp.desc()).limit(limit)
        results = await session.execute(statement)
        return results.scalars().all()


async def save_market_trend(trend: MarketTrend) -> MarketTrend:
    async with trading_session() as session:
        session.add(trend)
        await session.commit()
        await session.refresh(trend)
        return trend


async def get_latest_market_trend() -> Optional[MarketTrend]:
    async with trading_session() as session:
        statement = select(MarketTrend).order_by(MarketTrend.timestamp.desc()).limit(1)
        results = await session.execute(statement)
        return results.scalars().first()


# ──────────────────────────────────────────────
# Activity DB Operations  (auto-routes to current month)
# ──────────────────────────────────────────────

async def save_risk_review(review: RiskReview) -> RiskReview:
    await _ensure_activity_tables()
    session_factory = _get_activity_session()
    async with session_factory() as session:
        session.add(review)
        await session.commit()
        await session.refresh(review)
        return review


async def get_recent_risk_reviews(limit: int = 50, symbol: Optional[str] = None) -> List[RiskReview]:
    """Reads from the current month's activity DB."""
    await _ensure_activity_tables()
    session_factory = _get_activity_session()
    async with session_factory() as session:
        statement = select(RiskReview).order_by(RiskReview.timestamp.desc())
        if symbol:
            statement = statement.where(RiskReview.symbol == symbol)
        statement = statement.limit(limit)
        results = await session.execute(statement)
        return results.scalars().all()


async def save_agent_event(event: AgentEvent) -> AgentEvent:
    await _ensure_activity_tables()
    session_factory = _get_activity_session()
    async with session_factory() as session:
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event


async def get_recent_agent_events(limit: int = 100, event_type: Optional[str] = None) -> List[AgentEvent]:
    """Reads from the current month's activity DB."""
    await _ensure_activity_tables()
    session_factory = _get_activity_session()
    async with session_factory() as session:
        statement = select(AgentEvent).order_by(AgentEvent.timestamp.desc())
        if event_type:
            statement = statement.where(AgentEvent.event_type == event_type)
        statement = statement.limit(limit)
        results = await session.execute(statement)
        return results.scalars().all()


def get_activity_db_path(month_key: Optional[str] = None) -> str:
    """Returns the file path for a given month's activity DB. Useful for dashboard."""
    key = month_key or _get_activity_month_key()
    return f"activity_{key}.db"


async def save_api_call_log(log: APICallLog) -> APICallLog:
    await _ensure_activity_tables()
    session_factory = _get_activity_session()
    async with session_factory() as session:
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log


async def get_api_call_stats(
    limit: int = 200,
    source: Optional[str] = None,
    provider: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> List[APICallLog]:
    """Query API call logs with optional filters for dashboard."""
    await _ensure_activity_tables()
    session_factory = _get_activity_session()
    async with session_factory() as session:
        statement = select(APICallLog).order_by(APICallLog.timestamp.desc())
        if source:
            statement = statement.where(APICallLog.source == source)
        if provider:
            statement = statement.where(APICallLog.provider == provider)
        if since:
            statement = statement.where(APICallLog.timestamp >= since)
        if until:
            statement = statement.where(APICallLog.timestamp <= until)
        statement = statement.limit(limit)
        results = await session.execute(statement)
        return results.scalars().all()
