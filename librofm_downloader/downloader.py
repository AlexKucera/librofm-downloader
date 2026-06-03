"""Path resolution and sanitization for librofm-downloader.

Pure logic module — no I/O, no network. All deterministic string manipulation.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from librofm_downloader.client import M4BUnavailableError
from librofm_downloader.history import HistoryEntry

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# MP3 ZIP download + extraction
# ---------------------------------------------------------------------------

import zipfile as _zipfile

# Constants for downloads

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB


def _part_filename_from_url(url: str) -> str:
    """Derive a safe filename from a URL's last path component."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    name = Path(parsed.path).stem or "download"
    return sanitize(name)


def download_zip_part(
    url: str,
    output_dir: Path | str,
    transport: httpx.BaseTransport | None = None,
    progress: "Callable[[int], None] | None" = None,
) -> list[Path]:
    """Download a single ZIP part and extract its contents.

    Downloads to ``{name}.zip.partial`` during transfer, renames to
    ``{name}.zip`` on completion, then extracts all files into *output_dir*.

    Args:
        url: The CDN URL for this ZIP part.
        output_dir: Directory where extracted files are written.
        transport: Optional httpx transport override for testing.

    Returns:
        List of Paths to extracted files.

    Raises:
        zipfile.BadZipFile: If downloaded data is not valid ZIP.
        httpx.HTTPStatusError: On HTTP errors.
    """
    output_dir = Path(output_dir)
    part_name = _part_filename_from_url(url)
    zip_path = output_dir / f"{part_name}.zip"
    partial_path = output_dir / f"{part_name}.zip.partial"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Resume support
    resume_from = 0
    if partial_path.exists():
        resume_from = partial_path.stat().st_size
        logger.info("Resuming ZIP part from byte %d", resume_from)

    headers: dict[str, str] = {}
    if resume_from > 0:
        headers["Range"] = f"bytes={resume_from}-"

    client = httpx.Client(transport=transport, follow_redirects=True)
    mode = "ab" if resume_from > 0 else "wb"

    with client.stream("GET", url, headers=headers) as resp:
        resp.raise_for_status()
        with open(partial_path, mode) as f:
            downloaded = resume_from
            content_length: int | None = None
            for chunk in resp.iter_bytes(chunk_size=CHUNK_SIZE):
                f.write(chunk)
                downloaded += len(chunk)
                if progress:
                    if content_length is None:
                        cl_header = resp.headers.get("content-length")
                        if cl_header:
                            content_length = int(cl_header)
                        progress(downloaded, total=content_length)
                    else:
                        progress(downloaded)

    # Atomic rename from .partial to .zip
    partial_path.rename(zip_path)

    # Extract all files from ZIP into output_dir
    extracted: list[Path] = []
    with _zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(output_dir)
                for name in zf.namelist():
                    extracted.append(output_dir / name)

    # Clean up ZIP file after extraction
    zip_path.unlink(missing_ok=True)

    logger.info("Downloaded & extracted %s → %d file(s) in %s", url, len(extracted), output_dir)
    return extracted


# ---------------------------------------------------------------------------
# M4B streaming download
# ---------------------------------------------------------------------------


def download_m4b(
    url: str,
    output_path: Path | str,
    transport: httpx.BaseTransport | None = None,
    progress: "Callable[[int], None] | None" = None,
) -> Path:
    """Download an M4B file via streaming chunks.

    Writes to ``{output_path}.partial`` during transfer, then atomically
    renames to the final ``{output_path}`` on completion.

    Args:
        url: The CDN URL for the M4B file.
        output_path: Destination path (will have .m4b extension).
        transport: Optional httpx transport override for testing.

    Returns:
        The Path of the completed .m4b file.
    """
    output_path = Path(output_path)
    partial_path = output_path.with_suffix(output_path.suffix + ".partial")

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Resume support: detect existing partial file
    resume_from = 0
    if partial_path.exists():
        resume_from = partial_path.stat().st_size
        logger.info("Resuming download from byte %d", resume_from)

    headers: dict[str, str] = {}
    if resume_from > 0:
        headers["Range"] = f"bytes={resume_from}-"

    client = httpx.Client(transport=transport, follow_redirects=True)

    mode = "ab" if resume_from > 0 else "wb"

    with client.stream("GET", url, headers=headers) as resp:
        resp.raise_for_status()

        with open(partial_path, mode) as f:
            downloaded = resume_from
            content_length: int | None = None
            for chunk in resp.iter_bytes(chunk_size=CHUNK_SIZE):
                f.write(chunk)
                downloaded += len(chunk)
                if progress:
                    if content_length is None:
                        cl_header = resp.headers.get("content-length")
                        if cl_header:
                            content_length = int(cl_header)
                        progress(downloaded, total=content_length)
                    else:
                        progress(downloaded)

    # Atomic rename from .partial to final filename
    partial_path.rename(output_path)

    logger.info("Downloaded %s → %s", url, output_path)
    return output_path


