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
