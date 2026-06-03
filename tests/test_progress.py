"""Tests for librofm_downloader.progress — TDD vertical slices (Issue #8)."""

import io
import sys
import tempfile

import pytest

from librofm_downloader.downloader import Book
from librofm_downloader.progress import DownloadReporter, PlainTextReporter


# ---------------------------------------------------------------------------
# Test 1: TTY detection — reporter picks correct backend
# ---------------------------------------------------------------------------

class TestTTYDetection:
    """DownloadReporter factory selects PlainTextReporter when stdout is not a TTY."""

    def test_non_tty_returns_plain_text_reporter(self):
        """When stdout is not a TTY (pipe/cron), reporter uses plain text."""
        # Simulate non-TTY stdout (e.g., piped output or cron)
        fake_stdout = io.StringIO()  # StringIO is never a TTY
        reporter = DownloadReporter(stdout=fake_stdout)
        assert isinstance(reporter, PlainTextReporter)

    def test_tty_returns_progress_reporter(self):
        """When stdout IS a TTY, reporter uses rich Progress-based output."""
        from unittest.mock import MagicMock

        # Mock a TTY-like stdout
        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = DownloadReporter(stdout=mock_tty)
        # Should NOT be a PlainTextReporter when TTY detected
        assert not isinstance(reporter, PlainTextReporter)
        # Should be a ProgressReporter (rich-based)
        from librofm_downloader.progress import ProgressReporter
        assert isinstance(reporter, ProgressReporter)


# ---------------------------------------------------------------------------
# Test 2: Plain log format — downloading
# ---------------------------------------------------------------------------

class TestPlainTextDownloading:
    """PlainTextReporter emits 'Downloading: Author - Title (size)' on start."""

    def test_downloading_format_with_single_author(self, capsys):
        """Single author: 'Downloading: Author Name - Book Title (size in MB)'."""
        fake_stdout = io.StringIO()
        reporter = PlainTextReporter(stdout=fake_stdout)

        book = Book(
            title="The Final Empire",
            authors=["Brandon Sanderson"],
            narrators=["Michael Kramer"],
            isbn="9780765374991",
        )
        reporter.start_download(book, total_bytes=45_000_000)

        output = fake_stdout.getvalue()
        assert "Downloading:" in output
        assert "Brandon Sanderson" in output
        assert "The Final Empire" in output
        assert "MB" in output  # e.g., "42.9 MB" for 45M bytes (1024-base)

    def test_downloading_format_with_multiple_authors(self, capsys):
        """Multiple authors: joined with commas."""
        fake_stdout = io.StringIO()
        reporter = PlainTextReporter(stdout=fake_stdout)

        book = Book(
            title="Good Omens",
            authors=["Neil Gaiman", "Terry Pratchett"],
            narrators=["Martin Jarvis"],
            isbn="9780062982360",
        )
        reporter.start_download(book, total_bytes=10_000_000)

        output = fake_stdout.getvalue()
        assert "Neil Gaiman" in output
        assert "Terry Pratchett" in output


# ---------------------------------------------------------------------------
# Test 3: Plain log format — completed
# ---------------------------------------------------------------------------

class TestPlainTextCompleted:
    """PlainTextReporter emits 'Completed: Author - Title' on success."""

    def test_completed_format(self, capsys):
        """Successful download: 'Completed: Author - Title'."""
        fake_stdout = io.StringIO()
        reporter = PlainTextReporter(stdout=fake_stdout)

        book = Book(
            title="Skyward",
            authors=["Brandon Sanderson"],
            narrators=["Sophie Aldred"],
            isbn="9781509697815",
        )
        reporter.complete(book)

        output = fake_stdout.getvalue()
        assert "Completed:" in output
        assert "Brandon Sanderson" in output
        assert "Skyward" in output


# ---------------------------------------------------------------------------
# Test 4: Plain log format — failed with ISBN + reason
# ---------------------------------------------------------------------------

class TestPlainTextFailed:
    """PlainTextReporter emits 'Failed: Author - Title (reason)' with ISBN."""

    def test_failed_format_includes_isbn_and_reason(self, capsys):
        """Failed download includes ISBN, title, and error reason."""
        fake_stdout = io.StringIO()
        reporter = PlainTextReporter(stdout=fake_stdout)

        book = Book(
            title="Broken Book",
            authors=["Some Author"],
            narrators=["N"],
            isbn="9789999999999",
        )
        reporter.fail(book, reason="HTTP 404: Not Found")

        output = fake_stdout.getvalue()
        assert "Failed:" in output
        assert "Some Author" in output
        assert "Broken Book" in output
        assert "9789999999999" in output
        assert "404" in output


