import logging

from feed import get_new_feed_items
from feishu import send_feed_summary_to_feishu
from notion import add_feed_item_to_notion, delete_old_unread_feed_items_from_notion
from parser import html_to_notion_blocks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for the Notion Feeder application."""
    feed_items = get_new_feed_items()
    logger.info("Fetched %d new feed items", len(feed_items))

    if feed_items and not send_feed_summary_to_feishu(feed_items):
        logger.warning("Feishu webhook failed, continuing Notion workflow")

    success, failed = 0, 0
    for item in feed_items:
        notion_item = {
            "title": item.get("title", ""),
            "link": item.get("link", ""),
            "content": html_to_notion_blocks(item.get("content", "")),
        }
        if add_feed_item_to_notion(notion_item):
            success += 1
        else:
            failed += 1

    logger.info("Notion write complete: %d success, %d failed", success, failed)

    if failed:
        raise RuntimeError(f"Notion write failed for {failed} item(s)")

    delete_old_unread_feed_items_from_notion()


if __name__ == "__main__":
    main()
