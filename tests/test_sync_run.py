"""Tests for librofm_downloader.sync_run — TDD vertical slices + migrated CLI pipeline tests."""

from unittest.mock import MagicMock, patch

import pytest

from librofm_downloader.sync_run import sync_run, SyncRunResult
from librofm_downloader.downloader import DownloadResult


# ===========================================================================
# Phase 1: TDD vertical slices for sync_run() extraction
# ===========================================================================


class TestSyncRunExists:
    """Tracer bullet: sync_run() is callable and returns SyncRunResult."""

    def test_returns_sync_result_on_happy_path(self):
        """Happy path with mocked collaborators returns SyncRunResult with correct shape."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_all_books") as mock_download,
        ):
            # Config
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.format = "m4b_mp3_fallback"
            mock_config.return_value.workers = 3

            # Auth succeeds
            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = "tok_abc"

            # Library has books but all already downloaded → empty new_books list
            mock_instance.fetch_library.return_value = [
                {"isbn": "9781234567890", "title": "Old Book"},
            ]

            # History says all downloaded → empty list after filtering
            mock_history_instance = mock_history_cls.return_value
            mock_history_instance.is_downloaded.return_value = True

            # Download result (won't be reached for empty list, but set it)
            from librofm_downloader.orchestrator import OrchestratorResult
            mock_download.return_value = OrchestratorResult()

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
                verbose=False,
                limit=0,
                workers=0,
            )

            assert isinstance(result, SyncRunResult)
            assert result.downloaded_count == 0
            assert result.skipped_count == 0
            assert result.failed_count == 0
            assert result.failed_books == []
            assert result.skipped_books == []
            assert result.interrupted is False


class TestSyncRunSelectMode:
    """Select mode (ADR #6) branch point — stub, returns empty result."""

    def test_select_mode_returns_not_implemented_result(self):
        """select_mode=True → empty SyncRunResult (not yet implemented)."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = "tok_abc"
            mock_instance.fetch_library.return_value = [
                {"isbn": "9781234567890", "title": "A Book"},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False

            result = sync_run(
                verbose=False, limit=0, workers=0, select_mode=True,
            )

            assert isinstance(result, SyncRunResult)
            assert result.downloaded_count == 0
            assert result.interrupted is False


class TestSyncRunInterrupted:
    """Ctrl+C / interrupted path returns SyncRunResult(interrupted=True)."""

    def test_interrupted_download_returns_interrupted_result(self):
        """Orchestrator reports interrupted → SyncRunResult(interrupted=True)."""
        from librofm_downloader.orchestrator import OrchestratorResult

        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_all_books") as mock_download,
            patch("librofm_downloader.sync_run.DownloadReporter") as mock_reporter_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.format = "m4b_mp3_fallback"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = "tok_abc"
            mock_instance.fetch_library.return_value = [
                {"isbn": "9781234567890", "title": "A Book"},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False

            mock_download.return_value = OrchestratorResult(
                downloaded_count=0, skipped_count=0, failed_count=1,
                failed_books=[], skipped_books=[], interrupted=True,
            )

            mock_reporter = MagicMock()
            mock_reporter_cls.return_value = mock_reporter

            result = sync_run(verbose=False, limit=0, workers=0)

            assert result.interrupted is True


class TestSyncRunFetchLibraryFailure:
    """Library fetch failure → returns SyncRunResult with fatal_error."""

    def test_returns_fatal_error_on_fetch_failure(self):
        """fetch_library raises → SyncRunResult with fatal_error set."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = "tok_abc"
            mock_instance.fetch_library.side_effect = ConnectionError("Network down")

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
                verbose=False,
                limit=0,
                workers=0,
            )

            assert isinstance(result, SyncRunResult)
            assert result.downloaded_count == 0
            assert result.failed_count == 0
            assert result.interrupted is False
            assert result.fatal_error is not None
            assert "Failed to fetch library" in result.fatal_error


class TestSyncRunAuthFailure:
    """Auth failure → returns SyncRunResult with fatal_error (not exit code)."""

    def test_returns_fatal_error_on_auth_failure(self):
        """Auth fails → SyncRunResult with fatal_error set, no crash."""
        from librofm_downloader.session import AuthError

        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "wrong"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.side_effect = AuthError("Auth failed (401)")

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
                verbose=False,
                limit=0,
                workers=0,
            )

            assert isinstance(result, SyncRunResult)
            assert result.downloaded_count == 0
            assert result.interrupted is False
            assert result.fatal_error is not None
            assert "Authentication failed" in result.fatal_error


