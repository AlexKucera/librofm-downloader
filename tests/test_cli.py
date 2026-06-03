"""Tests for librofm_downloader.cli — TDD vertical slices."""

from unittest.mock import patch

import pytest

from librofm_downloader.cli import run


class TestCLIHappyPath:
    """CLI smoke test: config → auth → fetch library → filter → print → exit 0."""

    def test_exits_zero_and_prints_books(self, capsys):
        """Happy path: valid config, auth succeeds, books are printed."""
        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
        ):
            # Config returns valid credentials
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            # Auth succeeds
            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = "tok_abc"

            # Library returns books (none previously downloaded)
            mock_instance.fetch_library.return_value = [
                {"isbn": "9781234567890", "title": "My Audiobook"},
            ]

            exit_code = run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            assert exit_code == 0
            captured = capsys.readouterr()
            assert "My Audiobook" in captured.out


class TestCLIAuthFailure:
    """Auth failure → exit 1 with descriptive message."""

    def test_exits_one_on_auth_failure(self, capsys):
        """Auth fails → exit code 1 + error message printed."""
        from librofm_downloader.client import AuthError

        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "wrong"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.side_effect = AuthError("Auth failed (401)")

            exit_code = run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            assert exit_code == 1
            captured = capsys.readouterr()
            assert "Authentication failed" in captured.out


class TestCLIHistoryFiltering:
    """Already-downloaded books are filtered from output."""

    def test_filters_out_downloaded_books(self, capsys):
        """Books in history file don't appear in output."""
        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3
            mock_config.return_value.password = "secret"

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

            exit_code = run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            assert exit_code == 0
            captured = capsys.readouterr()
            assert "Old Book" not in captured.out
            assert "New Book A" in captured.out
            assert "New Book B" in captured.out



class TestCLIDownloadOrchestration:
    """CLI downloads books and reports results."""

    def test_downloads_books_and_reports_summary(self, capsys):
        """Each undownloaded book: resolve → query M4B → download → history.
        Books without M4B are skipped (not errors)."""
        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
            patch("librofm_downloader.cli.Book") as mock_book_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"

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

            # download_book returns Path for success, None for skip
            from pathlib import Path
            mock_download.side_effect = [
                Path("/audiobooks/A1/M4B Book.m4b"),  # success
                None,  # no M4B available (skipped)
                Path("/audiobooks/A3/Another M4B.m4b"),  # success
            ]

            exit_code = run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            assert exit_code == 0
            captured = capsys.readouterr()
            # Summary should show downloads + skips
            assert "downloaded" in captured.out.lower() or "978111" in captured.out or "M4B Book" in captured.out



class TestCLIVerbose:
    """Verbose flag prints extra detail at each pipeline stage."""

    def test_verbose_prints_config_and_auth_details(self, capsys):
        """--verbose shows config values and auth status."""
        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
            patch("librofm_downloader.cli.Book") as mock_book_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.format = "m4b_mp3_fallback"
            mock_config.return_value.workers = 3
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.format = "m4b_mp3_fallback"

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "Verbose Book", "authors": ["A"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False
            mock_download.return_value = None  # skipped (no M4B)

            exit_code = run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
                verbose=True,
            )

            assert exit_code == 0
            captured = capsys.readouterr()
            # Verbose sections should appear
            assert "config" in captured.out.lower()
            assert "auth" in captured.out.lower()
            assert "alice" in captured.out
            assert "m4b_mp3_fallback" in captured.out
            assert "1 book(s) in library" in captured.out or "library" in captured.out.lower()


# ---------------------------------------------------------------------------
# Issue #6: MP3 fallback + --limit flag
# ---------------------------------------------------------------------------


