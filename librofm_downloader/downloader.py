"""Path resolution and sanitization for librofm-downloader.

Pure logic module — no I/O, no network. All deterministic string manipulation.
"""

import re
from dataclasses import dataclass

# Characters that are unsafe in filesystem path components
_ILLEGAL_CHARS = str.maketrans("", "", "<>/\\|?*")

# Control characters U+0000–U+001F
_CONTROL_CHARS = {chr(i) for i in range(0x00, 0x20)}


@dataclass(frozen=True)
class Book:
    """Immutable book metadata record from Libro.fm."""

    title: str
    authors: list[str]
    narrators: list[str]
    isbn: str
    series: str = ""
    series_num: int | None = None
    cover_url: str = ""
    pdf_extras: bool = False
    publication_year: int | None = None
    publication_month: int | None = None
    publication_day: int | None = None


def sanitize(component: str) -> str:
    """Sanitize a single path component for filesystem safety.

    Rules applied in order:
    1. Replace ``:`` with `` -``
    2. Strip ``< > / \\ | ? *`` and control characters (U+0000–U+001F)
    3. Remove trailing dots
    4. Trim whitespace
    5. Cap at 255 characters

    Preserves: dashes, commas, apostrophes, parentheses, periods (non-trailing).
    """
    # 1. Replace colons
    result = component.replace(":", " -")
    # 2. Strip illegal chars and control characters
    result = result.translate(_ILLEGAL_CHARS)
    result = "".join(ch for ch in result if ch not in _CONTROL_CHARS)
    # 3. Trim whitespace (before dot removal so exposed dots are caught)
    result = result.strip()
    # 4. Remove trailing dots
    result = result.rstrip(".")
    # 5. Cap at 255 characters
    return result[:255]


# Token name → (attribute_path, formatter)
# attribute_path is a space-separated chain of attr lookups;
# formatter converts the raw value to string.
_TOKEN_REGISTRY: dict[str, tuple[str, str]] = {
    "FIRST_AUTHOR":  ("authors", "first"),
    "ALL_AUTHORS":   ("authors", "join"),
    "SERIES_NAME":   ("series", "raw"),
    "SERIES_NUM":    ("series_num", "raw"),
    "BOOK_TITLE":    ("title", "raw"),
    "ISBN":          ("isbn", "raw"),
    "FIRST_NARRATOR":("narrators", "first"),
    "ALL_NARRATORS": ("narrators", "join"),
    "PUBLICATION_YEAR":  ("publication_year", "raw"),
    "PUBLICATION_MONTH": ("publication_month", "raw"),
    "PUBLICATION_DAY":   ("publication_day", "raw"),
}


def _token_value(book: Book, token: str) -> str:
    """Resolve a single token to its string value from the book."""
    if token not in _TOKEN_REGISTRY:
        return ""
    attr, fmt = _TOKEN_REGISTRY[token]
    # Get the attribute value
    val = getattr(book, attr)
    # Format based on formatter type
    if fmt == "first":
        if isinstance(val, list) and val:
            return str(val[0])
        return ""
    if fmt == "join":
        if isinstance(val, list):
            return ", ".join(str(v) for v in val)
        return str(val) if val is not None else ""
    # fmt == "raw"
    return str(val) if val is not None else ""


def resolve_path(book: Book, pattern: str | None = None) -> str:
    """Resolve the relative output path for a book.

    Args:
        book: The book metadata.
        pattern: Optional custom path pattern with token placeholders.
                When set, overrides default conditional logic.
                Tokens: FIRST_AUTHOR, ALL_AUTHORS, SERIES_NAME, SERIES_NUM,
                BOOK_TITLE, ISBN, FIRST_NARRATOR, ALL_NARRATORS,
                PUBLICATION_YEAR, PUBLICATION_MONTH, PUBLICATION_DAY.

    Returns:
        Sanitized relative path string.
    """
    if pattern:
        return _resolve_custom_pattern(book, pattern)
    return _resolve_default_path(book)


def _resolve_default_path(book: Book) -> str:
    """Default conditional path logic."""
    first_author = sanitize(book.authors[0] if book.authors else "Unknown")
    title = sanitize(book.title)

    if book.series and book.series_num is not None:
        series_name = sanitize(book.series)
        return f"{first_author}/{series_name}/Book {book.series_num} {title}"

    if book.series:
        series_name = sanitize(book.series)
        return f"{first_author}/{series_name}/{title}"

    return f"{first_author}/{title}"


def _resolve_custom_pattern(book: Book, pattern: str) -> str:
    """Resolve path using custom pattern with token substitution."""

    def replacer(match: re.Match) -> str:
        token = match.group(1)
        raw = _token_value(book, token)
        return sanitize(raw)

    # Replace {TOKEN} patterns
    result = re.sub(r"\{([A-Z_]+)\}", replacer, pattern)
    return result


def needs_subdirectory(book: Book) -> bool:
    """Check whether a book needs a subdirectory for accompanying files.

    Returns True when PDF extras or cover art are present.
    """
    return bool(book.pdf_extras) or bool(book.cover_url)
