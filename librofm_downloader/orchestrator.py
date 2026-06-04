"""Parallel download orchestration — Issue #16.

Encapsulates the ThreadPoolExecutor lifecycle for concurrent book downloads.
Replaces the sequential for-loop in cli.py with a thread-pool-based model.

All coordination logic lives here; cli.py stays a thin wiring layer.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

from rich.console import Console

from librofm_downloader.book import Book, from_library_row


def _hard_exit(code: int) -> None:
    """Exit immediately without Python thread-pool cleanup.

    ThreadPoolExecutor workers may be blocked in HTTP reads and cannot be
    killed from Python. `sys.exit()` runs interpreter shutdown hooks that join
    those workers, causing Ctrl+C tracebacks. For user interrupts, flush output
    then bypass cleanup.
    """
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        os._exit(code)
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
    interrupted: bool = False




def _download_one(
    book: Book,
    download_fn: Callable[[Book], Any],
    reporter: Any,
    cancel_event: threading.Event | None = None,
) -> tuple[Book, Any, str | None, bool]:
    """Execute one book's download pipeline and return (book, result, error, was_skipped).

    Returns:
        - result: the return value of download_fn (Path or None)
        - error: exception string if download_fn raised, else None
        - was_skipped: True if download_fn returned None (skipped)
    """
    task_id = reporter.start_download(book)

    # Create a per-book progress callback bound to this book's task_id.
    # Without this, reporter.update() falls back to the most-recently-started
    # bar (see ProgressReporter.update), so all parallel downloads would
    # update the same progress bar.
    def _progress(completed: int, *, total: int | None = None) -> None:
        reporter.update(completed, total=total, task_id=task_id)

    try:
        result = download_fn(book, progress=_progress)
        if result is None:
            # Skipped (no format available)
            reporter.complete(book)  # still "complete" the progress tracking
            return book, None, None, True
        reporter.complete(book)
        return book, result, None, False
    except BaseException as exc:
        reporter.fail(book, reason=str(exc))
        return book, None, str(exc), False


def download_all_books(
    raw_books: list[dict],
    *,
    workers: int,
    download_fn: Callable[[Book], Any],
    reporter: Any,
    cancel_event: threading.Event | None = None,
    hard_exit: Callable[[int], Any] = _hard_exit,
) -> OrchestratorResult:
    """Run downloads for all books using a thread pool.

    Args:
        raw_books: List of raw Libro.fm API book dicts.
        workers: Number of parallel worker threads.
        download_fn: Callable accepting a Book, returning Path (success) or None (skipped).
        reporter: Reporter instance with start_download/complete/fail/summary methods.

    Returns:
        OrchestratorResult with counts and per-book details, stable-sorted by original index.

    Raises:
        KeyboardInterrupt: Re-raised after draining in-flight downloads on Ctrl+C.
    """
    if not raw_books:
        return OrchestratorResult()

    # Convert raw dicts to Book objects, preserving order and index
    books_with_index: list[tuple[int, Book]] = [
        (i, from_library_row(raw)) for i, raw in enumerate(raw_books)
    ]

    downloaded_count = 0
    skipped_count = 0
    failed_count = 0
    failed_books: list[tuple[int, Book, str]] = []  # (original_index, book, reason)
    skipped_books: list[tuple[int, Book]] = []  # (original_index, book)


    executor = ThreadPoolExecutor(max_workers=workers)
    executor_shutdown = False
    processed_futures: set[Any] = set()
    try:
        futures = {
            executor.submit(_download_one, book, download_fn, reporter, cancel_event): idx
            for idx, book in books_with_index
        }

        try:
            for future in as_completed(futures):
                original_idx = futures[future]
                book, result, error, was_skipped = future.result()
                processed_futures.add(future)

                if error:
                    failed_count += 1
                    failed_books.append((original_idx, book, error))
                elif was_skipped:
                    skipped_count += 1
                    skipped_books.append((original_idx, book))
                else:
                    downloaded_count += 1
        except KeyboardInterrupt:
            # --- Cooperative cancellation ---
            # 1. Signal download loops to check between chunks and exit
            if cancel_event is not None:
                cancel_event.set()

            # 2. Stop progress display BEFORE printing (prevents Rich corruption)
            reporter.stop()

            Console().print("\n[yellow]Aborting...[/yellow] (cancelling downloads)")

            # 3. Cancel all pending futures (ones not yet started by workers)
            for f in futures:
                f.cancel()

            # 4. Wait briefly for running tasks to notice cancel_event.
            #    Each download loop checks between 8 MB chunks, so worst case
            #    is ~1-2 seconds per task at slow connection speeds.
            try:
                deadline = time.monotonic() + 2.0
                for f in list(futures):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        f.result(timeout=min(remaining, 0.5))
                    except Exception:
                        pass  # cancelled/failed/interrupted — collect below
            except KeyboardInterrupt:
                # Double Ctrl+C → user wants out NOW. Do not rely on Python
                # shutdown; worker threads may be blocked in HTTP reads.
                Console().print("\n[red]Force quit — partial downloads may be incomplete.[/red]")
                executor.shutdown(wait=False, cancel_futures=True)
                executor_shutdown = True
                hard_exit(130)

            # Do not wait for running worker threads here. A worker may be
            # blocked in network I/O and Python cannot kill it. Mark every
            # unfinished future as aborted, return a partial result, and let
            # the CLI hard-exit after printing the summary.

            # 5. Collect whatever results we have and mark unfinished work aborted.
            for future in list(futures):
                if future in processed_futures:
                    continue
                idx = futures.get(future)
                if idx is None:
                    continue
                book = books_with_index[idx][1]

                if not future.done():
                    failed_count += 1
                    failed_books.append((idx, book, "Download cancelled by user"))
                    continue

                try:
                    _, result, error, was_skipped = future.result()
                    if error:
                        failed_count += 1
                        failed_books.append((idx, book, error or "Download cancelled by user"))
                    elif was_skipped:
                        skipped_count += 1
                        skipped_books.append((idx, book))
                    else:
                        downloaded_count += 1
                except Exception as exc:
                    failed_count += 1
                    failed_books.append((idx, book, "cancelled" if isinstance(exc, CancelledError) else (str(exc) or "Download cancelled by user")))

            # 6. Return partial result (no re-raise — CLI will hard-exit)
            executor.shutdown(wait=False, cancel_futures=True)
            executor_shutdown = True
            failed_books.sort(key=lambda x: x[0])
            skipped_books.sort(key=lambda x: x[0])
            return OrchestratorResult(
                downloaded_count=downloaded_count,
                skipped_count=skipped_count,
                failed_count=failed_count,
                failed_books=[(b, r) for (_, b, r) in failed_books],
                skipped_books=[b for (_, b) in skipped_books],
                interrupted=True,
            )
    finally:
        if not executor_shutdown:
            try:
                executor.shutdown(wait=True, cancel_futures=True)
            except KeyboardInterrupt:
                Console().print("\n[red]Force quit — partial downloads may be incomplete.[/red]")
                hard_exit(130)

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
