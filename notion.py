import datetime
import logging
import os

import requests
from dotenv import load_dotenv

from network import request_with_retries

load_dotenv()

logger = logging.getLogger(__name__)

NOTION_API_TOKEN = os.getenv("NOTION_API_TOKEN")
NOTION_READER_DATABASE_ID = os.getenv("NOTION_READER_DATABASE_ID")
NOTION_FEEDS_DATABASE_ID = os.getenv("NOTION_FEEDS_DATABASE_ID")

NOTION_API_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"
_MAX_BLOCKS_PER_REQUEST = 100
_REQUEST_TIMEOUT = 30
_ARCHIVE_AFTER_DAYS = 30
_SAFE_REQUEST_RETRIES = 2
_CREATE_PAGE_MAX_ATTEMPTS = 3


class NotionAPIError(RuntimeError):
    """Raised when a critical Notion API operation fails."""


def _get_headers() -> dict[str, str]:
    """Get common headers for Notion API requests."""
    return {
        "Authorization": f"Bearer {NOTION_API_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_API_VERSION,
    }


def _notion_request(
    method: str,
    path: str,
    *,
    max_retries: int,
    operation_name: str,
    **kwargs,
) -> requests.Response:
    """Execute a request against Notion API with standard headers and retry control."""
    return request_with_retries(
        method=method,
        url=f"{NOTION_BASE_URL}{path}",
        headers=_get_headers(),
        timeout=_REQUEST_TIMEOUT,
        max_retries=max_retries,
        operation_name=operation_name,
        **kwargs,
    )


def _query_database_with_pagination(database_id: str, payload: dict) -> list[dict]:
    """Query a Notion database handling pagination automatically."""
    all_results: list[dict] = []
    has_more = True
    start_cursor: str | None = None

    while has_more:
        page_payload = payload.copy()
        if start_cursor:
            page_payload["start_cursor"] = start_cursor

        try:
            response = _notion_request(
                "POST",
                f"/databases/{database_id}/query",
                json=page_payload,
                max_retries=_SAFE_REQUEST_RETRIES,
                operation_name=f"query notion database {database_id}",
            )
        except requests.exceptions.RequestException as err:
            raise NotionAPIError(
                f"Failed to query Notion database {database_id}"
            ) from err

        data = response.json()
        all_results.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return all_results


def _reader_item_exists(title: str, link: str) -> bool:
    """Check if a Reader record already exists by Link, or by Title when link is empty."""
    if link:
        query_payload = {
            "page_size": 1,
            "filter": {"property": "Link", "url": {"equals": link}},
        }
    else:
        query_payload = {
            "page_size": 1,
            "filter": {"property": "Title", "title": {"equals": title}},
        }

    results = _query_database_with_pagination(NOTION_READER_DATABASE_ID, query_payload)
    return bool(results)


def get_feed_urls_from_notion() -> list[dict]:
    """Fetch enabled feed URLs from the Feeds database in Notion."""
    payload = {
        "filter": {
            "property": "Enabled",
            "checkbox": {"equals": True},
        }
    }

    results = _query_database_with_pagination(NOTION_FEEDS_DATABASE_ID, payload)

    feeds: list[dict] = []
    for item in results:
        props = item.get("properties", {})
        title_prop = props.get("Title", {}).get("title", [])
        link_prop = props.get("Link", {}).get("url")

        title = title_prop[0].get("plain_text", "") if title_prop else ""
        feeds.append({"title": title, "feedUrl": link_prop})

    return feeds


def get_existing_items_since(days: int = 5) -> tuple[set[str], set[str]]:
    """Batch-fetch recent items from Reader database, returning sets for dedup.

    Returns:
        A tuple of (titles_set, links_set) for fast membership checks.
    """
    since_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=days
    )

    payload = {
        "filter": {
            "property": "Created At",
            "date": {"on_or_after": since_date.isoformat()},
        }
    }

    results = _query_database_with_pagination(NOTION_READER_DATABASE_ID, payload)

    titles: set[str] = set()
    links: set[str] = set()

    for item in results:
        props = item.get("properties", {})
        title_parts = props.get("Title", {}).get("title", [])
        if title_parts:
            titles.add(title_parts[0].get("plain_text", ""))
        link_val = props.get("Link", {}).get("url")
        if link_val:
            links.add(link_val)

    return titles, links