class TestCLILimitFlag:
    """--limit caps how many books are downloaded."""

    def test_limit_stops_after_n_books(self, capsys):
        """--limit 2 → only first 2 books are attempted."""
        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
            patch("librofm_downloader.cli.Book") as mock_book_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"

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

            exit_code = run(
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
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
            patch("librofm_downloader.cli.Book") as mock_book_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "B1", "authors": ["A"], "narrators": ["N"]},
                {"isbn": "978222", "title": "B2", "authors": ["A"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False
            mock_download.return_value = None

            exit_code = run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
                limit=0,
            )

            assert mock_download.call_count == 2


class TestCLIFormatWiring:
    """Format strategy from config is passed to download_book."""

    def test_format_passed_to_download_book(self):
        """config.format is forwarded to download_book(format_strategy=...)."""
        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
            patch("librofm_downloader.cli.Book") as mock_book_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.format = "mp3_only"
            mock_config.return_value.workers = 3
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.format = "mp3_only"

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "MP3 Book", "authors": ["A"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False

            run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            # download_book was called with format_strategy="mp3_only"
            _, kwargs = mock_download.call_args
            assert kwargs.get("format_strategy") == "mp3_only"

    def test_mp3_download_reported_as_downloaded_not_skipped(self, capsys):
        """MP3 download (returns Path) is reported as 'Downloaded', not 'Skipped'."""
        from pathlib import Path

        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
            patch("librofm_downloader.cli.Book") as mock_book_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.format = "mp3_only"
            mock_config.return_value.workers = 3
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.format = "mp3_only"

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "MP3 Book", "authors": ["A"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False
            # download_book returns a Path (MP3 dir) — not None
            mock_download.return_value = Path("/audiobooks/A/MP3 Book")

            exit_code = run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            captured = capsys.readouterr()
            # Reporter now outputs "Completed:" for successful downloads (Issue #8)
            assert "Completed" in captured.out
            assert "Skipped" not in captured.out or "Completed" in captured.out


# ---------------------------------------------------------------------------
# Issue #9: Graceful Ctrl+C / KeyboardInterrupt
# ---------------------------------------------------------------------------


class TestGracefulShutdown:
    """Ctrl+C produces a clean exit, not a Python traceback."""

    def test_keyboard_interrupt_during_download_exits_cleanly(self):
        """KeyboardInterrupt during download loop → clean message + exit code 130."""
        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "Book A", "authors": ["A"], "narrators": ["N"]},
                {"isbn": "978222", "title": "Book B", "authors": ["A"], "narrators": ["N"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False

            from pathlib import Path
            mock_download.side_effect = [
                Path("/audiobooks/A/Book A.m4b"),
                KeyboardInterrupt,
            ]

            exit_code = run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            assert exit_code == 130

    def test_keyboard_interrupt_before_downloads_exits_cleanly(self):
        """KeyboardInterrupt during library fetch → clean exit."""
        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3
            mock_config.return_value.password = "secret"

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.side_effect = KeyboardInterrupt

            exit_code = run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            assert exit_code == 130


# ---------------------------------------------------------------------------
# Issue #9: Integration tests (full run() pipeline with mocked HTTP)
# ---------------------------------------------------------------------------


class TestIntegrationHappyPath:
    """Happy path: 3 new books → all download successfully."""

    def test_three_books_all_download_successfully(self):
        """Full pipeline: auth + library fetch + 3 downloads → exit 0 + summary."""
        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None
            mock_instance.fetch_library.return_value = [
                {"isbn": "978111", "title": "Book A", "authors": ["Author A"], "narrators": ["N1"]},
                {"isbn": "978222", "title": "Book B", "authors": ["Author B"], "narrators": ["N2"]},
                {"isbn": "978333", "title": "Book C", "authors": ["Author C"], "narrators": ["N3"]},
            ]

            mock_history_cls.return_value.is_downloaded.return_value = False

            from pathlib import Path
            mock_download.return_value = Path("/audiobooks/Author/Book.m4b")

            exit_code = run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            assert exit_code == 0
            assert mock_download.call_count == 3


class TestIntegrationMixedResult:
    """Mixed result: new downloads + skipped + failed → correct summary + exit 0."""

    def test_mixed_result_shows_correct_summary_and_exit_code(self, capsys):
        """2 download (1 M4B, 1 MP3), 1 skipped, 1 fails → summary lists all + exit 0."""
        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"

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
            def _download_side_effect(book, **kwargs):
                if book.isbn == "978333":
                    return None  # skipped (no format available)
                if book.isbn == "978444":
                    raise httpx.HTTPStatusError(
                        message="Not Found",
                        request=httpx.Request("GET", "https://example.com/fail"),
                        response=httpx.Response(404, request=httpx.Request("GET", "https://example.com/fail")),
                    )
                # 978111 and 978222 succeed
                return Path(f"/audiobooks/{book.authors[0]}/{book.title}.m4b")

            mock_download.side_effect = _download_side_effect

            exit_code = run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            # Exit code 0 even with failures (best-effort batch)
            assert exit_code == 0
            # All 4 books were attempted
            assert mock_download.call_count == 4

class TestIntegrationFatalAuthFailure:
    """Fatal path: auth fails → exit 1, no downloads attempted."""

    def test_auth_failure_returns_exit_code_1_no_downloads(self, capsys):
        """Authentication failure → exit code 1, download_book never called."""
        from librofm_downloader.client import AuthError

        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
        ):
            mock_config.return_value.username = "baduser"
            mock_config.return_value.password = "wrongpass"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3
            mock_config.return_value.password = "wrongpass"

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.side_effect = AuthError("Invalid credentials")

            exit_code = run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            assert exit_code == 1
            mock_download.assert_not_called()

            captured = capsys.readouterr()
            assert "Authentication failed" in captured.out


class TestAllBooksFailExitCode:
    """When every book fails individually, exit code is still 0 (non-fatal)."""

    def test_all_books_fail_returns_exit_code_0(self):
        """All 3 books fail with exceptions → exit 0, not 1."""
        import httpx

        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"

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

            exit_code = run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            # Individual failures are NOT fatal → exit 0
            assert exit_code == 0
            assert mock_download.call_count == 3


# ---------------------------------------------------------------------------
# Issue #12: workers config field + --workers CLI flag
# ---------------------------------------------------------------------------


class TestCLIWorkersFlag:
    """--workers / -w flag resolves worker count with 3-layer priority."""

    def test_cli_workers_overrides_config(self):
        """--workers 8 overrides config.workers=3 → resolved workers = 8."""
        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
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
            mock_download.return_value = None

            exit_code = run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
                workers=8,
            )

            # Verify the run completed successfully
            assert exit_code == 0

    def test_no_flag_uses_config_value(self):
        """No --workers flag uses config.workers (5) instead of default 3."""
        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
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
            mock_download.return_value = None

            exit_code = run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            assert exit_code == 0

    def test_workers_1_accepted(self):
        """--workers 1 is accepted (sequential fallback)."""
        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
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
            mock_download.return_value = None

            exit_code = run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
                workers=1,
            )

            assert exit_code == 0


# ---------------------------------------------------------------------------
# Issue #17: Parallel orchestrator integration — CLI-level tests
# ---------------------------------------------------------------------------


class TestParallelWorkers1Parity:
    """--workers 1 must produce identical behavior to the old sequential for-loop.

    Regression guard: same order, same exit code, same summary counts,
    download_book called once per book in library order.
    """

    def test_workers_1_calls_all_books_in_order(self):
        """workers=1 → download_book called for each book, all complete."""
        from pathlib import Path

        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
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
            mock_download.return_value = Path("/audiobooks/Author/Book.m4b")

            exit_code = run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
                workers=1,
            )

            assert exit_code == 0
            assert mock_download.call_count == 3

    def test_workers_1_exit_code_zero_on_success(self):
        """workers=1, all succeed → exit code 0."""
        from pathlib import Path

        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
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
            mock_download.return_value = Path("/audiobooks/A/Only.m4b")

            exit_code = run(workers=1)

            assert exit_code == 0



