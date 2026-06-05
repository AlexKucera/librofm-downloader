"""Tests for librofm_downloader.progress — TDD vertical slices (Issue #8)."""

import io
import sys
import tempfile

import pytest

from librofm_downloader.book import Book
from librofm_downloader.downloader import (
    download_m4b,
    download_zip_part,
    download_book,
)
from librofm_downloader.progress import DownloadReporter, PlainTextReporter, ProgressReporter


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
            patch("librofm_downloader.cli.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.cli.DownloadHistory") as mock_history_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "secret"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

            mock_instance = mock_client_cls.return_value
            mock_instance.authenticate.return_value = None

            raw_books = [
                {"isbn": "978111", "title": "Book A", "authors": ["A1"], "narrators": ["N1"]},
                {"isbn": "978222", "title": "Book B", "authors": ["A2"], "narrators": ["N2"]},
                {"isbn": "978333", "title": "Book C", "authors": ["A3"], "narrators": ["N3"]},
            ]
            mock_instance.fetch_library.return_value = raw_books

            mock_history_cls.return_value.is_downloaded.return_value = False

            from librofm_downloader.downloader import DownloadResult

            # Book A succeeds, Book B fails, Book C succeeds
            mock_download.side_effect = [
                DownloadResult(status="downloaded", path=Path("/audiobooks/A1/Book A.m4b"), format="m4b"),  # success
                Exception("Network timeout"),          # failure
                DownloadResult(status="downloaded", path=Path("/audiobooks/A3/Book C.m4b"), format="m4b"),  # success
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
        from librofm_downloader.session import AuthError

        with (
            patch("librofm_downloader.cli.load_config") as mock_config,
            patch("librofm_downloader.cli.LibroFmSession") as mock_client_cls,
            patch("librofm_downloader.cli.download_book") as mock_download,
        ):
            mock_config.return_value.username = "alice"
            mock_config.return_value.password = "wrong"
            mock_config.return_value.output_dir = "./audiobooks"
            mock_config.return_value.workers = 3

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
# Test 7b: ProgressReporter.stop() — halts Rich Live display on interrupt
# ---------------------------------------------------------------------------


class TestProgressReporterStop:
    """ProgressReporter.stop() safely halts the Rich Live display.

    Critical for KeyboardInterrupt handling: stop() must be called before
    any console output to prevent Rich's background thread from corrupting
    interrupt messages with progress bar redraws.
    """

    def test_stop_calls_progress_stop_on_tty_reporter(self):
        """TTY reporter's stop() delegates to rich.Progress.stop()."""
        from unittest.mock import MagicMock, patch

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = DownloadReporter(stdout=mock_tty)
        book = Book(title="StopTest", authors=["A"], narrators=["N"], isbn="9780000000005")
        reporter.start_download(book, total_bytes=100_000_000)

        # Progress should be active
        assert reporter._progress is not None

        # Mock the underlying progress.stop to verify it's called
        original_stop = reporter._progress.stop
        with patch.object(reporter._progress, 'stop', wraps=original_stop) as mock_stop:
            reporter.stop()
            mock_stop.assert_called_once()

    def test_stop_is_idempotent(self):
        """Calling stop() twice doesn't raise (safe for finally blocks)."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = DownloadReporter(stdout=mock_tty)
        book = Book(title="Idempotent", authors=["A"], narrators=["N"], isbn="9780000000006")
        reporter.start_download(book, total_bytes=100_000_000)

        # Should not raise on double-stop
        reporter.stop()
        reporter.stop()  # second call must be safe

    def test_stop_on_plain_text_reporter_is_noop(self):
        """PlainTextReporter.stop() is a safe no-op."""
        import io

        fake_stdout = io.StringIO()
        fake_stdout.isatty = lambda: False

        reporter = DownloadReporter(stdout=fake_stdout)
        book = Book(title="Plain", authors=["A"], narrators=["N"], isbn="9780000000007")
        reporter.start_download(book, total_bytes=100_000_000)

        # Should not raise
        reporter.stop()

    def test_stop_before_any_download_is_safe(self):
        """stop() is safe even when no downloads were started (_progress may be None)."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = DownloadReporter(stdout=mock_tty)
        # _progress is None — haven't started any download yet
        reporter.stop()  # must not raise


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
# Test 8b: Enhanced summary — failed/skipped book details (Issue #9)
# ---------------------------------------------------------------------------


class TestEnhancedSummaryFailedBooks:
    """Summary lists each failed book with ISBN, title, and error reason."""

    def test_summary_lists_failed_books_with_isbn_title_and_reason(self):
        """When books fail, summary shows each one: ISBN, title, reason."""
        fake_stdout = io.StringIO()
        reporter = PlainTextReporter(stdout=fake_stdout)

        book1 = Book(
            title="Broken Book",
            authors=["Some Author"],
            narrators=["N"],
            isbn="9789999999999",
        )
        book2 = Book(
            title="Timeout Book",
            authors=["Other Author"],
            narrators=["N2"],
            isbn="9788888888888",
        )

        reporter.summary(
            downloaded=1,
            skipped=0,
            failed=2,
            failed_books=[(book1, "HTTP 404"), (book2, "Connection timed out")],
        )

        output = fake_stdout.getvalue()
        assert "Summary:" in output
        assert "1 downloaded" in output
        assert "2 failed" in output
        # Each failed book listed with ISBN, title, reason
        assert "9789999999999" in output
        assert "Broken Book" in output
        assert "HTTP 404" in output
        assert "9788888888888" in output
        assert "Timeout Book" in output
        assert "Connection timed out" in output

    def test_summary_no_failed_books_omits_section(self):
        """When no books failed, no failed-book section appears."""
        fake_stdout = io.StringIO()
        reporter = PlainTextReporter(stdout=fake_stdout)

        reporter.summary(
            downloaded=3,
            skipped=0,
            failed=0,
            failed_books=[],
        )

        output = fake_stdout.getvalue()
        assert "3 downloaded" in output
        assert "0 failed" in output
        # No individual failure lines
        assert "  ✗" not in output


class TestEnhancedSummarySkippedBooks:
    """Summary lists each skipped book with ISBN and title."""

    def test_summary_lists_skipped_books_with_isbn_and_title(self):
        """When books are skipped, summary shows each one: ISBN, title."""
        fake_stdout = io.StringIO()
        reporter = PlainTextReporter(stdout=fake_stdout)

        book = Book(
            title="No M4B Book",
            authors=["Author X"],
            narrators=["N"],
            isbn="9787777777777",
        )

        reporter.summary(
            downloaded=2,
            skipped=1,
            failed=0,
            skipped_books=[book],
        )

        output = fake_stdout.getvalue()
        assert "2 downloaded" in output
        assert "1 skipped" in output
        assert "9787777777777" in output
        assert "No M4B Book" in output

    def test_summary_no_skipped_books_omits_section(self):
        """When no books skipped, no skipped-book section appears."""
        fake_stdout = io.StringIO()
        reporter = PlainTextReporter(stdout=fake_stdout)

        reporter.summary(
            downloaded=5,
            skipped=0,
            failed=0,
            skipped_books=[],
        )

        output = fake_stdout.getvalue()
        assert "5 downloaded" in output
        assert "0 skipped" in output


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
        """progress callback from reporter reaches download_m4b chunk loop."""
        import httpx
        from pathlib import Path
        from unittest.mock import MagicMock
        from librofm_downloader.book import Book
        from librofm_downloader.downloader import download_book
        from librofm_downloader.session import LibroFmSession
        from librofm_downloader.path import resolve_output_plan
        from librofm_downloader.progress import DownloadReporter

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
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(title="CB Test", authors=["A"], narrators=["N"], isbn="9781111111111")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"

            plan = resolve_output_plan(book, base_dir)
            reporter = DownloadReporter()
            # Spy on the reporter's update method (used as progress callback)
            reporter.update = MagicMock(wraps=reporter.update)

            download_book(
                book=book,
                session=client,
                plan=plan,
                reporter=reporter,
            )

            # Progress callback was invoked during the M4B download
            assert reporter.update.call_count >= 1
            # Final call reflects the full download size
            last_call_args = reporter.update.call_args_list[-1]
            assert last_call_args[0][0] == len(m4b_payload)


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
        task_id = reporter.start_download(book, total_bytes=0)  # unknown at start

        # Simulate what download_m4b does after reading Content-Length header
        reporter.update(0, total=100_000_000)

        # Task now has a total — percentage can be computed
        task = reporter._progress.tasks[task_id]
        assert task.total == 100_000_000

    def test_percentage_works_after_total_set(self):
        """Once total is set via update(), percentage becomes calculable."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = DownloadReporter(stdout=mock_tty)

        book = Book(title="Pct", authors=["A"], narrators=["N"], isbn="9780000000011")
        task_id = reporter.start_download(book, total_bytes=0)

        # First callback sets total (from Content-Length)
        reporter.update(0, total=50_000_000)

        # Now at 50% when half done
        reporter.update(25_000_000)
        task = reporter._progress.tasks[task_id]
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


# ---------------------------------------------------------------------------
# Issue #9: Enhanced summary — ProgressReporter (rich/TTY) variants
# ---------------------------------------------------------------------------


class TestEnhancedSummaryProgressReporterFailed:
    """ProgressReporter (TTY/rich) summary lists failed books with details."""

    def test_rich_summary_lists_failed_books(self):
        """TTY reporter's summary includes failed book ISBN, title, reason."""
        from io import StringIO

        fake_stdout = StringIO()
        reporter = ProgressReporter(stdout=fake_stdout)

        book = Book(
            title="Rich Fail",
            authors=["R Author"],
            narrators=["N"],
            isbn="9780000000099",
        )

        # Should not raise; ProgressReporter prints via rich Console
        reporter.summary(
            downloaded=0,
            skipped=0,
            failed=1,
            failed_books=[(book, "HTTP 500")],
        )


class TestEnhancedSummaryProgressReporterSkipped:
    """ProgressReporter (TTY/rich) summary lists skipped books."""

    def test_rich_summary_lists_skipped_books(self):
        """TTY reporter's summary includes skipped book ISBN and title."""
        from io import StringIO

        fake_stdout = StringIO()
        reporter = ProgressReporter(stdout=fake_stdout)

        book = Book(
            title="Rich Skip",
            authors=["S Author"],
            narrators=["N"],
            isbn="9780000000088",
        )

        # Should not raise; ProgressReporter prints via rich Console
        reporter.summary(
            downloaded=1,
            skipped=1,
            failed=0,
            skipped_books=[book],
        )


# ---------------------------------------------------------------------------
# Issue #14: Multi-bar progress — per-book identity mapping
# ---------------------------------------------------------------------------


class TestMultiBarProgress:
    """ProgressReporter supports multiple simultaneous progress bars."""

    def test_start_download_returns_task_id(self):
        """start_download() returns a task_id for tracking this book's bar."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = ProgressReporter(stdout=mock_tty)

        book_a = Book(title="Book A", authors=["Author A"], narrators=["N"], isbn="9781111111111")
        task_id_a = reporter.start_download(book_a, total_bytes=100_000_000)

        # start_download should return a task_id (int)
        assert isinstance(task_id_a, int)
        # Progress should have exactly 1 task
        assert len(reporter._progress.tasks) == 1

    def test_two_simultaneous_bars(self):
        """Starting two downloads creates two independent progress tasks."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = ProgressReporter(stdout=mock_tty)

        book_a = Book(title="Book A", authors=["Author A"], narrators=["N"], isbn="9781111111111")
        book_b = Book(title="Book B", authors=["Author B"], narrators=["N"], isbn="9782222222222")

        task_id_a = reporter.start_download(book_a, total_bytes=100_000_000)
        task_id_b = reporter.start_download(book_b, total_bytes=50_000_000)

        # Two distinct task IDs
        assert task_id_a != task_id_b
        # Progress should have exactly 2 active tasks
        assert len(reporter._progress.tasks) == 2

    def test_update_targets_correct_bar_by_task_id(self):
        """update(task_id=X) updates bar X, not the most recently started."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = ProgressReporter(stdout=mock_tty)

        book_a = Book(title="Book A", authors=["Author A"], narrators=["N"], isbn="9781111111111")
        book_b = Book(title="Book B", authors=["Author B"], narrators=["N"], isbn="9782222222222")

        task_id_a = reporter.start_download(book_a, total_bytes=100_000_000)
        task_id_b = reporter.start_download(book_b, total_bytes=50_000_000)

        # Update only book A's bar to 50%
        reporter.update(50_000_000, task_id=task_id_a)

        task_a = reporter._progress.tasks[task_id_a]
        task_b = reporter._progress.tasks[task_id_b]

        assert task_a.completed == 50_000_000
        assert task_b.completed == 0  # Book B untouched

    def test_complete_removes_only_its_bar(self):
        """complete(book_a) removes only A's bar; B's bar stays active."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = ProgressReporter(stdout=mock_tty)

        book_a = Book(title="Book A", authors=["Author A"], narrators=["N"], isbn="9781111111111")
        book_b = Book(title="Book B", authors=["Author B"], narrators=["N"], isbn="9782222222222")

        task_id_a = reporter.start_download(book_a, total_bytes=100_000_000)
        task_id_b = reporter.start_download(book_b, total_bytes=50_000_000)

        assert len(reporter._progress.tasks) == 2

        # Complete only book A
        reporter.complete(book_a)

        # Book A's task is gone, Book B's remains
        assert task_id_a not in reporter._tasks
        assert task_id_b in reporter._tasks
        assert len(reporter._progress.tasks) == 2  # Rich keeps it (completed), but our mapping is clean

    def test_fail_removes_only_its_bar(self):
        """fail(book_b) removes only B's bar; A's bar stays active."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = ProgressReporter(stdout=mock_tty)

        book_a = Book(title="Book A", authors=["Author A"], narrators=["N"], isbn="9781111111111")
        book_b = Book(title="Book B", authors=["Author B"], narrators=["N"], isbn="9782222222222")

        task_id_a = reporter.start_download(book_a, total_bytes=100_000_000)
        task_id_b = reporter.start_download(book_b, total_bytes=50_000_000)

        # Fail only book B
        reporter.fail(book_b, reason="connection reset")

        # Book B's task is gone, Book A's remains
        assert task_id_b not in reporter._tasks
        assert task_id_a in reporter._tasks

    def test_summary_stops_progress_after_all_tasks_done(self):
        """summary() stops progress after all books completed/failed."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = ProgressReporter(stdout=mock_tty)

        book_a = Book(title="Book A", authors=["Author A"], narrators=["N"], isbn="9781111111111")
        book_b = Book(title="Book B", authors=["Author B"], narrators=["N"], isbn="9782222222222")

        reporter.start_download(book_a, total_bytes=100_000_000)
        reporter.start_download(book_b, total_bytes=50_000_000)

        reporter.complete(book_a)
        reporter.fail(book_b, reason="timeout")

        # summary() should not raise and should stop progress
        reporter.summary(downloaded=1, skipped=0, failed=1)

        # After summary, internal mappings are empty (all tasks removed)
        assert len(reporter._tasks) == 0
        assert len(reporter._book_ids) == 0

    def test_update_without_task_id_falls_back_to_most_recent(self):
        """update() without task_id updates the most recently started bar."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = ProgressReporter(stdout=mock_tty)

        book_a = Book(title="Book A", authors=["Author A"], narrators=["N"], isbn="9781111111111")
        book_b = Book(title="Book B", authors=["Author B"], narrators=["N"], isbn="9782222222222")

        task_id_a = reporter.start_download(book_a, total_bytes=100_000_000)
        task_id_b = reporter.start_download(book_b, total_bytes=50_000_000)

        # Update WITHOUT task_id — should fall back to most recent (book_b)
        reporter.update(25_000_000)

        task_b = reporter._progress.tasks[task_id_b]
        task_a = reporter._progress.tasks[task_id_a]

        assert task_b.completed == 25_000_000  # Most recent was updated
        assert task_a.completed == 0  # Older bar untouched

    def test_complete_unknown_book_is_safe(self):
        """complete() on a book that was never started does not raise."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = ProgressReporter(stdout=mock_tty)
        unknown = Book(title="Ghost", authors=["G"], narrators=["N"], isbn="9780000000000")

        # Should not raise
        reporter.complete(unknown)
        assert len(reporter._tasks) == 0

    def test_fail_unknown_book_is_safe(self):
        """fail() on a book that was never started does not raise."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = ProgressReporter(stdout=mock_tty)
        unknown = Book(title="Ghost", authors=["G"], narrators=["N"], isbn="9780000000000")

        # Should not raise
        reporter.fail(unknown, reason="phantom error")
        assert len(reporter._tasks) == 0

class TestMultiBookPlainText:
    """Plain-text reporter with multiple books."""

    def test_multiple_complete_and_fail(self):
        from io import StringIO

        out = StringIO()
        reporter = PlainTextReporter(stdout=out)
        book_a = Book(title="Alpha", authors=["A"], narrators=["N"], isbn="111")
        book_b = Book(title="Beta", authors=["B"], narrators=["N"], isbn="222")

        reporter.start_download(book_a)
        reporter.start_download(book_b)
        reporter.complete(book_a)
        reporter.fail(book_b, reason="network error")

        output = out.getvalue()
        assert "Completed: A - Alpha" in output
        assert "Failed: B - Beta [222] (network error)" in output


class TestParallelProgressCallbackWiring:
    """Regression test: progress callback must carry task_id to update correct bar.

    Bug: when cli.py passes ``progress=reporter.update`` as the callback,
    the downloader calls ``progress(downloaded)`` with no task_id.
    ProgressReporter.update() falls back to ``next(reversed(self._tasks))``,
    so ALL parallel download threads update the same (most recently started) bar.
    """

    def test_update_without_task_id_always_hits_most_recent_bar(self):
        """Demonstrates the bug: untargeted updates all go to the last-started bar."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = ProgressReporter(stdout=mock_tty)

        book_a = Book(title="Book A", authors=["Author A"], narrators=["N"], isbn="9781111111111")
        book_b = Book(title="Book B", authors=["Author B"], narrators=["N"], isbn="9782222222222")
        book_c = Book(title="Book C", authors=["Author C"], narrators=["N"], isbn="9783333333333")

        task_id_a = reporter.start_download(book_a, total_bytes=100_000_000)
        task_id_b = reporter.start_download(book_b, total_bytes=100_000_000)
        task_id_c = reporter.start_download(book_c, total_bytes=100_000_000)

        # Simulate what happens in production: each download thread calls
        # reporter.update(completed) WITHOUT passing task_id — because
        # cli.py wires ``progress=reporter.update`` which loses the identity.
        # Thread A reports 50% progress
        reporter.update(50_000_000)
        # Thread B reports 30% progress
        reporter.update(30_000_000)
        # Thread C reports 80% progress
        reporter.update(80_000_000)

        # BUG: all updates went to the most recently started bar (book_c)
        # because task_id was None every time, triggering the fallback.
        task_a = reporter._progress.tasks[task_id_a]
        task_b = reporter._progress.tasks[task_id_b]
        task_c = reporter._progress.tasks[task_id_c]

        # All three bars show the LAST value written (80M), not their own value
        assert task_c.completed == 80_000_000  # last-started bar got ALL updates
        assert task_a.completed == 0  # book A never got an update  ← THE BUG
        assert task_b.completed == 0  # book B never got an update  ← THE BUG

    def make_progress_callback(self, reporter, task_id):
        """Factory: returns a progress closure bound to a specific task_id.

        This is what cli.py SHOULD do instead of passing ``reporter.update`` directly.
        """
        def _progress(completed, *, total=None):
            reporter.update(completed, total=total, task_id=task_id)
        return _progress

    def test_bound_callback_updates_correct_bar(self):
        """When each thread gets a task_id-bound callback, bars update independently."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = ProgressReporter(stdout=mock_tty)

        book_a = Book(title="Book A", authors=["Author A"], narrators=["N"], isbn="9781111111111")
        book_b = Book(title="Book B", authors=["Author B"], narrators=["N"], isbn="9782222222222")
        book_c = Book(title="Book C", authors=["Author C"], narrators=["N"], isbn="9783333333333")

        task_id_a = reporter.start_download(book_a, total_bytes=100_000_000)
        task_id_b = reporter.start_download(book_b, total_bytes=100_000_1000)
        task_id_c = reporter.start_download(book_c, total_bytes=100_000_000)

        # Each download thread gets its OWN callback, pre-bound to its task_id
        progress_a = self.make_progress_callback(reporter, task_id_a)
        progress_b = self.make_progress_callback(reporter, task_id_b)
        progress_c = self.make_progress_callback(reporter, task_id_c)

        # Each thread reports its own progress
        progress_a(50_000_000)
        progress_b(30_000_000)
        progress_c(80_000_000)

        task_a = reporter._progress.tasks[task_id_a]
        task_b = reporter._progress.tasks[task_id_b]
        task_c = reporter._progress.tasks[task_id_c]

        # Each bar shows ITS OWN progress — this is the fixed behavior
        assert task_a.completed == 50_000_000
        assert task_b.completed == 30_000_000
        assert task_c.completed == 80_000_000
class TestParallelProgressCallbackWiring:
    """Regression test: progress callback must carry task_id to update correct bar.

    Bug: when cli.py passes ``progress=reporter.update`` as the callback,
    the downloader calls ``progress(downloaded)`` with no task_id.
    ProgressReporter.update() falls back to ``next(reversed(self._tasks))``,
    so ALL parallel download threads update the same (most recently started) bar.
    """

    def test_update_without_task_id_always_hits_most_recent_bar(self):
        """Demonstrates the bug: untargeted updates all go to the last-started bar."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = ProgressReporter(stdout=mock_tty)

        book_a = Book(title="Book A", authors=["Author A"], narrators=["N"], isbn="9781111111111")
        book_b = Book(title="Book B", authors=["Author B"], narrators=["N"], isbn="9782222222222")
        book_c = Book(title="Book C", authors=["Author C"], narrators=["N"], isbn="9783333333333")

        task_id_a = reporter.start_download(book_a, total_bytes=100_000_000)
        task_id_b = reporter.start_download(book_b, total_bytes=100_000_000)
        task_id_c = reporter.start_download(book_c, total_bytes=100_000_000)

        # Simulate what happens in production: each download thread calls
        # reporter.update(completed) WITHOUT passing task_id — because
        # cli.py wires ``progress=reporter.update`` which loses the identity.
        # Thread A reports 50% progress
        reporter.update(50_000_000)
        # Thread B reports 30% progress
        reporter.update(30_000_000)
        # Thread C reports 80% progress
        reporter.update(80_000_000)

        # BUG: all updates went to the most recently started bar (book_c)
        # because task_id was None every time, triggering the fallback.
        task_a = reporter._progress.tasks[task_id_a]
        task_b = reporter._progress.tasks[task_id_b]
        task_c = reporter._progress.tasks[task_id_c]

        # All three bars show the LAST value written (80M), not their own value
        assert task_c.completed == 80_000_000  # last-started bar got ALL updates
        assert task_a.completed == 0  # book A never got an update  ← THE BUG
        assert task_b.completed == 0  # book B never got an update  ← THE BUG

    def make_progress_callback(self, reporter, task_id):
        """Factory: returns a progress closure bound to a specific task_id.

        This is what cli.py SHOULD do instead of passing ``reporter.update`` directly.
        """
        def _progress(completed, *, total=None):
            reporter.update(completed, total=total, task_id=task_id)
        return _progress

    def test_bound_callback_updates_correct_bar(self):
        """When each thread gets a task_id-bound callback, bars update independently."""
        from unittest.mock import MagicMock

        mock_tty = MagicMock()
        mock_tty.isatty.return_value = True

        reporter = ProgressReporter(stdout=mock_tty)

        book_a = Book(title="Book A", authors=["Author A"], narrators=["N"], isbn="9781111111111")
        book_b = Book(title="Book B", authors=["Author B"], narrators=["N"], isbn="9782222222222")
        book_c = Book(title="Book C", authors=["Author C"], narrators=["N"], isbn="9783333333333")

        task_id_a = reporter.start_download(book_a, total_bytes=100_000_000)
        task_id_b = reporter.start_download(book_b, total_bytes=100_000_000)
        task_id_c = reporter.start_download(book_c, total_bytes=100_000_000)

        # Each download thread gets its OWN callback, pre-bound to its task_id
        progress_a = self.make_progress_callback(reporter, task_id_a)
        progress_b = self.make_progress_callback(reporter, task_id_b)
        progress_c = self.make_progress_callback(reporter, task_id_c)

        # Each thread reports its own progress
        progress_a(50_000_000)
        progress_b(30_000_000)
        progress_c(80_000_000)

        task_a = reporter._progress.tasks[task_id_a]
        task_b = reporter._progress.tasks[task_id_b]
        task_c = reporter._progress.tasks[task_id_c]

        # Each bar shows ITS OWN progress — this is the fixed behavior
        assert task_a.completed == 50_000_000
        assert task_b.completed == 30_000_000
        assert task_c.completed == 80_000_000

    """PlainTextReporter handles multiple concurrent books correctly."""

    def test_interleaved_start_complete_fail_lines(self):
        """Multiple books produce correctly interleaved start/complete/fail lines."""
        from io import StringIO

        out = StringIO()
        reporter = PlainTextReporter(stdout=out)

        book_a = Book(title="Alpha", authors=["Author A"], narrators=["N"], isbn="9781111111111")
        book_b = Book(title="Beta", authors=["Author B"], narrators=["N"], isbn="9782222222222")
        book_c = Book(title="Gamma", authors=["Author C"], narrators=["N"], isbn="9783333333333")

        # Start all three
        reporter.start_download(book_a, total_bytes=100_000_000)
        reporter.start_download(book_b, total_bytes=50_000_000)
        reporter.start_download(book_c, total_bytes=75_000_000)

        # Complete A, fail B, complete C (interleaved)
        reporter.complete(book_a)
        reporter.fail(book_b, reason="network error")
        reporter.complete(book_c)

        output = out.getvalue()

        # All three downloads started
        assert "Downloading: Author A - Alpha" in output
        assert "Downloading: Author B - Beta" in output
        assert "Downloading: Author C - Gamma" in output

        # Completions and failures present
        assert "Completed: Author A - Alpha" in output
        assert "Completed: Author C - Gamma" in output
        assert "Failed: Author B - Beta [9782222222222] (network error)" in output