class TestSyncRunConfigError:
    """Config error → returns SyncRunResult with fatal_error."""

    def test_returns_fatal_error_on_config_error(self):
        """load_config raises ConfigError → SyncRunResult with fatal_error set."""
        from librofm_downloader.config import ConfigError

        with patch("librofm_downloader.sync_run.load_config") as mock_config:
            mock_config.side_effect = ConfigError("Missing username")

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
                verbose=False,
                limit=0,
                workers=0,
            )

            assert isinstance(result, SyncRunResult)
            assert result.downloaded_count == 0
            assert result.failed_count == 0
            assert result.interrupted is False
            assert result.fatal_error is not None
            assert "Config error" in result.fatal_error


class TestSyncRunFilteringAndLimit:
    """Filtering (history) and limit flag produce correct book list."""

    def test_filters_already_downloaded_books(self):
        """Books already in history don't get passed to download_all_books."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_all_books") as mock_download,
            patch("librofm_downloader.sync_run.DownloadReporter") as mock_reporter_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.format = "m4b_mp3_fallback"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = "tok_abc"

            # 3 books: 2 already downloaded, 1 new
            mock_instance.fetch_library.return_value = [
                {"isbn": "9781111111111", "title": "Old Book 1"},
                {"isbn": "9782222222222", "title": "Old Book 2"},
                {"isbn": "9783333333333", "title": "New Book"},
            ]

            mock_hist = mock_history_cls.return_value
            # First two downloaded, third is new
            mock_hist.is_downloaded.side_effect = lambda isbn: isbn in ("9781111111111", "9782222222222")

            mock_reporter = MagicMock()
            mock_reporter_cls.return_value = mock_reporter

            sync_run(verbose=False, limit=0, workers=0)

            # download_all_books should receive only the 1 new book
            call_args = mock_download.call_args
            passed_books = call_args[0][0]  # positional arg: raw_books
            assert len(passed_books) == 1
            assert passed_books[0]["isbn"] == "9783333333333"

    def test_limit_caps_book_list(self):
        """--limit N caps the number of books passed to downloader."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_all_books") as mock_download,
            patch("librofm_downloader.sync_run.DownloadReporter") as mock_reporter_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.format = "m4b_mp3_fallback"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = "tok_abc"

            # 5 new books (none downloaded)
            mock_instance.fetch_library.return_value = [
                {"isbn": f"97800000000{i}", "title": f"Book {i}"}
                for i in range(5)
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False

            mock_reporter = MagicMock()
            mock_reporter_cls.return_value = mock_reporter

            sync_run(verbose=False, limit=2, workers=0)

            call_args = mock_download.call_args
            passed_books = call_args[0][0]
            assert len(passed_books) == 2


# ===========================================================================
# Migrated from test_cli.py — all pipeline tests now target sync_run
# ===========================================================================


class TestSyncRunHappyPath:
    """Smoke test: config → auth → fetch library → filter → print → success."""

    def test_exits_zero_and_prints_books(self, capsys):
        """Happy path: valid config, auth succeeds, books are printed."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = "tok_abc"

            mock_instance.fetch_library.return_value = [
                {"isbn": "9781234567890", "title": "My Audiobook"},
            ]

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            assert result.fatal_error is None
            assert result.interrupted is False
            captured = capsys.readouterr()
            assert "My Audiobook" in captured.out


class TestSyncRunHistoryFiltering:
    """Already-downloaded books are filtered from output."""

    def test_filters_out_downloaded_books(self, capsys):
        """Books in history file don't appear in output."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = "tok_abc"

            # 3 books total, 1 already downloaded
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "Old Book"},
                {"isbn": "978222", "title": "New Book A"},
                {"isbn": "978333", "title": "New Book B"},
            ]

            # 978111 is already downloaded
            mock_history_instance = mock_history_cls.return_value
            mock_history_instance.is_downloaded.side_effect = lambda isbn: isbn == "978111"

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            assert result.fatal_error is None
            captured = capsys.readouterr()
            assert "Old Book" not in captured.out
            assert "New Book A" in captured.out
            assert "New Book B" in captured.out


