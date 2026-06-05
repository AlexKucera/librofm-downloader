"""Download engine for librofm-downloader.

Streaming downloads (M4B, ZIP parts), accompanying files (covers, PDFs),
and download orchestration. Path logic lives in ``path.py``; Book domain
object lives in ``book.py``.
"""

import logging
import threading
from pathlib import Path

import httpx

from librofm_downloader.book import Book
from librofm_downloader.session import M4BUnavailableError
from librofm_downloader.history import HistoryEntry
from librofm_downloader.path import (
    _resolve_output_dir,
    needs_subdirectory,
    resolve_output_plan,
    resolve_path,
    sanitize,
)

logger = logging.getLogger(__name__)


from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class DownloadResult:
    """Immutable result of a single book download attempt.

    Returned by :func:`download_book` so callers can inspect outcome,
    decide on history writing, and report status.
    """
    status: Literal["downloaded", "skipped", "failed"]
    path: Path | None = None
    format: str | None = None  # e.g. "m4b" or "mp3"
    error: str | None = None


class InterruptedDownload(Exception):
    """Raised when a download is cancelled mid-stream via cancel_event.

    Signals that the user pressed Ctrl+C and the download loop detected
    the cancellation signal between chunks. Distinct from KeyboardInterrupt so
    callers can distinguish "user hit Ctrl+C" from "download was cancelled
    cooperatively during drain."
    """


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
    cancel_event: threading.Event | None = None,
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

    try:
        with client.stream("GET", url, headers=headers) as resp:
            resp.raise_for_status()
            with open(partial_path, mode) as f:
                downloaded = resume_from
                content_length: int | None = None
                for chunk in resp.iter_bytes(chunk_size=CHUNK_SIZE):
                    if cancel_event is not None and cancel_event.is_set():
                        raise InterruptedDownload("Download cancelled by user")
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
    except InterruptedDownload:
        # Skip post-processing on cancellation — partial file stays as .partial
        raise


# ---------------------------------------------------------------------------
# M4B streaming download
# ---------------------------------------------------------------------------


