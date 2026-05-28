import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import feedparser
import requests
from dotenv import load_dotenv

from network import request_with_retries
from notion import get_existing_items_since, get_feed_urls_from_notion

load_dotenv()

logger = logging.getLogger(__name__)
RUN_FREQUENCY = int(os.getenv("RUN_FREQUENCY", "86400"))
_MAX_FETCH_WORKERS = 5
_RSS_TIMEOUT = 20
_RSS_RETRIES = 2


def _parse_struct_time_to_timestamp(st) -> float:
    """Convert struct_time to timestamp."""
    if st:
        return time.mktime(st)
    return 0.0


def _extract_content(item) -> str:
    """Safely extract content from a feed item."""
    content_list = item.get("content", [])
    if content_list:
        return content_list[0].get("value", "") or item.get("summary", "")
    return item.get("summary", "")


def _get_new_feed_items_from(
    feed_url: str,
    existing_titles: set[str],
    existing_links: set[str],
) -> list[dict]:
    """Fetch and filter new items from a single RSS feed."""
    try:
        response = request_with_retries(
            "GET",
            feed_url,
            timeout=_RSS_TIMEOUT,
            max_retries=_RSS_RETRIES,
            operation_name=f"fetch rss {feed_url}",
        )
    except requests.exceptions.RequestException as err:
        logger.warning("Failed to fetch feed %s: %s", feed_url, err)
        return []

    try:
        rss = feedparser.parse(response.content)
    except Exception as err:
        logger.error("Error parsing feed %s: %s", feed_url, err)
        return []

    current_time_struct = rss.get("updated_parsed") or rss.get("published_parsed")
    current_time = (
        _parse_struct_time_to_timestamp(current_time_struct)
        if current_time_struct
        else time.time()
    )

    new_items: list[dict] = []
    for item in rss.entries:
        pub_date = item.get("published_parsed") or item.get("updated_parsed")
        if not pub_date:
            continue

        blog_published_time = _parse_struct_time_to_timestamp(pub_date)
        if (current_time - blog_published_time) >= RUN_FREQUENCY:
            continue

        title = item.get("title", "")
        link = item.get("link", "")

        if title in existing_titles or link in existing_links:
            continue

        new_items.append(
            {
                "title": title,
                "link": link,
                "content": _extract_content(item),
                "published_parsed": pub_date,
            }
        )

    return new_items


def get_new_feed_items() -> list[dict]:
    """Fetch new items from all enabled RSS feeds concurrently."""
    feeds = get_feed_urls_from_notion()
    existing_titles, existing_links = get_existing_items_since(days=5)

    feed_urls = [f["feedUrl"] for f in feeds if f.get("feedUrl")]
    all_new_feed_items: list[dict] = []

    with ThreadPoolExecutor(max_workers=_MAX_FETCH_WORKERS) as executor:
        futures = {
            executor.submit(
                _get_new_feed_items_from, url, existing_titles, existing_links
            ): url
            for url in feed_urls
        }
        for future in as_completed(futures):
            try:
                all_new_feed_items.extend(future.result())
            except Exception as err:
                logger.error("Error fetching feed %s: %s", futures[future], err)

    all_new_feed_items.sort(
        key=lambda x: _parse_struct_time_to_timestamp(x.get("published_parsed"))
    )

    return all_new_feed_items