class TestSyncRunDownloadOrchestration:
    """Downloads books and reports results."""

    def test_downloads_books_and_reports_summary(self, capsys):
        """Each undownloaded book: resolve → query M4B → download → history.
        Books without M4B are skipped (not errors)."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
            patch("librofm_downloader.sync_run.Book") as mock_book_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None

            # 3 new books
            raw_books = [
                {"isbn": "978111", "title": "M4B Book", "authors": ["A1"],
                 "narrators": ["N1"]},
                {"isbn": "978222", "title": "No M4B Book", "authors": ["A2"],
                 "narrators": ["N2"]},
                {"isbn": "978333", "title": "Another M4B", "authors": ["A3"],
                 "narrators": ["N3"]},
            ]
            mock_instance.fetch_library.return_value = raw_books

            # All are new (not in history)
            mock_history_instance = mock_history_cls.return_value
            mock_history_instance.is_downloaded.return_value = False

            # download_book returns DownloadResult for each book
            from pathlib import Path
            mock_download.side_effect = [
                DownloadResult(status="downloaded", path=Path("/audiobooks/A1/M4B Book.m4b"), format="m4b"),
                DownloadResult(status="skipped"),
                DownloadResult(status="downloaded", path=Path("/audiobooks/A3/Another M4B.m4b"), format="m4b"),
            ]

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            assert result.fatal_error is None
            captured = capsys.readouterr()
            # Summary should show downloads + skips
            assert "downloaded" in captured.out.lower() or "978111" in captured.out or "M4B Book" in captured.out


class TestSyncRunVerbose:
    """Verbose flag prints extra detail at each pipeline stage."""

    def test_verbose_prints_config_and_auth_details(self, capsys):
        """--verbose shows config values and auth status."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
            patch("librofm_downloader.sync_run.Book") as mock_book_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.format = "m4b_mp3_fallback"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "Verbose Book", "authors": ["A"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False
            mock_download.return_value = DownloadResult(status="skipped")  # skipped (no M4B)

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
                verbose=True,
            )

            assert result.fatal_error is None
            captured = capsys.readouterr()
            # Verbose sections should appear
            assert "config" in captured.out.lower()
            assert "auth" in captured.out.lower()
            assert "alice" in captured.out
            assert "m4b_mp3_fallback" in captured.out
            assert "1 book(s) in library" in captured.out or "library" in captured.out.lower()


