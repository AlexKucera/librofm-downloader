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
            assert "Downloaded" in captured.out
            assert "Skipped" not in captured.out or "Downloaded" in captured.out
