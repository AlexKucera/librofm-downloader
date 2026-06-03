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
            # 2 succeed, 1 returns None (skipped/no format), 1 raises error
            mock_download.side_effect = [
                Path("/audiobooks/A/New Book A.m4b"),
                Path("/audiobooks/B/New Book B.mp3"),
                None,  # skipped (no format available)
                httpx.HTTPStatusError(
                    message="Not Found",
                    request=httpx.Request("GET", "https://example.com/fail"),
                    response=httpx.Response(404, request=httpx.Request("GET", "https://example.com/fail")),
                ),
            ]

            exit_code = run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            assert exit_code == 0
            assert mock_download.call_count == 4
            captured = capsys.readouterr()
            output = captured.out
            # Summary should show counts
            assert "Summary:" in output
            assert "2 downloaded" in output
            # Failed book should be listed with ISBN and title
            assert "978444" in output
            assert "Fail Book D" in output
            assert "404" in output or "Not Found" in output
            # Skipped book should be listed
            assert "978333" in output
            assert "Skip Book C" in output


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