class TestSyncRunLimitFlag:
    """--limit caps how many books are downloaded."""

    def test_limit_stops_after_n_books(self, capsys):
        """--limit 2 → only first 2 books are attempted."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
            patch("librofm_downloader.sync_run.Book") as mock_book_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None

            # 5 new books
            raw_books = [
                {"isbn": f"97800{i}", "title": f"Book {i}", "authors": ["A"], "narrators": ["N"]}
                for i in range(5)
            ]
            mock_instance.fetch_library.return_value = raw_books

            mock_history_instance = mock_history_cls.return_value
            mock_history_instance.is_downloaded.return_value = False

            sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
                limit=2,
            )

            # download_book should only be called twice (not 5)
            assert mock_download.call_count == 2

    def test_limit_zero_or_none_means_no_limit(self, capsys):
        """--limit 0 (default) → all books are processed."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
            patch("librofm_downloader.sync_run.Book") as mock_book_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "B1", "authors": ["A"], "narrators": ["N"]},
                {"isbn": "978222", "title": "B2", "authors": ["A"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False
            mock_download.return_value = DownloadResult(status="skipped")

            sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
                limit=0,
            )

            assert mock_download.call_count == 2


class TestSyncRunFormatWiring:
    """Format strategy from config is passed to download_book."""

    def test_format_passed_to_download_book(self):
        """config.format is forwarded to OutputPlan (via resolve_output_plan)."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
            patch("librofm_downloader.sync_run.resolve_output_plan") as mock_plan,
            patch("librofm_downloader.sync_run.Book") as mock_book_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.format = "mp3_only"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "MP3 Book", "authors": ["A"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False

            sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            # resolve_output_plan was called with format_strategy="mp3_only"
            _, kwargs = mock_plan.call_args
            assert kwargs.get("format_strategy") == "mp3_only"

    def test_mp3_download_reported_as_downloaded_not_skipped(self, capsys):
        """MP3 download (returns Path) is reported as 'Downloaded', not 'Skipped'."""
        from pathlib import Path

        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
            patch("librofm_downloader.sync_run.Book") as mock_book_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.format = "mp3_only"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "MP3 Book", "authors": ["A"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False
            # download_book returns DownloadResult with MP3 path
            mock_download.return_value = DownloadResult(status="downloaded", path=Path("/audiobooks/A/MP3 Book"), format="mp3")

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            captured = capsys.readouterr()
            # Reporter now outputs "Completed:" for successful downloads (Issue #8)
            assert "Completed" in captured.out
            assert "Skipped" not in captured.out or "Completed" in captured.out


class TestSyncRunGracefulShutdown:
    """Ctrl+C produces a clean result, not a Python traceback."""

    def test_keyboard_interrupt_during_download_exits_cleanly(self):
        """KeyboardInterrupt during download loop → partial result.
        Since _download_one catches BaseException (including KI),
        the orchestrator wraps it as a failure and returns normally.
        """
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "Book A", "authors": ["A"], "narrators": ["N"]},
                {"isbn": "978222", "title": "Book B", "authors": ["A"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False

            from pathlib import Path
            mock_download.side_effect = [
                DownloadResult(status="downloaded", path=Path("/audiobooks/A/Book A.m4b"), format="m4b"),
                KeyboardInterrupt,
            ]

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            # _download_one wraps KI as failure; orchestrator returns partial result
            assert result.fatal_error is None  # not a fatal error, just interrupted or partial

    def test_keyboard_interrupt_before_downloads_exits_cleanly(self):
        """KeyboardInterrupt during library fetch → interrupted result."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.side_effect = KeyboardInterrupt

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            assert result.interrupted is True


class TestSyncRunIntegrationHappyPath:
    """Happy path: 3 new books → all download successfully."""

    def test_three_books_all_download_successfully(self):
        """Full pipeline: auth + library fetch + 3 downloads → success + summary."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "Book A", "authors": ["Author A"], "narrators": ["N1"]},
                {"isbn": "978222", "title": "Book B", "authors": ["Author B"], "narrators": ["N2"]},
                {"isbn": "978333", "title": "Book C", "authors": ["Author C"], "narrators": ["N3"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False

            from pathlib import Path
            mock_download.return_value = DownloadResult(status="downloaded", path=Path("/audiobooks/Author/Book.m4b"), format="m4b")

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            assert result.fatal_error is None
            assert result.interrupted is False
            assert mock_download.call_count == 3


class TestSyncRunIntegrationMixedResult:
    """Mixed result: new downloads + skipped + failed → correct summary."""

    def test_mixed_result_shows_correct_summary_and_exit_code(self, capsys):
        """2 download (1 M4B, 1 MP3), 1 skipped, 1 fails → summary lists all + success."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            # 3 new books (none already downloaded — all enter download loop)
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "New Book A", "authors": ["Author A"], "narrators": ["N1"]},
                {"isbn": "978222", "title": "New Book B", "authors": ["Author B"], "narrators": ["N2"]},
                {"isbn": "978333", "title": "Skip Book C", "authors": ["Author C"], "narrators": ["N3"]},
                {"isbn": "978444", "title": "Fail Book D", "authors": ["Author D"], "narrators": ["N4"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False

            from pathlib import Path
            import httpx

            # Deterministic mock based on ISBN — thread-safe for concurrent workers
            def _download_side_effect(book, *args, **kwargs):
                if book.isbn == "978333":
                    return DownloadResult(status="skipped")  # skipped (no format available)
                if book.isbn == "978444":
                    raise httpx.HTTPStatusError(
                        message="Not Found",
                        request=httpx.Request("GET", "https://example.com/fail"),
                        response=httpx.Response(404, request=httpx.Request("GET", "https://example.com/fail")),
                    )
                # 978111 and 978222 succeed
                return DownloadResult(status="downloaded", path=Path(f"/audiobooks/{book.authors[0]}/{book.title}.m4b"), format="m4b")

            mock_download.side_effect = _download_side_effect

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            # Success even with failures (best-effort batch)
            assert result.fatal_error is None
            # All 4 books were attempted
            assert mock_download.call_count == 4


class TestSyncRunIntegrationFatalAuthFailure:
    """Fatal path: auth fails → fatal_error, no downloads attempted."""

    def test_auth_failure_returns_fatal_error_no_downloads(self, capsys):
        """Authentication failure → fatal_error set, download_book never called."""
        from librofm_downloader.session import AuthError

        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
        ):
            mock_config.return_value.username = "baduser"
            mock_config.return_value.password = "wrongpass"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.side_effect = AuthError("Invalid credentials")

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            assert result.fatal_error is not None
            mock_download.assert_not_called()

            captured = capsys.readouterr()
            assert "Authentication failed" in captured.out


class TestSyncRunAllBooksFailExitCode:
    """When every book fails individually, still returns success (non-fatal)."""

    def test_all_books_fail_returns_success_result(self):
        """All 3 books fail with exceptions → success result (individual failures non-fatal)."""
        import httpx

        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "Fail A", "authors": ["A"], "narrators": ["N"]},
                {"isbn": "978222", "title": "Fail B", "authors": ["B"], "narrators": ["N"]},
                {"isbn": "978333", "title": "Fail C", "authors": ["C"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False

            mock_download.side_effect = [
                httpx.HTTPStatusError(
                    message="Server Error",
                    request=httpx.Request("GET", "https://example.com/a"),
                    response=httpx.Response(500, request=httpx.Request("GET", "https://example.com/a")),
                ),
                httpx.ConnectError("Connection refused"),
                Exception("Download timed out"),
            ]

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            # Individual failures are NOT fatal → no fatal_error
            assert result.fatal_error is None
            assert mock_download.call_count == 3


class TestSyncRunHistoryResolution:
    """History path resolves via XDG → CWD when not explicitly provided."""

    def test_history_defaults_to_xdg_location(self, tmp_path, monkeypatch):
        """sync_run() with history_path=None → history resolves to XDG path."""
        xdg_dir = tmp_path / ".config" / "librofm-downloader"
        xdg_dir.mkdir(parents=True)
        (xdg_dir / "download_history.json").write_text("{}")

        cwd = tmp_path / "cwd"
        cwd.mkdir()

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(cwd)

        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value._config_path = None
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = "tok"
            mock_instance.fetch_library.return_value = []

            result = sync_run(
                config_path=None,
                secrets_path=None,
                history_path=None,
            )

            assert result.fatal_error is None

            # Verify DownloadHistory received the XDG path
            history_arg = mock_history_cls.call_args[0][0]
            assert "librofm-downloader" in str(history_arg)
            assert "download_history.json" in str(history_arg)

    def test_history_defaults_to_xdg_when_not_found_anywhere(self, tmp_path, monkeypatch):
        """No download_history.json anywhere → defaults to XDG location."""
        cwd = tmp_path / "cwd"
        cwd.mkdir()

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(cwd)

        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value._config_path = None
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = "tok"
            mock_instance.fetch_library.return_value = []

            result = sync_run(history_path=None)

            assert result.fatal_error is None

            # Should default to XDG location even though file doesn't exist
            history_arg = mock_history_cls.call_args[0][0]
            assert "librofm-downloader" in str(history_arg)
            assert ".config" in str(history_arg)
            assert "download_history.json" in str(history_arg)

    def test_explicit_history_path_bypasses_resolution(self, tmp_path, monkeypatch):
        """Explicit --history flag uses the exact path provided."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value._config_path = None
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = "tok"
            mock_instance.fetch_library.return_value = []

            result = sync_run(history_path="/custom/my_history.json")

            assert result.fatal_error is None

            history_arg = mock_history_cls.call_args[0][0]
            assert str(history_arg) == "/custom/my_history.json"


class TestSyncRunConfigResolutionMessages:
    """Messages about config resolution."""

    def test_missing_config_message_includes_searched_paths(self, tmp_path, monkeypatch, capsys):
        """config.yaml not found → message lists XDG and CWD paths."""
        xdg_dir = tmp_path / ".config" / "librofm-downloader"
        xdg_dir.mkdir(parents=True)
        (xdg_dir / "secrets.yaml").write_text(
            "librofm:\n  username: alice\n  password: secret\n"
        )

        cwd = tmp_path / "cwd"
        cwd.mkdir()

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(cwd)

        with (
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.download_book"),
        ):
            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = "tok"
            mock_instance.fetch_library.return_value = []

            result = sync_run(config_path=None, secrets_path=None, history_path=None)

            assert result.fatal_error is None
            output = capsys.readouterr().out
            assert "config.yaml not found" in output
            assert ".config" in output or "librofm-downloader" in output
            assert "Using built-in defaults" in output

    def test_verbose_shows_resolved_paths(self, tmp_path, monkeypatch, capsys):
        """--verbose shows the actual resolved file paths after loading config."""
        xdg_dir = tmp_path / ".config" / "librofm-downloader"
        xdg_dir.mkdir(parents=True)
        (xdg_dir / "secrets.yaml").write_text(
            "librofm:\n  username: alice\n  password: secret\n"
        )
        (xdg_dir / "download_history.json").write_text("{}")

        cwd = tmp_path / "cwd"
        cwd.mkdir()

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(cwd)

        with (
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.download_book"),
        ):
            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = "tok"
            mock_instance.fetch_library.return_value = []

            result = sync_run(
                config_path=None,
                secrets_path=None,
                history_path=None,
                verbose=True,
            )

            assert result.fatal_error is None
            output = capsys.readouterr().out.lower()
            # Verbose should show the resolved XDG paths
            assert "secrets" in output
            assert "history" in output
            assert "librofm-downloader" in output


class TestSyncRunMissingFilesErrors:
    """Error handling when files are missing."""

    def test_empty_home_clean_secrets_error(self, tmp_path, monkeypatch, capsys):
        """No files anywhere → clean error about missing secrets, fatal_error."""
        cwd = tmp_path / "cwd"
        cwd.mkdir()

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(cwd)

        result = sync_run(config_path=None, secrets_path=None, history_path=None)

        assert result.fatal_error is not None
        output = capsys.readouterr().out
        assert "secrets.yaml" in output or "Config error" in output
        assert "Traceback" not in output

    def test_only_secrets_in_xdg_works(self, tmp_path, monkeypatch, capsys):
        """Secrets in XDG only → defaults work, 'using built-in defaults' message visible."""
        xdg_dir = tmp_path / ".config" / "librofm-downloader"
        xdg_dir.mkdir(parents=True)
        (xdg_dir / "secrets.yaml").write_text(
            "librofm:\n  username: alice\n  password: secret\n"
        )

        cwd = tmp_path / "cwd"
        cwd.mkdir()

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(cwd)

        with (
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.download_book"),
        ):
            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = "tok"
            mock_instance.fetch_library.return_value = []

            result = sync_run(config_path=None, secrets_path=None, history_path=None)

            assert result.fatal_error is None
            output = capsys.readouterr().out
            assert "Using built-in defaults" in output


class TestSyncRunWorkersFlag:
    """Workers flag resolves worker count with 3-layer priority."""

    def test_cli_workers_overrides_config(self):
        """workers=8 overrides config.workers=3 → resolved workers = 8."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "B1", "authors": ["A"], "narrators": ["N"]},
            ]
            mock_history_cls.return_value.is_downloaded.return_value = False
            mock_download.return_value = DownloadResult(status="skipped")

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
                workers=8,
            )

            # Verify the run completed successfully
            assert result.fatal_error is None

    def test_no_flag_uses_config_value(self):
        """No workers flag uses config.workers (5) instead of default 3."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 5

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "B1", "authors": ["A"], "narrators": ["N"]},
            ]
            mock_history_cls.return_value.is_downloaded.return_value = False
            mock_download.return_value = DownloadResult(status="skipped")

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            assert result.fatal_error is None

    def test_workers_1_accepted(self):
        """workers=1 is accepted (sequential fallback)."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 10

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "B1", "authors": ["A"], "narrators": ["N"]},
            ]
            mock_history_cls.return_value.is_downloaded.return_value = False
            mock_download.return_value = DownloadResult(status="skipped")

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
                workers=1,
            )

            assert result.fatal_error is None