def add_feed_item_to_notion(notion_item: dict) -> bool:
    """Add a new feed item to the Reader database in Notion.

    Handles Notion's 100-block-per-request limit by creating the page with
    the first chunk and appending remaining chunks via the blocks API.

    Creation timeout follows a confirm-before-retry strategy:
    query Reader by Link/Title first to avoid duplicate pages.
    """
    title = notion_item.get("title", "")
    link = notion_item.get("link", "")
    content: list[dict] = notion_item.get("content", [])

    first_chunk = content[:_MAX_BLOCKS_PER_REQUEST]
    remaining_chunks = [
        content[i : i + _MAX_BLOCKS_PER_REQUEST]
        for i in range(_MAX_BLOCKS_PER_REQUEST, len(content), _MAX_BLOCKS_PER_REQUEST)
    ]

    payload = {
        "parent": {"database_id": NOTION_READER_DATABASE_ID},
        "properties": {
            "Title": {"title": [{"text": {"content": title}}]},
            "Link": {"url": link},
        },
        "children": first_chunk,
    }

    page_id = ""
    for attempt in range(1, _CREATE_PAGE_MAX_ATTEMPTS + 1):
        try:
            response = _notion_request(
                "POST",
                "/pages",
                json=payload,
                max_retries=0,
                operation_name=f"create notion page for {title[:60]}",
            )
            page_id = response.json().get("id", "")
            break
        except requests.exceptions.Timeout as err:
            logger.warning(
                "Timeout creating Notion page for '%s' (attempt %d/%d): %s",
                title,
                attempt,
                _CREATE_PAGE_MAX_ATTEMPTS,
                err,
            )
            try:
                if _reader_item_exists(title=title, link=link):
                    logger.info(
                        "Notion page already exists after timeout, treat as success: %s",
                        title,
                    )
                    return True
            except NotionAPIError as lookup_err:
                logger.error(
                    "Failed to confirm page existence after timeout for '%s': %s",
                    title,
                    lookup_err,
                )
                return False

            if attempt == _CREATE_PAGE_MAX_ATTEMPTS:
                logger.error(
                    "Create page failed after %d attempts (timeout): %s",
                    _CREATE_PAGE_MAX_ATTEMPTS,
                    title,
                )
                return False
        except requests.exceptions.RequestException as err:
            logger.error("Error creating Notion page for '%s': %s", title, err)
            return False

    if not page_id:
        logger.error("Missing page id after creating Notion page for '%s'", title)
        return False

    for chunk in remaining_chunks:
        try:
            _notion_request(
                "PATCH",
                f"/blocks/{page_id}/children",
                json={"children": chunk},
                max_retries=0,
                operation_name=f"append blocks to notion page {page_id}",
            )
        except requests.exceptions.RequestException as err:
            logger.error("Error appending blocks to page %s: %s", page_id, err)
            return False

    return True


def delete_old_unread_feed_items_from_notion() -> None:
    """Archive feed items older than configured days that are still unread."""
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=_ARCHIVE_AFTER_DAYS
    )

    payload = {
        "filter": {
            "and": [
                {
                    "property": "Created At",
                    "date": {"on_or_before": cutoff.isoformat()},
                },
                {
                    "property": "Read",
                    "checkbox": {"equals": False},
                },
            ]
        }
    }

    results = _query_database_with_pagination(NOTION_READER_DATABASE_ID, payload)
    archived = 0

    for item in results:
        page_id = item.get("id")
        try:
            _notion_request(
                "PATCH",
                f"/pages/{page_id}",
                json={"archived": True},
                max_retries=_SAFE_REQUEST_RETRIES,
                operation_name=f"archive notion page {page_id}",
            )
            archived += 1
        except requests.exceptions.RequestException as err:
            raise NotionAPIError(f"Failed to archive Notion page {page_id}") from err

    if archived:
        logger.info("Archived %d old unread items", archived)
