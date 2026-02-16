from typing import List
import structlog
from .news import NewsFetcher
from .ai import AIAnalyzer
from config import settings

logger = structlog.get_logger()

class MarketScanner:
    def __init__(self, news_fetcher: NewsFetcher, ai_analyzer: AIAnalyzer):
        self.news_fetcher = news_fetcher
        self.ai_analyzer = ai_analyzer

    async def scan_market(self) -> List[str]:
        """Scans for trending stocks based on news."""
        logger.info("scanning_market_trends")
        
        # 1. Fetch General Market News
        # Keywords to find "hot" stocks
        queries = ["top gaining stocks today", "most active stocks", "stocks in the news"]
        all_news = []
        for q in queries:
            news = await self.news_fetcher.get_news(q)
            all_news.extend(news)
        
        # Deduplicate
        unique_news = {n.title: n for n in all_news}.values()
        
        if not unique_news:
            logger.warning("no_market_news_found")
            return []

        # 2. Use AI to extract Tickers from Headlines
        headlines = "\n".join([f"- {n.title}" for n in list(unique_news)[:15]])
        
        prompt = f"""
        Analyze these news headlines and extract a list of stock tickers (symbols) that are being positively discussed or have significant activity.
        
        CRITICAL INSTRUCTION:
        - Return tickers in Yahoo Finance format.
        - For US stocks: "AAPL", "TSLA", "NVDA"
        - For Indian stocks (NSE): Append ".NS", e.g. "RELIANCE.NS", "TCS.NS", "BEML.NS"
        - Ignore general market indices like SPY, NDAQ, DOW, SENSEX, NIFTY.
        
        Headlines:
        {headlines}
        
        Return ONLY a JSON list of strings.
        """
        
        try:
            response = await self.ai_analyzer.generate_text(prompt)
            
            # Extract JSON list
            import json
            import re
            
            # Find JSON-like array
            match = re.search(r'\[.*\]', response, re.DOTALL)
            if match:
                json_str = match.group(0)
                tickers = json.loads(json_str)
                valid_tickers = [t.upper() for t in tickers if isinstance(t, str)]
                
                logger.info("market_scan_results", tickers=valid_tickers)
                
                # Save to DB
                from database.db import save_market_trend
                from database.models import MarketTrend
                import json as pyjson
                
                if valid_tickers:
                    await save_market_trend(MarketTrend(tickers=pyjson.dumps(valid_tickers)))
                
                return valid_tickers
            else:
                logger.warning("market_scan_no_json", response=response)
                return []
            
        except Exception as e:
            logger.error("scanner_error", error=str(e))
            return []
