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
