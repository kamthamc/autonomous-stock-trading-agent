from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from typing import List, Optional
import structlog

from .models import Trade, Signal, MarketTrend

logger = structlog.get_logger()

DATABASE_URL = "sqlite+aiosqlite:///trading_agent.db"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        # await conn.run_sync(SQLModel.metadata.drop_all) # Uncomment to reset
        await conn.run_sync(SQLModel.metadata.create_all)

async def save_signal(signal: Signal):
    async with async_session() as session:
        session.add(signal)
        await session.commit()
        await session.refresh(signal)
        return signal

async def save_trade(trade: Trade):
    async with async_session() as session:
        session.add(trade)
        await session.commit()
        await session.refresh(trade)
        return trade

async def get_recent_signals(limit: int = 50) -> List[Signal]:
    async with async_session() as session:
        statement = select(Signal).order_by(Signal.timestamp.desc()).limit(limit)
        results = await session.execute(statement)
        return results.scalars().all()

async def get_recent_trades(limit: int = 50) -> List[Trade]:
    async with async_session() as session:
        statement = select(Trade).order_by(Trade.timestamp.desc()).limit(limit)
        results = await session.execute(statement)
        return results.scalars().all()

from .models import MarketTrend

async def save_market_trend(trend: MarketTrend):
    async with async_session() as session:
        session.add(trend)
        await session.commit()
        await session.refresh(trend)
        return trend

async def get_latest_market_trend() -> Optional[MarketTrend]:
    async with async_session() as session:
        statement = select(MarketTrend).order_by(MarketTrend.timestamp.desc()).limit(1)
        results = await session.execute(statement)
        return results.scalars().first()