# ---------------------------------------------------------------------------
# Test 5: Failure isolation — one fail + others succeed
# ---------------------------------------------------------------------------

class TestFailureIsolationCLI:
    """One failing book does not prevent subsequent books from downloading."""

    def test_one_failure_does_not_stop_batch(self, capsys):
        """Second book fails; first and third still download. Exit code 0."""
        from pathlib import Path
        from unittest.mock import patch

        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None

            raw_books = [
                {"isbn": "978111", "title": "Book A", "authors": ["A1"], "narrators": ["N1"]},
                {"isbn": "978222", "title": "Book B", "authors": ["A2"], "narrators": ["N2"]},
                {"isbn": "978333", "title": "Book C", "authors": ["A3"], "narrators": ["N3"]},
            ]
            mock_instance.fetch_library.return_value = raw_books

            mock_history_cls.return_value.is_downloaded.return_value = False

            # Book A succeeds, Book B fails, Book C succeeds
            mock_download.side_effect = [
                Path("/audiobooks/A1/Book A.m4b"),   # success
                Exception("Network timeout"),          # failure
                Path("/audiobooks/A3/Book C.m4b"),   # success
            ]

            exit_code = run = __import__("librofm_downloader.cli").cli.run
            # Need to import run properly
            from librofm_downloader.cli import run as cli_run

            exit_code = cli_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            # All 3 books were attempted
            assert mock_download.call_count == 3
            # Exit code is 0 (failures are non-fatal)
            assert exit_code == 0
            captured = capsys.readouterr()
            # Reporter output: Completed for successes, Failed for failure, Summary with counts
            out = captured.out
            assert "Completed" in out   # at least one success
            assert "Failed" in out       # the failure case
            assert "2 downloaded" in out  # summary counts correct
            assert "1 failed" in out


# ---------------------------------------------------------------------------
# Test 6: Fatal vs book-level error distinction
# ---------------------------------------------------------------------------

class TestFatalVsBookLevel:
    """Fatal errors (auth fail) exit 1 immediately before any downloads start."""

    def test_auth_failure_exits_one_before_downloads(self, capsys):
        """Auth failure → exit 1, download_book never called."""
        from unittest.mock import patch
        from librofm_downloader.client import AuthError

        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmClient") as mock_client_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "wrong"

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.side_effect = AuthError("Auth failed (401)")

            from librofm_downloader.cli import run as cli_run

            exit_code = cli_run(
                config_path="/fake/config.yaml",
                secrets_path="/fake/secrets.yaml",
                history_path="/fake/history.json",
            )

            assert exit_code == 1
            # No downloads were attempted
            assert mock_download.call_count == 0
            captured = capsys.readouterr()
            assert "Authentication failed" in captured.out


# ---------------------------------------------------------------------------
# Test 7: Progress bar columns — TTY mode renders %, speed, ETA, size
# ---------------------------------------------------------------------------

