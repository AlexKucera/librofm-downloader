"""Download history — track which ISBNs have been downloaded."""

import json
import logging
import threading
from dataclasses import dataclass, asdict
from pathlib import Path

from librofm_downloader.book import Book  # noqa: F401 — used in _write_history() type hints

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HistoryEntry:
    """A single download history record."""

    isbn: str
    title: str
    format: str
    path: str
    downloaded_at: str


class DownloadHistory:
    """Read/write download_history.json — ISBN → entry mapping."""

    def __init__(self, path: Path | str):
        self._path = Path(path)
        self._data: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        """Load existing history from disk. Missing/corrupt → empty with warning."""
        if not self._path.exists():
            return

        try:
            text = self._path.read_text(encoding="utf-8")
            self._data = json.loads(text) if text.strip() else {}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Corrupt history file %s: %s. Starting with empty history.", self._path, exc)
            self._data = {}

    def find(self, isbn: str) -> HistoryEntry | None:
        """Look up a history entry by ISBN. Returns None if not found."""
        entry_dict = self._data.get(str(isbn))
        if entry_dict is None:
            return None
        return HistoryEntry(**entry_dict)

    def is_downloaded(self, isbn: str) -> bool:
        """Check whether an ISBN was previously downloaded."""
        return str(isbn) in self._data

    def write(self, entry: HistoryEntry) -> None:
        """Persist a history entry to disk. Thread-safe."""
        with self._lock:
            self._data[entry.isbn] = asdict(entry)
            self._flush()

    def _flush(self) -> None:
        """Write current in-memory state to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _write_history(
    history: "DownloadHistory",
    book: "Book",
    fmt: str,
    path: str,
) -> None:
    """Write a download history entry.

    Relocated from downloader.py (Issue #40) — this is a persistence
    helper that belongs with the history module, not the download engine.
    """
    from datetime import datetime, timezone

    entry = HistoryEntry(
        isbn=book.isbn,
        title=book.title,
        format=fmt,
        path=path,
        downloaded_at=datetime.now(timezone.utc).isoformat(),
    )
    history.write(entry)