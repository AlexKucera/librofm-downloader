"""Path resolution and sanitization for librofm-downloader.

Pure logic module — no I/O, no network. All deterministic string manipulation.
"""

import re
from pathlib import Path

from librofm_downloader.book import Book


# Characters that are unsafe in filesystem path components
_ILLEGAL_CHARS = str.maketrans("", "", "<>/\\|?*")

# Control characters U+0000–U+001F
_CONTROL_CHARS = {chr(i) for i in range(0x00, 0x20)}


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
    result = component.replace(":", " -")
    result = result.translate(_ILLEGAL_CHARS)
    result = "".join(ch for ch in result if ch not in _CONTROL_CHARS)
    result = result.strip()
    result = result.rstrip(".")
    return result[:255]


# Token name → (attribute_path, formatter)
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
    val = getattr(book, attr)
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

    Returns True when PDF extras are present.
    Cover art does NOT trigger a subdirectory here — cover downloads are
    config-gated (``config.download_covers``) and considered separately
    in ``_resolve_output_dir``.
    """
    return bool(book.pdf_extras)


def _resolve_output_dir(
    book: Book,
    output_base: Path | str,
    config: "Config | None" = None,
) -> Path:
    """Resolve the output directory for a book (parent of the actual file).

    For books with accompanying files → subdirectory: base/Author/Title/
    For standalone books → parent dir only: base/Author/  (file is leaf: Title.m4b)

    Subdirectory is needed when:
    - PDF extras exist (multi-file output), OR
    - Cover art will be downloaded (``config.download_covers`` + ``book.cover_url``)
    """
    base = Path(output_base)
    first_author = sanitize(book.authors[0] if book.authors else 'Unknown')

    needs_subdir = needs_subdirectory(book)  # pdf_extras
    if not needs_subdir and config is not None:
        needs_subdir = bool(config.download_covers and book.cover_url)

    if needs_subdir:
        relative = resolve_path(book)  # e.g. "Author/Title" — already includes title
        return base / relative

    # Flat: file is leaf node under author dir
    return base / first_author