class TestProgressReporterColumns:
    """ProgressReporter (TTY mode) configures rich.Progress with required columns."""

    def test_progress_bar_has_speed_column(self):
        """Progress bar includes TransferSpeedColumn (MB/s)."""
        from unittest.mock import MagicMock, patch

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = DownloadReporter(stdout=mock_tty)

        book = Book(
            title="Big Book",
            authors=["Author"],
            narrators=["N"],
            isbn="9780000000001",
        )
        # Should not raise — progress bar initializes with speed column
        reporter.start_download(book, total_bytes=100_000_000)
        reporter.complete(book)

        # Verify progress was created with expected column types
        assert reporter._progress is not None
        column_types = [type(c).__name__ for c in reporter._progress.columns]
        assert "TransferSpeedColumn" in column_types

    def test_progress_bar_has_eta_column(self):
        """Progress bar includes RemainingTimeColumn (ETA)."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = DownloadReporter(stdout=mock_tty)

        book = Book(title="Test", authors=["A"], narrators=["N"], isbn="9780000000002")
        reporter.start_download(book, total_bytes=50_000_000)
        reporter.complete(book)

        column_types = [type(c).__name__ for c in reporter._progress.columns]
        assert "TimeRemainingColumn" in column_types

    def test_progress_bar_has_percentage_column(self):
        """Progress bar shows percentage."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = DownloadReporter(stdout=mock_tty)

        book = Book(title="Test", authors=["A"], narrators=["N"], isbn="9780000000003")
        reporter.start_download(book, total_bytes=50_000_000)

        # Percentage column renders task.percentage (it's a format string, not a Column)
        assert "percentage" in reporter._progress.columns[2].lower()

    def test_progress_bar_has_download_size_column(self):
        """Progress bar includes DownloadColumn (file size)."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = DownloadReporter(stdout=mock_tty)

        book = Book(title="Test", authors=["A"], narrators=["N"], isbn="9780000000004")
        reporter.start_download(book, total_bytes=75_000_000)
        reporter.complete(book)

        column_types = [type(c).__name__ for c in reporter._progress.columns]
        assert "DownloadColumn" in column_types


# ---------------------------------------------------------------------------
# Test 8: Summary line — correct counts after mixed results
# ---------------------------------------------------------------------------

class TestSummaryLine:
    """Summary shows correct downloaded/skipped/failed counts."""

    def test_plain_text_summary(self):
        """PlainTextReporter.summary() prints correct counts."""
        fake_stdout = io.StringIO()
        reporter = PlainTextReporter(stdout=fake_stdout)

        reporter.summary(downloaded=5, skipped=2, failed=1)

        output = fake_stdout.getvalue()
        assert "Summary:" in output
        assert "5 downloaded" in output
        assert "2 skipped" in output
        assert "1 failed" in output

    def test_all_zero_summary(self):
        """Summary handles all-zero counts."""
        fake_stdout = io.StringIO()
        reporter = PlainTextReporter(stdout=fake_stdout)

        reporter.summary(downloaded=0, skipped=0, failed=0)

        output = fake_stdout.getvalue()
        assert "0 downloaded" in output
        assert "0 skipped" in output
        assert "0 failed" in output


# ---------------------------------------------------------------------------
# Test 9: Progress callback — download functions call back with bytes done
# ---------------------------------------------------------------------------

class TestProgressCallbackM4B:
    """download_m4b() calls progress callback with running byte count."""

    def test_m4b_progress_callback_receives_increasing_bytes(self):
        """During M4B download, callback is called with monotonically increasing values."""
        import httpx
        from pathlib import Path
        from librofm_downloader.downloader import download_m4b

        # 3 chunks of 10 bytes = 30 bytes total
        payload = b"A" * 30

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=payload, headers={"content-length": "30"})

        transport = httpx.MockTransport(handler)
        progress_calls: list[int] = []

        def on_progress(completed: int, *, total: int | None = None) -> None:
            progress_calls.append(completed)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.m4b"
            result = download_m4b(
                url="https://cdn.example.com/test.m4b",
                output_path=output_path,
                transport=transport,
                progress=on_progress,
            )

            assert result == output_path
            # Callback must be called at least once
            assert len(progress_calls) >= 1
            # Values must be strictly increasing (bytes downloaded so far)
            for i in range(1, len(progress_calls)):
                assert progress_calls[i] > progress_calls[i - 1], \
                    f"Expected increasing, got {progress_calls[i-1]} -> {progress_calls[i]}"
            # Final call should reflect full payload size (including resume offset if any)
            assert progress_calls[-1] == 30

    def test_m4b_no_callback_still_works(self):
        """Download works normally when no progress callback is provided."""
        import httpx
        from pathlib import Path
        from librofm_downloader.downloader import download_m4b

        payload = b"B" * 20

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=payload)

        transport = httpx.MockTransport(handler)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nocallback.m4b"
            result = download_m4b(
                url="https://cdn.example.com/nocallback.m4b",
                output_path=output_path,
                transport=transport,
                # No progress= argument — must not raise
            )
            assert result == output_path
            assert output_path.read_bytes() == payload


class TestProgressCallbackZipPart:
    """download_zip_part() calls progress callback with running byte count."""

    def test_zip_part_progress_callback_receives_bytes(self):
        """During ZIP part download, callback is called with running byte count."""
        import zipfile
        import httpx
        from pathlib import Path
        from librofm_downloader.downloader import download_zip_part

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("track.mp3", b"audio-data-" * 5)  # ~60 bytes of zip payload
        zip_payload = zip_buf.getvalue()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=zip_payload, headers={"content-length": str(len(zip_payload))})

        transport = httpx.MockTransport(handler)
        progress_calls: list[int] = []

        def on_progress(completed: int, *, total: int | None = None) -> None:
            progress_calls.append(completed)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "extracted"
            output_dir.mkdir()
            result = download_zip_part(
                url="https://cdn.example.com/part.zip",
                output_dir=output_dir,
                transport=transport,
                progress=on_progress,
            )

            # ZIP was extracted
            assert (output_dir / "track.mp3").exists()
            # Callback received increasing values
            assert len(progress_calls) >= 1
            for i in range(1, len(progress_calls)):
                assert progress_calls[i] >= progress_calls[i - 1]


class TestProgressCallbackWiring:
    """download_book() threads the progress callback through to low-level downloads."""

    def test_download_book_forwards_progress_to_m4b(self):
        """progress callable passed to download_book reaches download_m4b."""
        import httpx
        from pathlib import Path
        from librofm_downloader.downloader import Book, download_book
        from librofm_downloader.client import LibroFmClient
        from librofm_downloader.history import DownloadHistory

        m4b_payload = b"callback-test-data" * 10  # 160 bytes

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/audiobooks/9781111111111/packaged_m4b":
                return httpx.Response(200, json={"m4b_url": "https://cdn.example.com/book.m4b"})
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=m4b_payload)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = LibroFmClient(base_url="https://libro.fm", username="u", password="p")
        client.authenticate(transport=transport)

        book = Book(title="CB Test", authors=["A"], narrators=["N"], isbn="9781111111111")
        progress_calls: list[int] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            history = DownloadHistory(Path(tmpdir) / "history.json")

            download_book(
                book=book,
                client=client,
                output_base=base_dir,
                history=history,
                transport=transport,
                progress=lambda n, **kw: progress_calls.append(n),
            )

            # Progress callback was invoked during the M4B download
            assert len(progress_calls) >= 1
            # Final value reflects the full download size
            assert progress_calls[-1] == len(m4b_payload)


# ---------------------------------------------------------------------------
# Test 10: Progress bar total is set from response Content-Length
# ---------------------------------------------------------------------------

class TestProgressTotalFromContentLength:
    """ProgressReporter.update(completed, total) sets the task's total so % and ETA work."""

    def test_update_with_total_sets_task_total(self):
        """When progress callback includes total, task.total is updated."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = DownloadReporter(stdout=mock_tty)

        book = Book(title="Big", authors=["A"], narrators=["N"], isbn="9780000000010")
        reporter.start_download(book, total_bytes=0)  # unknown at start

        # Simulate what download_m4b does after reading Content-Length header
        reporter.update(0, total=100_000_000)

        # Task now has a total — percentage can be computed
        task = reporter._progress.tasks[reporter._current_task]
        assert task.total == 100_000_000

    def test_percentage_works_after_total_set(self):
        """Once total is set via update(), percentage becomes calculable."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = DownloadReporter(stdout=mock_tty)

        book = Book(title="Pct", authors=["A"], narrators=["N"], isbn="9780000000011")
        reporter.start_download(book, total_bytes=0)

        # First callback sets total (from Content-Length)
        reporter.update(0, total=50_000_000)

        # Now at 50% when half done
        reporter.update(25_000_000)
        task = reporter._progress.tasks[reporter._current_task]
        assert task.percentage == 50.0

    def test_plain_text_update_with_total_is_noop(self):
        """PlainTextReporter.update(completed, total) doesn't break."""
        fake_stdout = io.StringIO()
        reporter = PlainTextReporter(stdout=fake_stdout)

        # Should not raise even with extra kwarg
        reporter.update(12345, total=99999)
        assert len(fake_stdout.getvalue()) == 0  # no output for update


class TestM4BReportsContentLength:
    """download_m4b() reads Content-Length and reports it as total on first callback."""

    def test_m4b_callback_receives_content_length_as_total(self):
        """First progress call includes (completed, content_length) so bar can show %."""
        import httpx
        from pathlib import Path
        from librofm_downloader.downloader import download_m4b

        payload = b"M" * 200  # 200 bytes
        content_length = len(payload)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=payload,
                headers={"content-length": str(content_length)},
            )

        transport = httpx.MockTransport(handler)
        calls: list[tuple[int, int | None]] = []

        def on_progress(completed: int, total: int | None = None) -> None:
            calls.append((completed, total))

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "cl_test.m4b"
            download_m4b(
                url="https://cdn.example.com/cl.m4b",
                output_path=output_path,
                transport=transport,
                progress=on_progress,
            )

        # At least one call should have total set to content_length
        totals_with_cl = [t for _, t in calls if t is not None]
        assert len(totals_with_cl) >= 1
        assert content_length in totals_with_cl
