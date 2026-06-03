"""User-facing output polish — Issue #8.

TTY-aware download reporting:
- TTY (interactive): rich.Progress bars with %, speed, ETA, size
- Non-TTY (cron/pipe): plain log lines

All output goes through DownloadReporter so cli.py stays clean.
"""

from __future__ import annotations

import sys
import time
from typing import IO, TextIO


class PlainTextReporter:
    """Plain-text log lines for non-TTY output (cron, piped)."""

    def __init__(self, stdout: TextIO | None = None) -> None:
        self._out: TextIO = stdout or sys.stdout

    def start_download(self, book, total_bytes: int = 0) -> None:
        """Log download start with author, title, and file size."""
        authors = ", ".join(book.authors) if book.authors else "Unknown"
        size_str = _fmt_size(total_bytes)
        self._print(f"Downloading: {authors} - {book.title} ({size_str})")

    def complete(self, book) -> None:
        """Log successful completion."""
        authors = ", ".join(book.authors) if book.authors else "Unknown"
        self._print(f"Completed: {authors} - {book.title}")

    def fail(self, book, reason: str = "") -> None:
        """Log failure with ISBN, title, and error reason."""
        authors = ", ".join(book.authors) if book.authors else "Unknown"
        detail = f" ({reason})" if reason else ""
        self._print(f"Failed: {authors} - {book.title} [{book.isbn}]{detail}")

    def update(self, completed: int, *, total: int | None = None) -> None:
        """No-op progress update — plain text mode has no progress bar."""

    def summary(
        self,
        downloaded: int,
        skipped: int,
        failed: int,
        *,
        failed_books: list[tuple] | None = None,
        skipped_books: list | None = None,
    ) -> None:
        """Print summary line with optional per-book details.

        Args:
            downloaded: Count of successfully downloaded books.
            skipped: Count of skipped books.
            failed: Count of failed books.
            failed_books: List of (book, reason) tuples for each failure.
            skipped_books: List of Book objects that were skipped.
        """
        self._print(f"\nSummary: {downloaded} downloaded, {skipped} skipped, {failed} failed")

        if failed_books:
            self._print("  Failed:")
            for book, reason in failed_books:
                authors = ", ".join(book.authors) if book.authors else "Unknown"
                self._print(f"    ✗ {authors} - {book.title} [{book.isbn}] ({reason})")

        if skipped_books:
            self._print("  Skipped:")
            for book in skipped_books:
                authors = ", ".join(book.authors) if book.authors else "Unknown"
                self._print(f"    ⏭ {authors} - {book.title} [{book.isbn}]")

    def _print(self, message: str) -> None:
        self._out.write(message + "\n")
        self._out.flush()


class ProgressReporter:
    """Rich Progress-based reporter for TTY (interactive) output."""

    def __init__(self, stdout: TextIO | None = None) -> None:
        from rich.console import Console

        self._console = Console(file=stdout or sys.stdout)
        self._progress = None  # Lazy init on first download
        # Per-book identity mapping for concurrent downloads
        self._tasks: dict[int, object] = {}  # task_id -> book
        self._book_ids: dict[int, int] = {}  # id(book) -> task_id

    def start_download(self, book, total_bytes: int = 0) -> int:
        """Start a progress bar for this book's download.

        Returns:
            The Rich task ID for this book's progress bar.
        """
        from rich.progress import (
            BarColumn,
            DownloadColumn,
            Progress,
            TimeRemainingColumn,
            TransferSpeedColumn,
        )

        if self._progress is None:
            self._progress = Progress(
                "[progress.description]{task.description}",
                BarColumn(),
                "[progress.percentage]{task.percentage:>3.1f}%",
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                DownloadColumn(),
                console=self._console,
            )
            self._progress.start()

        authors = ", ".join(book.authors) if book.authors else "Unknown"
        description = f"{authors} - {book.title}"
        task_id = self._progress.add_task(description, total=total_bytes or None)

        # Store bidirectional mapping for per-book lookup
        self._tasks[task_id] = book
        self._book_ids[id(book)] = task_id

        return task_id

    def update(self, completed: int, *, total: int | None = None, task_id: int | None = None) -> None:
        """Update progress bar with bytes completed.

        If *total* is provided (e.g. from a Content-Length header), also
        updates the task's total so that percentage and ETA can be computed.

        Args:
            completed: Bytes downloaded so far.
            total: Optional total bytes (from Content-Length).
            task_id: Specific task to update. Falls back to most recent if omitted.
        """
        if not self._progress:
            return
        if task_id is None:
            # Backward compat: use the most recently started task
            task_id = next(reversed(self._tasks), None)
        if task_id is None or task_id not in self._tasks:
            return
        kwargs: dict = {"completed": completed}
        if total is not None:
            kwargs["total"] = total
        self._progress.update(task_id, **kwargs)

    def complete(self, book) -> None:
        """Mark this book's progress bar as complete and remove it."""
        task_id = self._book_ids.pop(id(book), None)
        if task_id is None or not self._progress:
            return
        self._tasks.pop(task_id, None)
        self._progress.update(task_id, completed=self._progress.tasks[task_id].total or 0)
        self._console.print(f"  [green]✓[/green] {book.title}")

    def fail(self, book, reason: str = "") -> None:
        """Mark this book's progress bar as failed and remove it."""
        task_id = self._book_ids.pop(id(book), None)
        if task_id is None or not self._progress:
            return
        self._tasks.pop(task_id, None)
        self._progress.stop_task(task_id)
        detail = f" ({reason})" if reason else ""
        self._console.print(f"  [red]✗[/red] {book.title}[dim] [{book.isbn}]{detail}[/dim]")

    def summary(
        self,
        downloaded: int,
        skipped: int,
        failed: int,
        *,
        failed_books: list[tuple] | None = None,
        skipped_books: list | None = None,
    ) -> None:
        """Print summary line with optional per-book details and stop progress."""
        if self._progress:
            self._progress.stop()
        self._console.print(f"\n[bold]Summary:[/bold] {downloaded} downloaded, {skipped} skipped, {failed} failed")

        if failed_books:
            self._console.print("  [red]Failed:[/red]")
            for book, reason in failed_books:
                authors = ", ".join(book.authors) if book.authors else "Unknown"
                self._console.print(f"    ✗ {authors} - {book.title} [{book.isbn}] ({reason})")

        if skipped_books:
            self._console.print("  [yellow]Skipped:[/yellow]")
            for book in skipped_books:
                authors = ", ".join(book.authors) if book.authors else "Unknown"
                self._console.print(f"    ⏭ {authors} - {book.title} [{book.isbn}]")


def _fmt_size(bytes_val: int) -> str:
    """Format byte count as human-readable size string."""
    if bytes_val <= 0:
        return "unknown size"
    for unit in ("B", "KB", "MB", "GB"):
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}" if unit != "B" else f"{bytes_val} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"


def DownloadReporter(stdout=None):
    """Factory: returns appropriate reporter based on TTY detection.

    Args:
        stdout: File-like object to check for TTY and write to.
                Defaults to sys.stdout.

    Returns:
        ProgressReporter if stdout is a TTY, else PlainTextReporter.
    """
    if stdout is None:
        stdout = sys.stdout

    if getattr(stdout, "isatty", lambda: False)():
        return ProgressReporter(stdout=stdout)
    return PlainTextReporter(stdout=stdout)
