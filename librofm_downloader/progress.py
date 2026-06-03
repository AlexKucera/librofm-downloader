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

    def summary(self, downloaded: int, skipped: int, failed: int) -> None:
        """Print summary line."""
        self._print(f"\nSummary: {downloaded} downloaded, {skipped} skipped, {failed} failed")

    def _print(self, message: str) -> None:
        self._out.write(message + "\n")
        self._out.flush()


class ProgressReporter:
    """Rich Progress-based reporter for TTY (interactive) output."""

    def __init__(self, stdout: TextIO | None = None) -> None:
        from rich.console import Console

        self._console = Console(file=stdout or sys.stdout)
        self._progress = None  # Lazy init on first download

    def start_download(self, book, total_bytes: int = 0) -> None:
        """Start a progress bar for this book's download."""
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

        # Store task_id on self for update() to find it
        # In practice we'd track per-book; for now store as current
        self._current_task = task_id
        self._current_book = book
        self._start_time = time.monotonic()

    def update(self, completed: int, *, total: int | None = None) -> None:
        """Update progress bar with bytes completed.

        If *total* is provided (e.g. from a Content-Length header), also
        updates the task's total so that percentage and ETA can be computed.
        """
        if self._progress and hasattr(self, "_current_task"):
            kwargs: dict = {"completed": completed}
            if total is not None:
                kwargs["total"] = total
            self._progress.update(self._current_task, **kwargs)

    def complete(self, book) -> None:
        """Mark current progress bar as complete."""
        if self._progress and hasattr(self, "_current_task"):
            self._progress.update(self._current_task, completed=self._progress.tasks[self._current_task].total or 0)
            self._console.print(f"  [green]✓[/green] {book.title}")
            self._current_task = None

    def fail(self, book, reason: str = "") -> None:
        """Mark current progress bar as failed."""
        if self._progress and hasattr(self, "_current_task"):
            self._progress.stop_task(self._current_task)
            detail = f" ({reason})" if reason else ""
            self._console.print(f"  [red]✗[/red] {book.title}[dim] [{book.isbn}]{detail}[/dim]")
            self._current_task = None

    def summary(self, downloaded: int, skipped: int, failed: int) -> None:
        """Print summary line and stop progress."""
        if self._progress:
            self._progress.stop()
        self._console.print(f"\n[bold]Summary:[/bold] {downloaded} downloaded, {skipped} skipped, {failed} failed")


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
