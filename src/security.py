import html
import logging
import re
from typing import Optional
from src.config import settings

logger = logging.getLogger(__name__)

# Control characters to strip (ASCII 0x00-0x1F, excluding \t, \n, \r)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")

# Unicode Bidirectional Override and Invisible Format characters
_BIDI_AND_FORMAT_RE = re.compile(r"[\u200B-\u200F\u202A-\u202E\u2060-\u206F\uFEFF]")

# HTML script and style block remover
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


def sanitize_user_input(query: str, max_chars: Optional[int] = None) -> str:
    """
    Validates and sanitizes a user-submitted research query.

    Args:
        query: Raw query string from user.
        max_chars: Optional maximum character limit (defaults to config setting).

    Returns:
        Cleaned, sanitized query string.

    Raises:
        ValueError: If query is empty or exceeds maximum character limit.
    """
    if not isinstance(query, str):
        raise ValueError("Research query must be a string.")

    cleaned = query.strip()
    if not cleaned:
        raise ValueError("Research query cannot be empty.")

    limit = max_chars or settings.max_query_length
    if len(cleaned) > limit:
        raise ValueError(
            f"Research query exceeds maximum allowed length of {limit} characters "
            f"({len(cleaned)} characters provided). Please shorten your question."
        )

    # Strip dangerous control and BIDI override characters
    cleaned = _CONTROL_CHAR_RE.sub("", cleaned)
    cleaned = _BIDI_AND_FORMAT_RE.sub("", cleaned)

    # Normalize excessive consecutive whitespace
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned.strip()


def sanitize_web_content(content: str, max_chars: Optional[int] = None) -> str:
    """
    Sanitizes untrusted web content retrieved from search engines.

    Args:
        content: Raw snippet or page content.
        max_chars: Maximum character limit for the snippet.

    Returns:
        Sanitized content string.
    """
    if not content:
        return ""

    limit = max_chars or settings.max_content_chars_per_source

    # 1. Strip raw script/style blocks
    text = _SCRIPT_STYLE_RE.sub("", content)

    # 2. Strip null bytes, control, and format spoofing characters
    text = _CONTROL_CHAR_RE.sub("", text)
    text = _BIDI_AND_FORMAT_RE.sub("", text)

    # 3. Normalize whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    # 4. Enforce strict character length limit (Lesson 3 & PRD Section 4)
    if len(text) > limit:
        text = text[:limit] + " ... [content truncated for length and security]"

    return text


def escape_structural_tags(text: str) -> str:
    """
    Neutralizes structural delimiter tags inside untrusted text to prevent
    delimiter-breaking and prompt escape attacks.
    """
    if not text:
        return ""
    # Escape opening and closing delimiter tags
    text = text.replace("</untrusted_source_content>", "[escaped_closing_tag]")
    text = text.replace("<untrusted_source_content>", "[escaped_opening_tag]")
    text = re.sub(r"</?untrusted_source_content[^>]*>", "[escaped_tag]", text, flags=re.IGNORECASE)
    return text


def wrap_in_delimiters(
    source_id: int,
    title: str,
    url: str,
    content: str,
    matched_query: Optional[str] = None
) -> str:
    """
    Wraps an untrusted search result in strict structural XML-style delimiters
    with tag-escaping and metadata attributes.
    """
    safe_title = escape_structural_tags(title.strip() if title else "Untitled Source")
    safe_url = escape_structural_tags(url.strip() if url else "N/A")
    sanitized_content = sanitize_web_content(content)
    safe_content = escape_structural_tags(sanitized_content)

    query_attr = f' query="{escape_structural_tags(matched_query)}"' if matched_query else ""

    return (
        f'<untrusted_source_content index="{source_id}" url="{safe_url}" title="{safe_title}"{query_attr}>\n'
        f"{safe_content}\n"
        f"</untrusted_source_content>"
    )
