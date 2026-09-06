from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional

import feedparser
import httpx

from app.models.market_schemas import NewsHeadline

logger = logging.getLogger("moneycontrol_rss")
_MAX_SNIPPET_CHARS = 280


class MoneycontrolRSSError(RuntimeError):
    pass


class MoneycontrolRSSClient:
    def __init__(self, feed_urls: list[str], http_client: Optional[httpx.AsyncClient] = None):
        if not feed_urls:
            raise ValueError("At least one Moneycontrol RSS feed URL must be configured")
        self._feed_urls = feed_urls
        self._client = http_client or httpx.AsyncClient(timeout=15.0, follow_redirects=True)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_all(self, max_items_per_feed: int = 20) -> list[NewsHeadline]:
        import asyncio
        results = await asyncio.gather(
            *(self._fetch_one(url, max_items_per_feed) for url in self._feed_urls), return_exceptions=True,
        )
        headlines: list[NewsHeadline] = []
        for url, result in zip(self._feed_urls, results):
            if isinstance(result, Exception):
                logger.warning("Failed to fetch Moneycontrol feed %s: %s", url, result)
                continue
            headlines.extend(result)
        return headlines

    async def _fetch_one(self, url: str, max_items: int) -> list[NewsHeadline]:
        resp = await self._client.get(url)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        if parsed.bozo and not parsed.entries:
            raise MoneycontrolRSSError(f"Could not parse RSS feed at {url}: {parsed.bozo_exception}")

        items: list[NewsHeadline] = []
        for entry in parsed.entries[:max_items]:
            raw_summary = getattr(entry, "summary", "") or ""
            snippet = _strip_html(raw_summary)[:_MAX_SNIPPET_CHARS]
            published_at = _parse_published(entry)
            items.append(NewsHeadline(source="moneycontrol", headline=getattr(entry, "title", "").strip(),
                                        snippet=snippet, url=getattr(entry, "link", ""), published_at=published_at))
        return items


def _strip_html(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", text).strip()


def _parse_published(entry) -> Optional[datetime]:
    parsed_time = getattr(entry, "published_parsed", None)
    if not parsed_time:
        return None
    import calendar
    return datetime.fromtimestamp(calendar.timegm(parsed_time), tz=timezone.utc)