def download_m4b(
    url: str,
    output_path: Path | str,
    transport: httpx.BaseTransport | None = None,
    progress: "Callable[[int], None] | None" = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    """Download an M4B file via streaming chunks.

    Writes to ``{output_path}.partial`` during transfer, then atomically
    renames to the final ``output_path`` on completion.

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

    try:
        with client.stream("GET", url, headers=headers) as resp:
            resp.raise_for_status()

            with open(partial_path, mode) as f:
                downloaded = resume_from
                content_length: int | None = None
                for chunk in resp.iter_bytes(chunk_size=CHUNK_SIZE):
                    if cancel_event is not None and cancel_event.is_set():
                        raise InterruptedDownload("Download cancelled by user")
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
    except InterruptedDownload:
        raise


def download_book(
    book: Book,
    session: "LibroFmSession",
    plan: "OutputPlan",
    reporter: "DownloadReporter",
) -> DownloadResult:
    """Orchestrate a single book download with format strategy.

    Args:
        book: The book metadata.
        session: Authenticated LibroFmSession instance.
        plan: Resolved output paths, format strategy, and extras flags.
        reporter: Reporter for progress callbacks and cancel event.

    Returns:
        DownloadResult indicating outcome (downloaded/skipped/failed).
        History is NOT written here — caller inspects result and writes.
    """
    output_dir = plan.audio_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    format_strategy = plan.format_strategy
    progress = reporter.update
    cancel_event = reporter.cancel_event
    transport = session._client._transport

    # --- m4b_mp3_fallback: try M4B first, fall back to MP3 ---
    if format_strategy == "m4b_mp3_fallback":
        # Try M4B first
        try:
            m4b_url = session.fetch_m4b_url(book.isbn)
            result_path = download_m4b(m4b_url, plan.audio_path, transport=transport, progress=progress, cancel_event=cancel_event)
            if plan.cover_path is not None or plan.pdf_path is not None:
                download_accompanying_files(book, plan, client=session, transport=transport)
            return DownloadResult(status="downloaded", path=result_path, format="m4b")
        except M4BUnavailableError:
            logger.info("M4B not available for %s (%s), falling back to MP3", book.title, book.isbn)

        # Fall back to MP3
        result_path = _download_mp3(book, session, output_dir, transport=transport, progress=progress, cancel_event=cancel_event)
        if result_path and (plan.cover_path is not None or plan.pdf_path is not None):
            download_accompanying_files(book, plan, client=session, transport=transport)
        if result_path:
            return DownloadResult(status="downloaded", path=result_path, format="mp3")
        return DownloadResult(status="skipped")

    # --- mp3_only: skip M4B entirely ---
    if format_strategy == "mp3_only":
        result_path = _download_mp3(book, session, output_dir, transport=transport, progress=progress, cancel_event=cancel_event)
        if result_path and (plan.cover_path is not None or plan.pdf_path is not None):
            download_accompanying_files(book, plan, client=session, transport=transport)
        if result_path:
            return DownloadResult(status="downloaded", path=result_path, format="mp3")
        return DownloadResult(status="skipped")

    # --- m4b_only: skip book if M4B unavailable ---
    if format_strategy == "m4b_only":
        try:
            m4b_url = session.fetch_m4b_url(book.isbn)
            result_path = download_m4b(m4b_url, plan.audio_path, transport=transport, progress=progress, cancel_event=cancel_event)
            if plan.cover_path is not None or plan.pdf_path is not None:
                download_accompanying_files(book, plan, client=session, transport=transport)
            return DownloadResult(status="downloaded", path=result_path, format="m4b")
        except M4BUnavailableError:
            logger.info("Skipping %s (%s): no M4B available (m4b_only mode)", book.title, book.isbn)
            return DownloadResult(status="skipped")

    raise ValueError(f"Unknown format strategy: {format_strategy}")


def _download_mp3(
    book: Book,
    client: "LibroFmSession",
    output_dir: Path,
    transport: httpx.BaseTransport | None = None,
    progress: "Callable[[int], None] | None" = None,
    cancel_event: threading.Event | None = None,
) -> Path | None:
    """Fetch MP3 manifest and download all ZIP parts."""
    try:
        manifest = client.fetch_download_manifest(book.isbn)
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
        extracted = download_zip_part(part_url, output_dir, transport=transport, progress=progress, cancel_event=cancel_event)
        all_extracted.extend(extracted)

    # Return output directory as representative path
    if all_extracted:
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
    expected_path: Path | None = None,
    transport: httpx.BaseTransport | None = None,
) -> Path | None:
    """Download a cover art file via streaming .partial → atomic rename.

    Sends the same User-Agent/AppVer headers as the main client so the
    Libro.fm CDN accepts the request.

    Returns Path on success, None on failure (logs warning).
    """
    from librofm_downloader.session import LibroFmSession

    if expected_path is not None:
        output_path = expected_path
    else:
        filename = _cover_filename_from_url(url)
        output_path = output_dir / filename

    # Normalize protocol-relative URLs (//covers.libro.fm/... → https://covers.libro.fm/...)
    if url.startswith("//"):
        url = "https:" + url
    partial_path = output_path.with_suffix(output_path.suffix + ".partial")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        client = httpx.Client(
            transport=transport,
            follow_redirects=True,
            headers=LibroFmSession.DEFAULT_HEADERS,
        )
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
    expected_path: Path | None = None,
    transport: httpx.BaseTransport | None = None,
) -> Path | None:
    """Download a PDF extra file via streaming .partial → atomic rename.

    Returns Path on success, None on failure (logs warning).
    """
    if expected_path is not None:
        output_path = expected_path
    else:
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
    plan: "OutputPlan",
    client: "LibroFmSession | None" = None,
    transport: httpx.BaseTransport | None = None,
    progress: "Callable[[int], None] | None" = None,
) -> list[Path]:
    """Download PDF extras and/or cover art for a book.

    Non-critical: failures log warnings but do not raise.

    Args:
        book: The book metadata.
        plan: OutputPlan with resolved paths (None when disabled).
        client: Optional LibroFmSession for fetching PDF URLs.
        transport: Optional httpx transport override for testing.

    Returns:
        List of Paths successfully downloaded.
    """
    from librofm_downloader.session import LibroFmSession

    output_dir = plan.audio_path.parent
    downloaded: list[Path] = []

    # Download cover art when path is resolved (means covers enabled + URL present)
    if plan.cover_path is not None:
        result = _download_cover(book.cover_url, output_dir, expected_path=plan.cover_path, transport=transport)
        if result:
            downloaded.append(result)

    # Download PDF extras when path is resolved (means extras enabled + available)
    if plan.pdf_path is not None:
        try:
            pdf_url = client.fetch_pdf_extra_url(book.isbn, "map.pdf")
            if pdf_url:
                result = _download_pdf(pdf_url, "map.pdf", output_dir, expected_path=plan.pdf_path, transport=transport)
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
