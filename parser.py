import logging
import re
from urllib.parse import urljoin, urlparse

from markdownify import markdownify as turndown

logger = logging.getLogger(__name__)
NOTION_MAX_TEXT_LENGTH = 2000
NOTION_MAX_URL_LENGTH = 2000
_ALLOWED_URL_SCHEMES = {"http", "https"}
_LINK_RE = re.compile(r'\[(.+?)]\((.+?)\)')
_NUMBERED_LIST_RE = re.compile(r'^\d+\.\s')


def html_to_markdown(html_content: str) -> str:
    """Convert HTML content to Markdown."""
    try:
        return turndown(html_content)
    except Exception as e:
        logger.error("Error converting HTML to Markdown: %s", e)
        return ""


def _truncate(text: str, max_len: int = NOTION_MAX_TEXT_LENGTH) -> str:
    """Truncate text to fit Notion's per-block character limit."""
    return text[:max_len] if len(text) > max_len else text


def _normalize_url(url: str, base_url: str = "") -> str | None:
    """Resolve a possibly relative URL into an absolute http(s) URL Notion accepts."""
    parts = url.strip().split()
    if not parts:
        return None

    absolute = urljoin(base_url, parts[0].strip("<>"))
    parsed = urlparse(absolute)
    if parsed.scheme not in _ALLOWED_URL_SCHEMES or not parsed.netloc:
        return None
    if len(absolute) > NOTION_MAX_URL_LENGTH:
        return None
    return absolute


def _make_rich_text(content: str, *, link: str | None = None, **annotations) -> list[dict]:
    text_obj: dict = {"content": _truncate(content)}
    if link:
        text_obj["link"] = {"url": link}
    entry: dict = {"type": "text", "text": text_obj}
    if annotations:
        entry["annotations"] = annotations
    return [entry]


def _make_block(block_type: str, rich_text: list[dict]) -> dict:
    return {"type": block_type, block_type: {"rich_text": rich_text}}


def markdown_to_notion_blocks(markdown_content: str, base_url: str = "") -> list[dict]:
    """Convert Markdown content to Notion blocks."""
    blocks: list[dict] = []

    for line in markdown_content.split("\n"):
        line = line.strip()
        if not line:
            continue

        if line.startswith("### "):
            blocks.append(_make_block("heading_3", _make_rich_text(line[4:])))
        elif line.startswith("## "):
            blocks.append(_make_block("heading_2", _make_rich_text(line[3:])))
        elif line.startswith("# "):
            blocks.append(_make_block("heading_1", _make_rich_text(line[2:])))
        elif line.startswith("- ") or line.startswith("* "):
            blocks.append(_make_block("bulleted_list_item", _make_rich_text(line[2:])))
        elif _NUMBERED_LIST_RE.match(line):
            text = _NUMBERED_LIST_RE.sub("", line, count=1)
            blocks.append(_make_block("numbered_list_item", _make_rich_text(text)))
        elif line.startswith("**") and line.endswith("**") and len(line) > 4:
            blocks.append(_make_block("paragraph", _make_rich_text(line[2:-2], bold=True)))
        elif line.startswith("*") and line.endswith("*") and len(line) > 2:
            blocks.append(_make_block("paragraph", _make_rich_text(line[1:-1], italic=True)))
        elif line.startswith("`") and line.endswith("`") and len(line) > 2:
            blocks.append(_make_block("paragraph", _make_rich_text(line[1:-1], code=True)))
        elif line.startswith("http://") or line.startswith("https://"):
            blocks.append(
                _make_block("paragraph", _make_rich_text(line, link=_normalize_url(line)))
            )
        elif line.startswith("Comments URL: <") and line.endswith(">"):
            # Convert 'Comments URL: <https://example>' to Notion hyperlinked text
            label, link = line.split("<")
            label = label.replace(":", "").strip()
            link = link[:-1].strip()
            blocks.append(
                _make_block(
                    "paragraph",
                    _make_rich_text(f"{label}: {link}", link=_normalize_url(link, base_url)),
                )
            )
        else:
            link_match = _LINK_RE.match(line)
            if link_match:
                text_part, url_part = link_match.groups()
                blocks.append(
                    _make_block(
                        "paragraph",
                        _make_rich_text(text_part, link=_normalize_url(url_part, base_url)),
                    )
                )
            else:
                blocks.append(_make_block("paragraph", _make_rich_text(line)))

    return blocks


def html_to_notion_blocks(html_content: str, base_url: str = "") -> list[dict]:
    """Convert HTML content to Notion blocks."""
    markdown = html_to_markdown(html_content)
    return markdown_to_notion_blocks(markdown, base_url=base_url)
