import asyncio
import hashlib
from GoogleNews import GoogleNews
from typing import List, Dict, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
import structlog
from concurrent.futures import ThreadPoolExecutor

logger = structlog.get_logger()

class NewsItem(BaseModel):
    title: str
    link: str
    date: str
    source: str
    sentiment: str = "neutral"
    fingerprint: str = ""  # SHA-256 hash for dedup

    def compute_fingerprint(self, symbol: str) -> str:
        """Deterministic hash of symbol + headline for dedup."""
        raw = f"{symbol.upper()}:{self.title.strip().lower()}"
        self.fingerprint = hashlib.sha256(raw.encode()).hexdigest()
        return self.fingerprint


# ─── Keyword-based sentiment scoring ────────────
_BULLISH_KEYWORDS = {
    "beat", "beats", "surge", "surges", "upgrade", "upgrades", "rally",
    "record", "growth", "profit", "strong", "bullish", "buy", "raises",
    "outperform", "buyback", "acquisition", "positive", "soars",
    "dividend", "approve", "deal", "expands", "win", "wins", "boost",
}
_BEARISH_KEYWORDS = {
    "miss", "misses", "crash", "plunge", "downgrade", "downgrades",
    "fall", "falls", "loss", "losses", "weak", "bearish", "sell",
    "layoff", "layoffs", "recall", "fine", "fines", "fraud",
    "investigation", "sec", "lawsuit", "decline", "warning", "debt",
    "bankruptcy", "default", "tariff", "sanction",
}

def score_sentiment(title: str) -> str:
    """Simple keyword-based sentiment: bullish / bearish / neutral."""
    lower = title.lower()
    bull = sum(1 for kw in _BULLISH_KEYWORDS if kw in lower)
    bear = sum(1 for kw in _BEARISH_KEYWORDS if kw in lower)
    if bull > bear:
        return "bullish"
    elif bear > bull:
        return "bearish"
    return "neutral"


class NewsFetcher:
    def __init__(self, lang='en', region='US'):
        self.googlenews = GoogleNews(lang=lang, region=region)
        self._executor = ThreadPoolExecutor(max_workers=3)
        self._cache: Dict[str, Dict] = {}
        self._cache_ttl_seconds = 600  # 10 minutes
        self._cache_lock = asyncio.Lock()
        # In-memory set of fingerprints seen THIS session (fast path)
        self._seen_fingerprints: set = set()

    async def get_news(self, query: str, period: str = '1d',
                       dedup_symbol: Optional[str] = None) -> List[NewsItem]:
        """Fetches news for a query. Optionally dedup against seen headlines.
        
        Args:
            query: Search query (e.g., 'AAPL stock' or 'Geopolitics')
            period: Time period ('1d', '7d', etc.)
            dedup_symbol: If set, compute fingerprints and filter out already-seen news
        """
        try:
            # Check Cache
            now = datetime.now()
            async with self._cache_lock:
                if query in self._cache:
                    last_fetched = self._cache[query]['timestamp']
                    if (now - last_fetched).total_seconds() < self._cache_ttl_seconds:
                        logger.debug("news_cache_hit", query=query)
                        cached = self._cache[query]['data']
                        if dedup_symbol:
                            return self._filter_seen(cached, dedup_symbol)
                        return cached

            loop = asyncio.get_running_loop()
            
            def fetch():
                self.googlenews.clear()
                self.googlenews.set_period(period)
                self.googlenews.search(query)
                return self.googlenews.result()

            results = await loop.run_in_executor(self._executor, fetch)
            
            news_items = []
            for item in results:
                n = NewsItem(
                    title=item.get('title', ''),
                    link=item.get('link', ''),
                    date=item.get('date', ''),
                    source=item.get('media', ''),
                    sentiment=score_sentiment(item.get('title', '')),
                )
                news_items.append(n)
            
            # Update Cache
            final_items = news_items[:10]
            async with self._cache_lock:
                self._cache[query] = {
                    'timestamp': now,
                    'data': final_items
                }
            logger.info("news_fetched_fresh", query=query, count=len(final_items))
            
            # Dedup: filter out headlines we already acted on
            if dedup_symbol:
                return self._filter_seen(final_items, dedup_symbol)
            return final_items

        except Exception as e:
            logger.error("fetch_news_error", query=query, error=str(e))
            return []

    def _filter_seen(self, items: List[NewsItem], symbol: str) -> List[NewsItem]:
        """Filter out news items whose fingerprint we've already seen."""
        fresh = []
        for item in items:
            fp = item.compute_fingerprint(symbol)
            if fp not in self._seen_fingerprints:
                fresh.append(item)
        return fresh

    def mark_news_seen(self, items: List[NewsItem], symbol: str):
        """Mark news items as processed so we don't re-act on them."""
        for item in items:
            fp = item.compute_fingerprint(symbol)
            self._seen_fingerprints.add(fp)

    def get_new_count(self, items: List[NewsItem], symbol: str) -> int:
        """Returns how many items in the list are genuinely new."""
        count = 0
        for item in items:
            fp = item.compute_fingerprint(symbol)
            if fp not in self._seen_fingerprints:
                count += 1
        return count