def _resolve_output_dir(book: Book, output_base: Path | str) -> Path:
    """Resolve the output directory for a book (parent of the actual file).

    For books with accompanying files → subdirectory: base/Author/Series/Book Title/
    For standalone books → parent dir only: base/Author/  (file is leaf: Title.m4b)
    """
    base = Path(output_base)
    first_author = sanitize(book.authors[0] if book.authors else 'Unknown')

    if needs_subdirectory(book):
        relative = resolve_path(book)
        title_sanitized = sanitize(book.title)
        return base / relative / title_sanitized

    # Flat: file is leaf node under author dir
    return base / first_author


def download_book(
    book: Book,
    client: "LibroFmClient",
    output_base: Path | str,
    history: "DownloadHistory",
    format_strategy: str = "m4b_mp3_fallback",
    config: "Config | None" = None,
    transport: httpx.BaseTransport | None = None,
    progress: "Callable[[int], None] | None" = None,
) -> Path | None:
    """Orchestrate a single book download with format strategy.

    Args:
        book: The book metadata.
        client: Authenticated LibroFmClient instance.
        output_base: Base directory for downloads.
        history: DownloadHistory instance to record successful downloads.
        format_strategy: One of ``m4b_mp3_fallback``, ``mp3_only``, ``m4b_only``.
        config: Optional Config for accompanying file settings.
        transport: Optional httpx transport override for testing.

    Returns:
        Path to the downloaded file/dir, or None if book is skipped.
    """
    from datetime import datetime, timezone

    output_dir = _resolve_output_dir(book, output_base)
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- m4b_mp3_fallback: try M4B first, fall back to MP3 ---
    if format_strategy == "m4b_mp3_fallback":
        # Try M4B first
        try:
            m4b_url = client.fetch_m4b_url(book.isbn, transport=transport)
            title_sanitized = sanitize(book.title)
            m4b_path = output_dir / f"{title_sanitized}.m4b"
            result = download_m4b(m4b_url, m4b_path, transport=transport, progress=progress)
            _write_history(history, book, "m4b", str(result))
            if config:
                download_accompanying_files(book, output_dir, config, client=client, transport=transport)
            return result
        except M4BUnavailableError:
            logger.info("M4B not available for %s (%s), falling back to MP3", book.title, book.isbn)

        # Fall back to MP3
        result = _download_mp3(book, client, output_dir, history, transport)
        if result and config:
            download_accompanying_files(book, output_dir, config, client=client, transport=transport)
        return result

    # --- mp3_only: skip M4B entirely ---
    if format_strategy == "mp3_only":
        result = _download_mp3(book, client, output_dir, history, transport)
        if result and config:
            download_accompanying_files(book, output_dir, config, client=client, transport=transport)
        return result

    # --- m4b_only: skip book if M4B unavailable ---
    if format_strategy == "m4b_only":
        try:
            m4b_url = client.fetch_m4b_url(book.isbn, transport=transport)
            title_sanitized = sanitize(book.title)
            m4b_path = output_dir / f"{title_sanitized}.m4b"
            result = download_m4b(m4b_url, m4b_path, transport=transport, progress=progress)
            _write_history(history, book, "m4b", str(result))
            if config:
                download_accompanying_files(book, output_dir, config, client=client, transport=transport)
            return result
        except M4BUnavailableError:
            logger.info("Skipping %s (%s): no M4B available (m4b_only mode)", book.title, book.isbn)
            return None

    raise ValueError(f"Unknown format strategy: {format_strategy}")


def _download_mp3(
    book: Book,
    client: "LibroFmClient",
    output_dir: Path,
    history: "DownloadHistory",
    transport: httpx.BaseTransport | None = None,
    progress: "Callable[[int], None] | None" = None,
) -> Path | None:
    """Fetch MP3 manifest and download all ZIP parts."""
    try:
        manifest = client.fetch_download_manifest(book.isbn, transport=transport)
    except M4BUnavailableError:
        logger.warning("MP3 manifest not available for %s (%s), skipping", book.title, book.isbn)
        return None

    parts = manifest.get("parts", [])
    if not parts:
        logger.warning("Empty parts list in manifest for %s (%s), skipping", book.title, book.isbn)
        return None

    all_extracted: list[Path] = []
    for part in parts:
        part_url = part["url"]
        extracted = download_zip_part(part_url, output_dir, transport=transport, progress=progress)
        all_extracted.extend(extracted)

    # Record first extracted file as representative path
    if all_extracted:
        _write_history(history, book, "mp3", str(output_dir))
        return output_dir

    return None