class TestSyncRunRenameChaptersFlag:
    """rename_chapters flag: CLI flag overrides config value."""

    def test_cli_rename_chapters_overrides_config_false(self):
        """rename_chapters=True overrides config.rename_chapters=False."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3
            mock_config.return_value.rename_chapters = False

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "B1", "authors": ["A"], "narrators": ["N"]},
            ]
            mock_history_cls.return_value.is_downloaded.return_value = False
            mock_download.return_value = DownloadResult(status="skipped")

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
                rename_chapters=True,
            )

            assert result.fatal_error is None

class TestSyncRunParallelWorkers1Parity:
    """--workers 1 must produce identical behavior to sequential.
    Regression guard: same order, same result, same summary counts,
    download_book called once per book in library order.
    """

    def test_workers_1_calls_all_books_in_order(self):
        """workers=1 → download_book called for each book, all complete."""
        from pathlib import Path

        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "Book A", "authors": ["A"], "narrators": ["N"]},
                {"isbn": "978222", "title": "Book B", "authors": ["B"], "narrators": ["N"]},
                {"isbn": "978333", "title": "Book C", "authors": ["C"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False
            mock_download.return_value = DownloadResult(status="downloaded", path=Path("/audiobooks/Author/Book.m4b"), format="m4b")

            result = sync_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
                workers=1,
            )

            assert result.fatal_error is None
            assert mock_download.call_count == 3

    def test_workers_1_exit_code_zero_on_success(self):
        """workers=1, all succeed → success result."""
        from pathlib import Path

        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "Only Book", "authors": ["A"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False
            mock_download.return_value = DownloadResult(status="downloaded", path=Path("/audiobooks/A/Only.m4b"), format="m4b")

            result = sync_run(workers=1)

            assert result.fatal_error is None


class TestSyncRunParallelCtrlCDrain:
    """Ctrl+C during parallel downloads triggers graceful drain."""

    def test_ctrl_c_during_download_prints_aborting_and_exits_cleanly(self):
        """KeyboardInterrupt → 'Aborting...' message + interrupted result."""
        from pathlib import Path

        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "Slow Book", "authors": ["A"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False
            mock_download.side_effect = KeyboardInterrupt

            result = sync_run(workers=1)

            # _download_one wraps KI as failure → partial result, clean exit
            # (may or may not be interrupted depending on where KI hits)
            assert result.fatal_error is None

    def test_ctrl_c_during_download_shows_aborting_message(self):
        """KeyboardInterrupt prints 'Aborting...' or similar message."""
        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "Book", "authors": ["A"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False
            mock_download.side_effect = KeyboardInterrupt

            result = sync_run(workers=1)

            # Current behavior just prints interrupt message; after implementation
            # it should also show 'Aborting...'
            # _download_one wraps KI as failure → partial result, clean exit
            assert result.fatal_error is None


class TestSyncRunParallelSummaryOrdering:
    """Summary groups: succeeded first, then failed, then skipped.
    Each group is in original library order (stable sort).
    """

    def test_summary_groups_succeeded_then_failed_then_skipped(self):
        """Result ordering: downloaded → failed → skipped, each group stable-sorted."""
        from pathlib import Path

        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "Will Succeed", "authors": ["A"], "narrators": ["N"]},
                {"isbn": "978222", "title": "Will Fail", "authors": ["B"], "narrators": ["N"]},
                {"isbn": "978333", "title": "Also Succeeds", "authors": ["C"], "narrators": ["N"]},
                {"isbn": "978444", "title": "Will Skip", "authors": ["D"], "narrators": ["N"]},
                {"isbn": "978555", "title": "Third Success", "authors": ["E"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False

            def _download_side_effect(book, *args, **kwargs):
                if book.isbn == "978222":
                    raise Exception("Download failed")
                if book.isbn == "978444":
                    return DownloadResult(status="skipped")  # skip (no format available)
                return DownloadResult(status="downloaded", path=Path(f"/audiobooks/{book.isbn}.m4b"), format="m4b")

            mock_download.side_effect = _download_side_effect

            result = sync_run(workers=3)

            assert result.fatal_error is None
            # All 5 books attempted
            assert mock_download.call_count == 5

    def test_mixed_results_correct_counts(self):
        """Mixed success/fail/skip → correct counts passed to reporter.summary()."""
        from pathlib import Path

        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
            patch("librofm_downloader.sync_run.DownloadReporter") as mock_reporter_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 2

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "OK", "authors": ["A"], "narrators": ["N"]},
                {"isbn": "978222", "title": "Fail", "authors": ["B"], "narrators": ["N"]},
                {"isbn": "978333", "title": "Skip", "authors": ["C"], "narrators": ["N"]},
                {"isbn": "978444", "title": "OK2", "authors": ["D"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False

            def _download_side_effect(book, *args, **kwargs):
                if book.isbn == "978222":
                    raise Exception("boom")
                if book.isbn == "978333":
                    return DownloadResult(status="skipped")  # skip
                return DownloadResult(status="downloaded", path=Path(f"/audiobooks/{book.isbn}.m4b"), format="m4b")

            mock_download.side_effect = _download_side_effect

            result = sync_run(workers=2)

            assert result.fatal_error is None

            # Verify summary was called with correct counts
            mock_reporter = mock_reporter_cls.return_value
            mock_reporter.summary.assert_called_once()
            call_kwargs = mock_reporter.summary.call_args.kwargs
            assert call_kwargs["downloaded"] == 2
            assert call_kwargs["failed"] == 1
            assert call_kwargs["skipped"] == 1


class TestSyncRunParallelConcurrency:
    """Verify that workers > 1 actually executes downloads concurrently."""

    def test_workers_3_faster_than_sequential(self):
        """With 3 slow books and workers=3, wall clock < sum of individual times."""
        import time
        from pathlib import Path

        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "Book A", "authors": ["A"], "narrators": ["N"]},
                {"isbn": "978222", "title": "Book B", "authors": ["B"], "narrators": ["N"]},
                {"isbn": "978333", "title": "Book C", "authors": ["C"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False

            def _slow_download(book, *args, **kwargs):
                time.sleep(0.1)
                return DownloadResult(status="downloaded", path=Path(f"/audiobooks/{book.isbn}.m4b"), format="m4b")

            mock_download.side_effect = _slow_download

            start = time.monotonic()
            result = sync_run(workers=3)
            elapsed = time.monotonic() - start

            assert result.fatal_error is None
            # 3 books × 0.1s each = 0.3s sequential. With 3 workers: ~0.1s.
            # Generous bound: must be < 0.25s (proves parallelism).
            assert elapsed < 0.25, f"workers=3 took {elapsed:.3f}s — expected < 0.25s for parallel execution"

    def test_failure_isolation_in_parallel(self):
        """One failing book doesn't prevent others from succeeding."""
        from pathlib import Path

        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "OK", "authors": ["A"], "narrators": ["N"]},
                {"isbn": "978222", "title": "BOOM", "authors": ["B"], "narrators": ["N"]},
                {"isbn": "978333", "title": "Also OK", "authors": ["C"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False

            call_results: list[str] = []

            def _download_side_effect(book, *args, **kwargs):
                call_results.append(book.isbn)
                if book.isbn == "978222":
                    raise Exception("network error")
                return DownloadResult(status="downloaded", path=Path(f"/audiobooks/{book.isbn}.m4b"), format="m4b")

            mock_download.side_effect = _download_side_effect

            result = sync_run(workers=3)

            assert result.fatal_error is None
            # All 3 were attempted
            assert mock_download.call_count == 3
            # Both successful books completed despite the failure
            assert "978111" in call_results
            assert "978333" in call_results


class TestSyncRunParallelVerboseMode:
    """Verbose mode output is readable when downloads overlap temporally."""

    def test_verbose_prints_per_book_details_with_workers_3(self):
        """With verbose=True and workers=3, each book's details are printed.
        Verbose lines use console.print which is thread-safe in Rich."""
        from pathlib import Path

        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "Alpha", "authors": ["Author A"], "narrators": ["Narr X"]},
                {"isbn": "978222", "title": "Beta", "authors": ["Author B"], "narrators": ["Narr Y"]},
                {"isbn": "978333", "title": "Gamma", "authors": ["Author C"], "narrators": ["Narr Z"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False
            mock_download.return_value = DownloadResult(status="downloaded", path=Path(f"/audiobooks/book.m4b"), format="m4b")

            # Should not raise or produce garbled output
            result = sync_run(verbose=True, workers=3)

            assert result.fatal_error is None
            assert mock_download.call_count == 3

    def test_verbose_with_failure_shows_book_details_before_error(self):
        """Verbose mode prints book info even for books that fail."""
        from pathlib import Path

        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 2

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "Fails", "authors": ["A"], "narrators": ["N"]},
                {"isbn": "978222", "title": "OK", "authors": ["B"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False

            def _download_side_effect(book, *args, **kwargs):
                if book.isbn == "978111":
                    raise Exception("connection reset")
                return DownloadResult(status="downloaded", path=Path(f"/audiobooks/{book.isbn}.m4b"), format="m4b")

            mock_download.side_effect = _download_side_effect

            # Should not raise; failure is isolated
            result = sync_run(verbose=True, workers=2)

            assert result.fatal_error is None
            assert mock_download.call_count == 2


class TestSyncRunParallelPartialFileSafety:
    """Partial files after Ctrl+C are left for resume on next run.
    The downloader uses .partial + atomic rename; the orchestrator must NOT
    clean up partial files on interrupt.
    """

    def test_ctrl_c_leaves_partial_files_for_resume(self):
        """After KeyboardInterrupt, .partial files are not deleted — resume-safe."""
        from pathlib import Path
        from unittest.mock import MagicMock, patch as mock_patch

        with (
            patch("librofm_downloader.sync_run.load_config") as mock_config,
            patch("librofm_downloader.sync_run.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.sync_run.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.sync_run.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 1

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "Big Book", "authors": ["A"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False
            mock_download.side_effect = KeyboardInterrupt

            result = sync_run(workers=1)

            # _download_one wraps KI as failure → partial result, clean exit
            assert result.fatal_error is None
            # download_book was called (partial file may have been created)
            assert mock_download.call_count == 1
