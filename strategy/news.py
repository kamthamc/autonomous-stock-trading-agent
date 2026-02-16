import asyncio
from GoogleNews import GoogleNews
from typing import List, Dict
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
    sentiment: str = "neutral" # Placeholder for future sentiment analysis

class NewsFetcher:
    def __init__(self, lang='en', region='US'):
        self.googlenews = GoogleNews(lang=lang, region=region)
        self._executor = ThreadPoolExecutor(max_workers=3)
        self._cache: Dict[str, Dict] = {} # {query: {'timestamp': datetime, 'data': List[NewsItem]}}
        self._cache_ttl_seconds = 600 # 10 minutes

    async def get_news(self, query: str, period: str = '1d') -> List[NewsItem]:
        """Fetches news for a given query (e.g., 'AAPL stock' or 'Geopolitics')."""
        try:
            # Check Cache
            now = datetime.now()
            if query in self._cache:
                last_fetched = self._cache[query]['timestamp']
                if (now - last_fetched).total_seconds() < self._cache_ttl_seconds:
                    logger.debug("news_cache_hit", query=query)
                    return self._cache[query]['data']

            loop = asyncio.get_running_loop()
            
            def fetch():
                self.googlenews.clear()
                self.googlenews.set_period(period)
                self.googlenews.search(query)
                return self.googlenews.result()

            results = await loop.run_in_executor(self._executor, fetch)
            
            news_items = []
            for item in results:
                # Basic parsing, date handling in GoogleNews is sometimes tricky
                news_items.append(NewsItem(
                    title=item.get('title', ''),
                    link=item.get('link', ''),
                    date=item.get('date', ''),
                    source=item.get('media', '')
                ))
            
            # Update Cache
            final_items = news_items[:10]
            self._cache[query] = {
                'timestamp': now,
                'data': final_items
            }
            logger.info("news_fetched_fresh", query=query, count=len(final_items))
            
            return final_items

        except Exception as e:
            logger.error("fetch_news_error", query=query, error=str(e))
            return []