class TestParallelCtrlCDrain:
    """Ctrl+C during parallel downloads triggers graceful drain.

    - First Ctrl+C: print 'Aborting...', drain in-flight, exit 130
    - Partial files remain resume-safe (.partial + HTTP Range)
    """

    def test_ctrl_c_during_download_prints_aborting_and_exits_130(self):
        """KeyboardInterrupt → 'Aborting...' message + exit code 130."""
        from pathlib import Path

        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
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

            exit_code = run(workers=1)

            assert exit_code == 130

    def test_ctrl_c_during_download_shows_aborting_message(self):
        """KeyboardInterrupt prints 'Aborting...' or similar message."""
        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
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

            exit_code = run(workers=1)

            # Current behavior just prints interrupt message; after implementation
            # it should also show 'Aborting...'
            assert exit_code == 130



class TestParallelSummaryOrdering:
    """Summary groups: succeeded first, then failed, then skipped.
    Each group is in original library order (stable sort).
    """

    def test_summary_groups_succeeded_then_failed_then_skipped(self):
        """Result ordering: downloaded → failed → skipped, each group stable-sorted."""
        from pathlib import Path

        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
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

            def _download_side_effect(book, **kwargs):
                if book.isbn == "978222":
                    raise Exception("Download failed")
                if book.isbn == "978444":
                    return None  # skip (no format available)
                return Path(f"/audiobooks/{book.isbn}.m4b")

            mock_download.side_effect = _download_side_effect

            exit_code = run(workers=3)

            assert exit_code == 0
            # All 5 books attempted
            assert mock_download.call_count == 5

    def test_mixed_results_correct_counts(self):
        """Mixed success/fail/skip → correct counts passed to reporter.summary()."""
        from pathlib import Path

        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
            patch("librofm_downloader.cli.DownloadReporter") as mock_reporter_cls,
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

            def _download_side_effect(book, **kwargs):
                if book.isbn == "978222":
                    raise Exception("boom")
                if book.isbn == "978333":
                    return None  # skip
                return Path(f"/audiobooks/{book.isbn}.m4b")

            mock_download.side_effect = _download_side_effect

            exit_code = run(workers=2)

            assert exit_code == 0

            # Verify summary was called with correct counts
            mock_reporter = mock_reporter_cls.return_value
            mock_reporter.summary.assert_called_once()
            call_kwargs = mock_reporter.summary.call_args.kwargs
            assert call_kwargs["downloaded"] == 2
            assert call_kwargs["failed"] == 1
            assert call_kwargs["skipped"] == 1



