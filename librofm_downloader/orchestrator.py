"""Parallel download orchestration — Issue #16.

Encapsulates the ThreadPoolExecutor lifecycle for concurrent book downloads.
Replaces the sequential for-loop in cli.py with a thread-pool-based model.

All coordination logic lives here; cli.py stays a thin wiring layer.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

from librofm_downloader.downloader import Book


@dataclass(frozen=True)
class OrchestratorResult:
    """Structured result from a parallel download batch.

    Attributes:
        downloaded_count: Books successfully downloaded.
        skipped_count: Books skipped (download_fn returned None).
        failed_count: Books that raised an exception.
        failed_books: List of (book, reason_string) tuples in original order.
        skipped_books: List of Book objects that were skipped, in original order.
    """

    downloaded_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    failed_books: list[tuple[Book, str]] = field(default_factory=list)
    skipped_books: list[Book] = field(default_factory=list)


def _raw_to_book(raw: dict) -> Book:
    """Convert a Libro.fm API dict to a Book object.

    Mirrors the Book-building logic previously in cli.py's download loop.
    """
    audiobook_info = raw.get("audiobook_info", {}) or {}
    narrators = audiobook_info.get("narrators", []) or raw.get("narrators", [])

    return Book(
        title=raw.get("title", "Unknown"),
        authors=raw.get("authors", []),
        narrators=narrators,
        isbn=raw.get("isbn", "?"),
        series=raw.get("series", ""),
        series_num=raw.get("series_num"),
        cover_url=raw.get("cover_url", ""),
        pdf_extras=bool(audiobook_info.get("pdf_extras")) if audiobook_info else False,
        publication_year=raw.get("publication_year"),
        publication_month=raw.get("publication_month"),
        publication_day=raw.get("publication_day"),
    )


def _download_one(
    book: Book,
    download_fn: Callable[[Book], Any],
    reporter: Any,
) -> tuple[Book, Any, str | None, bool]:
    """Execute one book's download pipeline and return (book, result, error, was_skipped).

    Returns:
        - result: the return value of download_fn (Path or None)
        - error: exception string if download_fn raised, else None
        - was_skipped: True if download_fn returned None (skipped)
    """
    reporter.start_download(book)
    try:
        result = download_fn(book)
        if result is None:
            # Skipped (no format available)
            reporter.complete(book)  # still "complete" the progress tracking
            return book, None, None, True
        reporter.complete(book)
        return book, result, None, False
    except Exception as exc:
        reporter.fail(book, reason=str(exc))
        return book, None, str(exc), False


def download_all_books(
    raw_books: list[dict],
    *,
    workers: int,
    download_fn: Callable[[Book], Any],
    reporter: Any,
) -> OrchestratorResult:
    """Run downloads for all books using a thread pool.

    Args:
        raw_books: List of raw Libro.fm API book dicts.
        workers: Number of parallel worker threads.
        download_fn: Callable accepting a Book, returning Path (success) or None (skipped).
        reporter: Reporter instance with start_download/complete/fail/summary methods.

    Returns:
        OrchestratorResult with counts and per-book details, stable-sorted by original index.
    """
    if not raw_books:
        return OrchestratorResult()

    # Convert raw dicts to Book objects, preserving order and index
    books_with_index: list[tuple[int, Book]] = [
        (i, _raw_to_book(raw)) for i, raw in enumerate(raw_books)
    ]

    downloaded_count = 0
    skipped_count = 0
    failed_count = 0
    failed_books: list[tuple[int, Book, str]] = []  # (original_index, book, reason)
    skipped_books: list[tuple[int, Book]] = []  # (original_index, book)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_download_one, book, download_fn, reporter): idx
            for idx, book in books_with_index
        }

        for future in as_completed(futures):
            original_idx = futures[future]
            book, result, error, was_skipped = future.result()

            if error:
                failed_count += 1
                failed_books.append((original_idx, book, error))
            elif was_skipped:
                skipped_count += 1
                skipped_books.append((original_idx, book))
            else:
                downloaded_count += 1

    # Stable sort by original index to preserve library order
    failed_books.sort(key=lambda x: x[0])
    skipped_books.sort(key=lambda x: x[0])

    return OrchestratorResult(
        downloaded_count=downloaded_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
        failed_books=[(b, r) for (_, b, r) in failed_books],
        skipped_books=[b for (_, b) in skipped_books],
    )