# ---------------------------------------------------------------------------
# Accompanying files download — Issue #7
# ---------------------------------------------------------------------------

import tempfile as _tempfile
from urllib.parse import urlparse as _urlparse


def _cover_filename_from_url(url: str) -> str:
    """Derive a cover filename from URL, defaulting to 'cover.jpg'."""
    parsed = _urlparse(url)
    name = Path(parsed.path).name or "cover.jpg"
    return sanitize(name)


def _download_cover(
    url: str,
    output_dir: Path,
    transport: httpx.BaseTransport | None = None,
) -> Path | None:
    """Download a cover art file via streaming .partial → atomic rename.

    Returns Path on success, None on failure (logs warning).
    """
    filename = _cover_filename_from_url(url)
    output_path = output_dir / filename
    partial_path = output_path.with_suffix(output_path.suffix + ".partial")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        client = httpx.Client(transport=transport, follow_redirects=True)
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(partial_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=CHUNK_SIZE):
                    f.write(chunk)

        partial_path.rename(output_path)
        logger.info("Downloaded cover → %s", output_path)
        return output_path
    except Exception as exc:
        logger.warning("Failed to download cover from %s: %s", url, exc)
        # Clean up partial file if it exists
        partial_path.unlink(missing_ok=True)
        return None


def _download_pdf(
    url: str,
    filename: str,
    output_dir: Path,
    transport: httpx.BaseTransport | None = None,
) -> Path | None:
    """Download a PDF extra file via streaming .partial → atomic rename.

    Returns Path on success, None on failure (logs warning).
    """
    safe_name = sanitize(filename)
    output_path = output_dir / safe_name
    partial_path = output_path.with_suffix(output_path.suffix + ".partial")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        client = httpx.Client(transport=transport, follow_redirects=True)
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(partial_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=CHUNK_SIZE):
                    f.write(chunk)

        partial_path.rename(output_path)
        logger.info("Downloaded PDF extra → %s", output_path)
        return output_path
    except Exception as exc:
        logger.warning("Failed to download PDF from %s: %s", url, exc)
        partial_path.unlink(missing_ok=True)
        return None


def download_accompanying_files(
    book: Book,
    output_dir: Path | str,
    config: "Config",
    client: "LibroFmClient | None" = None,
    transport: httpx.BaseTransport | None = None,
    progress: "Callable[[int], None] | None" = None,
) -> list[Path]:
    """Download PDF extras and/or cover art for a book.

    Non-critical: failures log warnings but do not raise.

    Args:
        book: The book metadata.
        output_dir: Directory where accompanying files are placed.
        config: Config with download_extras / download_covers toggles.
        client: Optional LibroFmClient for fetching PDF URLs.
        transport: Optional httpx transport override for testing.

    Returns:
        List of Paths successfully downloaded.
    """
    from librofm_downloader.client import LibroFmClient

    output_dir = Path(output_dir)
    downloaded: list[Path] = []

    # Download cover art if enabled and available
    if config.download_covers and book.cover_url:
        result = _download_cover(book.cover_url, output_dir, transport=transport)
        if result:
            downloaded.append(result)

    # Download PDF extras if enabled and available
    if config.download_extras and book.pdf_extras and client is not None:
        try:
            pdf_url = client.fetch_pdf_extra_url(book.isbn, "map.pdf", transport=transport)
            if pdf_url:
                result = _download_pdf(pdf_url, "map.pdf", output_dir, transport=transport)
                if result:
                    downloaded.append(result)
        except Exception as exc:
            logger.warning("Failed to fetch PDF URL for %s: %s", book.isbn, exc)

    return downloaded


def _write_history(
    history: "DownloadHistory",
    book: Book,
    fmt: str,
    path: str,
) -> None:
    """Write a download history entry."""
    from datetime import datetime, timezone

    entry = HistoryEntry(
        isbn=book.isbn,
        title=book.title,
        format=fmt,
        path=path,
        downloaded_at=datetime.now(timezone.utc).isoformat(),
    )
    history.write(entry)
