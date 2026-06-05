"""Tests for librofm_downloader.cli — argparse + exit code translation only."""

from unittest.mock import patch

import pytest

from librofm_downloader.cli import run, main


class TestCLIExitCodeTranslation:
    """run() correctly maps SyncRunResult fields to exit codes."""

    def test_success_returns_zero(self):
        """Successful sync (no errors, no interrupt) → exit 0."""
        with patch("librofm_downloader.cli.sync_run") as mock_sr:
            from librofm_downloader.sync_run import SyncRunResult
            mock_sr.return_value = SyncRunResult(downloaded_count=2)
            assert run() == 0

    def test_fatal_error_returns_one(self):
        """Fatal error (auth failure, config error, etc.) → exit 1."""
        with patch("librofm_downloader.cli.sync_run") as mock_sr:
            from librofm_downloader.sync_run import SyncRunResult
            mock_sr.return_value = SyncRunResult(fatal_error="Auth failed")
            assert run() == 1

    def test_interrupted_returns_130(self):
        """Ctrl+C interrupt → exit 130."""
        with patch("librofm_downloader.cli.sync_run") as mock_sr:
            from librofm_downloader.sync_run import SyncRunResult
            mock_sr.return_value = SyncRunResult(interrupted=True)
            assert run() == 130

    def test_all_books_fail_still_returns_zero(self):
        """All downloads failed but no fatal error → exit 0 (not an error exit)."""
        with patch("librofm_downloader.cli.sync_run") as mock_sr:
            from librofm_downloader.sync_run import SyncRunResult
            mock_sr.return_value = SyncRunResult(failed_count=3)
            assert run() == 0

    def test_interrupted_takes_priority_over_fatal_error(self):
        """If both interrupted and fatal_error, interrupted wins (exit 130)."""
        with patch("librofm_downloader.cli.sync_run") as mock_sr:
            from librofm_downloader.sync_run import SyncRunResult
            mock_sr.return_value = SyncRunResult(interrupted=True, fatal_error="something")
            assert run() == 130


class TestCLIArgparse:
    """main() parses CLI flags and passes them to run()."""

    def test_default_args(self, monkeypatch):
        """No flags → all defaults (None/False/0)."""
        monkeypatch.setattr("sys.argv", ["prog"])
        with patch("librofm_downloader.cli.run") as mock_run:
            mock_run.return_value = 0
            with pytest.raises(SystemExit):
                main()
            _, kwargs = mock_run.call_args
            assert kwargs["config_path"] is None
            assert kwargs["secrets_path"] is None
            assert kwargs["history_path"] is None
            assert kwargs["verbose"] is False
            assert kwargs["limit"] == 0
            assert kwargs["workers"] == 0
            assert kwargs["select_mode"] is False

    def test_verbose_flag(self, monkeypatch):
        """-v sets verbose=True."""
        monkeypatch.setattr("sys.argv", ["prog", "-v"])
        with patch("librofm_downloader.cli.run") as mock_run:
            mock_run.return_value = 0
            with pytest.raises(SystemExit):
                main()
            _, kwargs = mock_run.call_args
            assert kwargs["verbose"] is True

    def test_limit_flag(self, monkeypatch):
        """--limit N passes N through."""
        monkeypatch.setattr("sys.argv", ["prog", "--limit", "5"])
        with patch("librofm_downloader.cli.run") as mock_run:
            mock_run.return_value = 0
            with pytest.raises(SystemExit):
                main()
            _, kwargs = mock_run.call_args
            assert kwargs["limit"] == 5

    def test_workers_flag(self, monkeypatch):
        """-w N passes N through."""
        monkeypatch.setattr("sys.argv", ["prog", "-w", "8"])
        with patch("librofm_downloader.cli.run") as mock_run:
            mock_run.return_value = 0
            with pytest.raises(SystemExit):
                main()
            _, kwargs = mock_run.call_args
            assert kwargs["workers"] == 8

    def test_select_flag(self, monkeypatch):
        """--select passes select_mode=True."""
        monkeypatch.setattr("sys.argv", ["prog", "--select"])
        with patch("librofm_downloader.cli.run") as mock_run:
            mock_run.return_value = 0
            with pytest.raises(SystemExit):
                main()
            _, kwargs = mock_run.call_args
            assert kwargs["select_mode"] is True

    def test_rename_chapters_flag_default(self, monkeypatch):
        """No --rename-chapters → rename_chapters defaults to False."""
        monkeypatch.setattr("sys.argv", ["prog"])
        with patch("librofm_downloader.cli.run") as mock_run:
            mock_run.return_value = 0
            with pytest.raises(SystemExit):
                main()
            _, kwargs = mock_run.call_args
            assert "rename_chapters" in kwargs

    def test_rename_chapters_flag(self, monkeypatch):
        """--rename-chapters sets rename_chapters=True."""
        monkeypatch.setattr("sys.argv", ["prog", "--rename-chapters"])
        with patch("librofm_downloader.cli.run") as mock_run:
            mock_run.return_value = 0
            with pytest.raises(SystemExit):
                main()
            _, kwargs = mock_run.call_args
            assert kwargs.get("rename_chapters") is True