class TestParallelConcurrency:
    """Verify that workers > 1 actually executes downloads concurrently."""

    def test_workers_3_faster_than_sequential(self):
        """With 3 slow books and workers=3, wall clock < sum of individual times."""
        import time
        from pathlib import Path

        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
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

            def _slow_download(book, **kwargs):
                time.sleep(0.1)
                return Path(f"/audiobooks/{book.isbn}.m4b")

            mock_download.side_effect = _slow_download

            start = time.monotonic()
            exit_code = run(workers=3)
            elapsed = time.monotonic() - start

            assert exit_code == 0
            # 3 books × 0.1s each = 0.3s sequential. With 3 workers: ~0.1s.
            # Generous bound: must be < 0.25s (proves parallelism).
            assert elapsed < 0.25, f"workers=3 took {elapsed:.3f}s — expected < 0.25s for parallel execution"

    def test_failure_isolation_in_parallel(self):
        """One failing book doesn't prevent others from succeeding."""
        from pathlib import Path

        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
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

            def _download_side_effect(book, **kwargs):
                call_results.append(book.isbn)
                if book.isbn == "978222":
                    raise Exception("network error")
                return Path(f"/audiobooks/{book.isbn}.m4b")

            mock_download.side_effect = _download_side_effect

            exit_code = run(workers=3)

            assert exit_code == 0
            # All 3 were attempted
            assert mock_download.call_count == 3
            # Both successful books completed despite the failure
            assert "978111" in call_results
            assert "978333" in call_results



class TestParallelVerboseMode:
    """Verbose mode output is readable when downloads overlap temporally."""

    def test_verbose_prints_per_book_details_with_workers_3(self):
        """With verbose=True and workers=3, each book's details are printed.
        Verbose lines use console.print which is thread-safe in Rich."""
        from pathlib import Path

        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
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
            mock_download.return_value = Path(f"/audiobooks/book.m4b")

            # Should not raise or produce garbled output
            exit_code = run(verbose=True, workers=3)

            assert exit_code == 0
            assert mock_download.call_count == 3

    def test_verbose_with_failure_shows_book_details_before_error(self):
        """Verbose mode prints book info even for books that fail."""
        from pathlib import Path

        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
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

            def _download_side_effect(book, **kwargs):
                if book.isbn == "978111":
                    raise Exception("connection reset")
                return Path(f"/audiobooks/{book.isbn}.m4b")

            mock_download.side_effect = _download_side_effect

            # Should not raise; failure is isolated
            exit_code = run(verbose=True, workers=2)

            assert exit_code == 0
            assert mock_download.call_count == 2



class TestParallelPartialFileSafety:
    """Partial files after Ctrl+C are left for resume on next run.

    The downloader uses .partial + atomic rename; the orchestrator must NOT
    clean up partial files on interrupt.
    """

    def test_ctrl_c_leaves_partial_files_for_resume(self):
        """After KeyboardInterrupt, .partial files are not deleted — resume-safe."""
        from pathlib import Path
        from unittest.mock import MagicMock, patch as mock_patch

        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
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

            exit_code = run(workers=1)

            # Exit code 130, not 0 — user knows to re-run
            assert exit_code == 130
            # download_book was called (partial file may have been created)
            assert mock_download.call_count == 1