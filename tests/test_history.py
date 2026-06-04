"""Tests for librofm_downloader.history — TDD vertical slices."""

import json
import tempfile
from pathlib import Path

import pytest

from librofm_downloader.history import DownloadHistory, HistoryEntry


class TestWriteAndRead:
    """Tracer bullet: write an entry and read it back by ISBN."""

    def test_write_and_read_entry_by_isbn(self):
        """After writing an entry, looking it up by ISBN returns it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "download_history.json"
            history = DownloadHistory(history_path)

            entry = HistoryEntry(
                isbn="9781234567890",
                title="Test Book",
                format="m4b",
                path="/audiobooks/Author/Test Book/Test Book.m4b",
                downloaded_at="2025-01-01T12:00:00Z",
            )
            history.write(entry)

            result = history.find("9781234567890")

            assert result is not None
            assert result.title == "Test Book"
            assert result.format == "m4b"


class TestIsDownloaded:
    """is_downloaded() returns bool for previously downloaded ISBNs."""

    def test_returns_true_for_downloaded_isbn(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = DownloadHistory(Path(tmpdir) / "history.json")
            entry = HistoryEntry(
                isbn="978111", title="Book", format="m4b",
                path="/book.m4b", downloaded_at="2025-01-01T00:00:00Z",
            )
            history.write(entry)

            assert history.is_downloaded("978111") is True

    def test_returns_false_for_unknown_isbn(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = DownloadHistory(Path(tmpdir) / "history.json")

            assert history.is_downloaded("978999") is False


class TestFileCreation:
    """History file is created on disk when it doesn't exist."""

    def test_file_created_after_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "subdir" / "download_history.json"
            history = DownloadHistory(history_path)
            entry = HistoryEntry(
                isbn="978111", title="Book", format="m4b",
                path="/book.m4b", downloaded_at="2025-01-01T00:00:00Z",
            )
            history.write(entry)

            assert history_path.exists()
            data = json.loads(history_path.read_text())
            assert "978111" in data


class TestCorruptRecovery:
    """Corrupt or missing JSON → empty history with warning."""

    def test_corrupt_json_treated_as_empty(self, caplog):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "corrupt.json"
            history_path.write_text("{this is not valid json!!!")

            history = DownloadHistory(history_path)

            assert history.is_downloaded("978111") is False
            assert history.find("978111") is None
            assert "Corrupt" in caplog.text

    def test_missing_file_treated_as_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = DownloadHistory(Path(tmpdir) / "no_such_file.json")

            assert history.is_downloaded("978111") is False

    def test_empty_file_treated_as_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "empty.json"
            history_path.write_text("")

            history = DownloadHistory(history_path)

            assert history.is_downloaded("978111") is False


class TestThreadSafety:
    """Issue #13: DownloadHistory.write() is safe for concurrent callers."""

    def test_has_lock_attribute(self):
        """DownloadHistory initialises a _lock threading.Lock."""
        import threading

        with tempfile.TemporaryDirectory() as tmpdir:
            history = DownloadHistory(Path(tmpdir) / "history.json")

            assert hasattr(history, "_lock")
            assert isinstance(history._lock, type(threading.Lock()))

    def test_write_acquires_lock(self):
        """write() acquires _lock during execution and releases it after."""
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            history = DownloadHistory(Path(tmpdir) / "history.json")
            entry = HistoryEntry(
                isbn="978000",
                title="Test Book",
                format="m4b",
                path=str(Path(tmpdir) / "book.m4b"),
                downloaded_at="2026-06-03T00:00:00Z",
            )

            lock_held_during_write = []

            original_flush = history._flush

            def slow_flush():
                lock_held_during_write.append(history._lock.locked())
                time.sleep(0.05)
                original_flush()

            history._flush = slow_flush

            assert history._lock.locked() is False
            history.write(entry)
            assert history._lock.locked() is False  # released after
            assert lock_held_during_write == [True], "Lock must be held during _flush"

    def test_concurrent_writes_no_lost_entries(self):
        """Multiple threads calling write() simultaneously don't lose entries."""
        import threading

        with tempfile.TemporaryDirectory() as tmpdir:
            history = DownloadHistory(Path(tmpdir) / "history.json")

            num_threads = 20
            entries = [
                HistoryEntry(
                    isbn=f"978{i:03d}",
                    title=f"Book {i}",
                    format="m4b",
                    path=str(Path(tmpdir) / f"book{i}.m4b"),
                    downloaded_at=f"2026-06-03T{i:02d}:00:00Z",
                )
                for i in range(num_threads)
            ]

            threads = [
                threading.Thread(target=history.write, args=(entries[i],))
                for i in range(num_threads)
            ]

            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

            # All entries must be present — none lost to race conditions
            for i in range(num_threads):
                assert history.is_downloaded(f"978{i:03d}"), f"Entry 978{i:03d} was lost"

    def test_concurrent_writes_produce_valid_json(self):
        """Concurrent writes don't corrupt the on-disk JSON file."""
        import json
        import threading

        with tempfile.TemporaryDirectory() as tmpdir:
            history = DownloadHistory(Path(tmpdir) / "history.json")

            num_threads = 20
            entries = [
                HistoryEntry(
                    isbn=f"999{i:03d}",
                    title=f"Concurrent {i}",
                    format="mp3",
                    path=str(Path(tmpdir) / f"c{i}.mp3"),
                    downloaded_at=f"2026-06-04T{i:02d}:00:00Z",
                )
                for i in range(num_threads)
            ]

            threads = [
                threading.Thread(target=history.write, args=(entries[i],))
                for i in range(num_threads)
            ]

            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

            # On-disk file must be valid JSON
            raw = history._path.read_text()
            data = json.loads(raw)  # raises if corrupted
            assert len(data) == num_threads

    def test_sequential_behavior_unchanged(self):
        """Sequential writes still work exactly as before (regression)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            history = DownloadHistory(Path(tmpdir) / "history.json")

            entry1 = HistoryEntry(
                isbn="111",
                title="First",
                format="m4b",
                path=str(Path(tmpdir) / "first.m4b"),
                downloaded_at="2026-01-01T00:00:00Z",
            )
            entry2 = HistoryEntry(
                isbn="222",
                title="Second",
                format="mp3",
                path=str(Path(tmpdir) / "second.mp3"),
                downloaded_at="2026-02-01T00:00:00Z",
            )

            history.write(entry1)
            history.write(entry2)

            assert history.is_downloaded("111") is True
            assert history.is_downloaded("222") is True
            assert history.is_downloaded("999") is False

            found = history.find("111")
            assert found is not None
            assert found.title == "First"