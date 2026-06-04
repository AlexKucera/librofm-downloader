"""Tests for librofm_downloader.orchestrator — Issue #16.

TDD vertical slices: ThreadPoolExecutor-based parallel download orchestration.
All tests use an injected download_fn — no network or filesystem required.
"""

from pathlib import Path

import pytest

from librofm_downloader.book import Book
from librofm_downloader.orchestrator import OrchestratorResult, download_all_books


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_raw_book(
    isbn: str = "9781234567890",
    title: str = "Test Book",
    authors: list[str] | None = None,
    narrators: list[str] | None = None,
    **extra,
) -> dict:
    """Build a raw book dict matching Libro.fm API shape."""
    return {
        "isbn": isbn,
        "title": title,
        "authors": authors or ["Author A"],
        "narrators": narrators or ["Narrator X"],
        "cover_url": "",
        "series": "",
        **extra,
    }


class FakeReporter:
    """Captures reporter callbacks for assertion."""

    def __init__(self) -> None:
        self.started: list[Book] = []
        self.completed: list[Book] = []
        self.failed: list[tuple[Book, str]] = []

    def start_download(self, book: Book, total_bytes: int = 0) -> None:
        self.started.append(book)

    def complete(self, book: Book) -> None:
        self.completed.append(book)

    def fail(self, book: Book, reason: str = "") -> None:
        self.failed.append((book, reason))

    def stop(self) -> None:
        """No-op for test reporter."""

    def summary(self, **kwargs) -> None:
        pass  # no-op for unit tests


# ---------------------------------------------------------------------------
# Test 1: Tracer bullet — workers=1 sequential parity
# ---------------------------------------------------------------------------


class TestSequentialParity:
    """workers=1 processes every book exactly once, in order."""

    def test_single_book_downloaded(self):
        """One book, workers=1 → downloaded_count=1, no failures."""
        results: list[Path | None] = []

        def download_fn(book: Book, **_kwargs) -> Path | None:
            results.append(Path(f"/fake/{book.isbn}.m4b"))
            return results[-1]

        raw_books = [_make_raw_book(isbn="978111", title="Only Book")]

        result = download_all_books(
            raw_books,
            workers=1,
            download_fn=download_fn,
            reporter=FakeReporter(),
        )

        assert result.downloaded_count == 1
        assert result.skipped_count == 0
        assert result.failed_count == 0
        assert len(results) == 1

    def test_three_books_all_downloaded_sequential(self):
        """Three books, workers=1 → all 3 downloaded, counts correct."""
        results: list[Path | None] = []

        def download_fn(book: Book, **_kwargs) -> Path | None:
            p = Path(f"/fake/{book.isbn}.m4b")
            results.append(p)
            return p

        raw_books = [
            _make_raw_book(isbn="978111", title="Book A"),
            _make_raw_book(isbn="978222", title="Book B"),
            _make_raw_book(isbn="978333", title="Book C"),
        ]

        result = download_all_books(
            raw_books,
            workers=1,
            download_fn=download_fn,
            reporter=FakeReporter(),
        )

        assert result.downloaded_count == 3
        assert result.skipped_count == 0
        assert result.failed_count == 0
        assert len(results) == 3


# ---------------------------------------------------------------------------
# Test 2: Skipped books — download_fn returns None
# ---------------------------------------------------------------------------


class TestSkippedBooks:
    """Books where download_fn returns None are counted as skipped."""

    def test_skipped_book_returned_in_result(self):
        """download_fn returning None → skipped_count=1, book in skipped_books."""
        def download_fn(book: Book, **_kwargs) -> Path | None:
            return None  # no format available

        raw_books = [_make_raw_book(isbn="978111", title="Skip Me")]

        result = download_all_books(
            raw_books,
            workers=1,
            download_fn=download_fn,
            reporter=FakeReporter(),
        )

        assert result.skipped_count == 1
        assert result.downloaded_count == 0
        assert result.failed_count == 0
        assert len(result.skipped_books) == 1
        assert result.skipped_books[0].isbn == "978111"
        assert result.skipped_books[0].title == "Skip Me"

    def test_mixed_download_and_skip(self):
        """2 succeed, 1 skipped → correct counts and lists."""
        def download_fn(book: Book, **_kwargs) -> Path | None:
            if book.isbn == "978222":
                return None  # skip this one
            return Path(f"/fake/{book.isbn}.m4b")

        raw_books = [
            _make_raw_book(isbn="978111", title="Download A"),
            _make_raw_book(isbn="978222", title="Skip B"),
            _make_raw_book(isbn="978333", title="Download C"),
        ]

        result = download_all_books(
            raw_books,
            workers=1,
            download_fn=download_fn,
            reporter=FakeReporter(),
        )

        assert result.downloaded_count == 2
        assert result.skipped_count == 1
        assert result.failed_count == 0
        assert len(result.skipped_books) == 1
        assert result.skipped_books[0].isbn == "978222"


# ---------------------------------------------------------------------------
# Test 3: Failed books — download_fn raises exception
# ---------------------------------------------------------------------------


class TestFailedBooks:
    """Books where download_fn raises are counted as failures with (book, reason)."""

    def test_failed_book_with_reason_tuple(self):
        """Exception → failed_count=1, (book, reason_string) in failed_books."""
        def download_fn(book: Book, **_kwargs) -> Path | None:
            raise ConnectionError("CDN unreachable")

        raw_books = [_make_raw_book(isbn="978111", title="Fail Book")]

        result = download_all_books(
            raw_books,
            workers=1,
            download_fn=download_fn,
            reporter=FakeReporter(),
        )

        assert result.failed_count == 1
        assert result.downloaded_count == 0
        assert result.skipped_count == 0
        assert len(result.failed_books) == 1
        failed_book, reason = result.failed_books[0]
        assert failed_book.isbn == "978111"
        assert failed_book.title == "Fail Book"
        assert "CDN unreachable" in reason

    def test_mixed_success_skip_fail(self):
        """1 downloads, 1 skips, 1 fails → all three buckets populated."""
        def download_fn(book: Book, **_kwargs) -> Path | None:
            if book.isbn == "978222":
                return None
            if book.isbn == "978333":
                raise TimeoutError("download timed out")
            return Path(f"/fake/{book.isbn}.m4b")

        raw_books = [
            _make_raw_book(isbn="978111", title="OK"),
            _make_raw_book(isbn="978222", title="Skipped"),
            _make_raw_book(isbn="978333", title="Failed"),
        ]

        result = download_all_books(
            raw_books,
            workers=1,
            download_fn=download_fn,
            reporter=FakeReporter(),
        )

        assert result.downloaded_count == 1
        assert result.skipped_count == 1
        assert result.failed_count == 1
        assert result.failed_books[0][0].isbn == "978333"
        assert result.skipped_books[0].isbn == "978222"


# ---------------------------------------------------------------------------
# Test 4: Stable sort — results preserve original library order
# ---------------------------------------------------------------------------


class TestStableOrdering:
    """Results within each group are sorted by original library index."""

    def test_failed_books_sorted_by_original_order(self):
        """With concurrent execution, failures complete out-of-order but result is sorted."""
        import time

        # Book at index 0 takes longer to fail than book at index 1
        # This proves stable sort, not completion-order sort
        def download_fn(book: Book, **_kwargs) -> Path | None:
            if book.isbn == "978111":
                time.sleep(0.05)  # index 0 is slower
            raise RuntimeError(f"fail {book.isbn}")

        raw_books = [
            _make_raw_book(isbn="978111", title="Slow Fail"),   # index 0
            _make_raw_book(isbn="978222", title="Fast Fail"),   # index 1
        ]

        result = download_all_books(
            raw_books,
            workers=2,  # concurrent so they overlap
            download_fn=download_fn,
            reporter=FakeReporter(),
        )

        assert result.failed_count == 2
        # Index 0 should come first despite completing second
        assert result.failed_books[0][0].isbn == "978111"
        assert result.failed_books[1][0].isbn == "978222"

    def test_skipped_books_sorted_by_original_order(self):
        """Skipped books maintain original library order."""
        def download_fn(book: Book, **_kwargs) -> Path | None:
            return None

        raw_books = [
            _make_raw_book(isbn="978111", title="First"),
            _make_raw_book(isbn="978222", title="Second"),
            _make_raw_book(isbn="978333", title="Third"),
        ]

        result = download_all_books(
            raw_books,
            workers=3,
            download_fn=download_fn,
            reporter=FakeReporter(),
        )

        assert [b.isbn for b in result.skipped_books] == ["978111", "978222", "978333"]


# ---------------------------------------------------------------------------
# Test 5: Concurrency — workers > 1 runs downloads in parallel
# ---------------------------------------------------------------------------


class TestConcurrency:
    """workers=N actually runs downloads concurrently."""

    def test_workers_three_runs_concurrently(self):
        """3 books with workers=3 → all overlap (total time < sequential)."""
        import signal
        import signal
        import threading
        import time

        start_times: list[float] = []
        lock = threading.Lock()

        def download_fn(book: Book, **_kwargs) -> Path | None:
            with lock:
                start_times.append(time.monotonic())
            time.sleep(0.05)  # simulate work
            return Path(f"/fake/{book.isbn}.m4b")

        raw_books = [
            _make_raw_book(isbn=f"97800{i}", title=f"Book {i}")
            for i in range(3)
        ]

        wall_start = time.monotonic()
        result = download_all_books(
            raw_books,
            workers=3,
            download_fn=download_fn,
            reporter=FakeReporter(),
        )
        wall_elapsed = time.monotonic() - wall_start

        assert result.downloaded_count == 3
        # All 3 started near-simultaneously (within 20ms of each other)
        assert max(start_times) - min(start_times) < 0.02
        # Total wall time should be ~0.05s (parallel), not ~0.15s (sequential)
        assert wall_elapsed < 0.12


# ---------------------------------------------------------------------------
# Test 6: Failure isolation — one failure doesn't block siblings
# ---------------------------------------------------------------------------


class TestFailureIsolation:
    """A failing future does not cancel or block sibling futures."""

    def test_one_failure_does_not_block_others(self):
        """2nd book fails; 1st and 3rd still succeed."""
        results: list[str] = []

        def download_fn(book: Book, **_kwargs) -> Path | None:
            if book.isbn == "978222":
                raise RuntimeError("boom")
            results.append(book.isbn)
            return Path(f"/fake/{book.isbn}.m4b")

        raw_books = [
            _make_raw_book(isbn="978111", title="OK A"),
            _make_raw_book(isbn="978222", title="BOOM"),
            _make_raw_book(isbn="978333", title="OK B"),
        ]

        result = download_all_books(
            raw_books,
            workers=3,
            download_fn=download_fn,
            reporter=FakeReporter(),
        )

        assert result.downloaded_count == 2
        assert result.failed_count == 1
        assert set(results) == {"978111", "978333"}

    def test_all_siblings_complete_despite_early_failure(self):
        """Even when one fails immediately, others run to completion."""
        import time

        completed_isbns: list[str] = []

        def download_fn(book: Book, **_kwargs) -> Path | None:
            if book.isbn == "978111":
                raise RuntimeError("instant fail")
            time.sleep(0.03)  # other books take time
            completed_isbns.append(book.isbn)
            return Path(f"/fake/{book.isbn}.m4b")

        raw_books = [
            _make_raw_book(isbn="978111", title="Instant Fail"),
            _make_raw_book(isbn="978222", title="Slow A"),
            _make_raw_book(isbn="978333", title="Slow B"),
        ]

        result = download_all_books(
            raw_books,
            workers=3,
            download_fn=download_fn,
            reporter=FakeReporter(),
        )

        assert result.downloaded_count == 2
        assert result.failed_count == 1
        assert set(completed_isbns) == {"978222", "978333"}


# ---------------------------------------------------------------------------
# Test 7: Callback wiring — download_fn called correctly
# ---------------------------------------------------------------------------


class TestCallbackWiring:
    """download_fn is called exactly once per book with correct Book object."""

    def test_download_fn_called_once_per_book(self):
        """Each book triggers exactly one download_fn call."""
        calls: list[Book] = []

        def download_fn(book: Book, **_kwargs) -> Path | None:
            calls.append(book)
            return Path(f"/fake/{book.isbn}.m4b")

        raw_books = [
            _make_raw_book(isbn="978111", title="A", authors=["Auth1"]),
            _make_raw_book(isbn="978222", title="B", authors=["Auth2"]),
            _make_raw_book(isbn="978333", title="C", authors=["Auth3"]),
        ]

        download_all_books(
            raw_books,
            workers=2,
            download_fn=download_fn,
            reporter=FakeReporter(),
        )

        assert len(calls) == 3
        # Each book was called exactly once (order non-deterministic with workers > 1)
        call_isbns = {b.isbn for b in calls}
        assert call_isbns == {"978111", "978222", "978333"}

    def test_book_object_has_correct_fields(self):
        """The Book passed to download_fn has all fields from raw dict."""
        captured_book: Book | None = None

        def download_fn(book: Book, **_kwargs) -> Path | None:
            nonlocal captured_book
            captured_book = book
            return Path("/fake/book.m4b")

        raw_books = [_make_raw_book(
            isbn="9789990001111",
            title="Deep Work",
            authors=["Cal Newport"],
            narrators=["David M. Rose"],
            series="Productivity",
            series_num=3,
            cover_url="https://covers.libro.fm/cover.jpg",
        )]

        download_all_books(
            raw_books,
            workers=1,
            download_fn=download_fn,
            reporter=FakeReporter(),
        )

        assert captured_book is not None
        assert captured_book.title == "Deep Work"
        assert captured_book.authors == ["Cal Newport"]
        assert captured_book.narrators == ["David M. Rose"]
        assert captured_book.series == "Productivity"
        assert captured_book.series_num == 3


# ---------------------------------------------------------------------------
# Test 8: Reporter callbacks fire correctly
# ---------------------------------------------------------------------------


class TestReporterCallbacks:
    """Reporter start/complete/fail callbacks fire per book based on outcome."""

    def test_successful_book_triggers_start_and_complete(self):
        """Download success → start_download + complete (no fail)."""
        reporter = FakeReporter()

        def download_fn(book: Book, **_kwargs) -> Path | None:
            return Path(f"/fake/{book.isbn}.m4b")

        raw_books = [_make_raw_book(isbn="978111", title="OK")]

        download_all_books(
            raw_books,
            workers=1,
            download_fn=download_fn,
            reporter=reporter,
        )

        assert len(reporter.started) == 1
        assert len(reporter.completed) == 1
        assert len(reporter.failed) == 0

    def test_skipped_book_triggers_start_and_complete_not_fail(self):
        """Skipped book (None return) → start + complete, not fail."""
        reporter = FakeReporter()

        def download_fn(book: Book, **_kwargs) -> Path | None:
            return None

        raw_books = [_make_raw_book(isbn="978111", title="Skip")]

        download_all_books(
            raw_books,
            workers=1,
            download_fn=download_fn,
            reporter=reporter,
        )

        assert len(reporter.started) == 1
        assert len(reporter.completed) == 1
        assert len(reporter.failed) == 0

    def test_failed_book_triggers_start_and_fail_not_complete(self):
        """Exception → start + fail (no complete)."""
        reporter = FakeReporter()

        def download_fn(book: Book, **_kwargs) -> Path | None:
            raise ConnectionError("network error")

        raw_books = [_make_raw_book(isbn="978111", title="Fail")]

        download_all_books(
            raw_books,
            workers=1,
            download_fn=download_fn,
            reporter=reporter,
        )

        assert len(reporter.started) == 1
        assert len(reporter.completed) == 0
        assert len(reporter.failed) == 1
        assert "network error" in reporter.failed[0][1]

    def test_mixed_results_fire_correct_callbacks(self):
        """2 ok, 1 skip, 1 fail → correct callback counts."""
        reporter = FakeReporter()

        def download_fn(book: Book, **_kwargs) -> Path | None:
            if book.isbn == "978222":
                return None
            if book.isbn == "978333":
                raise ValueError("bad data")
            return Path(f"/fake/{book.isbn}.m4b")

        raw_books = [
            _make_raw_book(isbn="978111", title="A"),
            _make_raw_book(isbn="978222", title="B"),
            _make_raw_book(isbn="978333", title="C"),
            _make_raw_book(isbn="978444", title="D"),
        ]

        result = download_all_books(
            raw_books,
            workers=4,
            download_fn=download_fn,
            reporter=reporter,
        )

        assert len(reporter.started) == 4
        assert len(reporter.completed) == 3  # A, B (skip→complete), D
        assert len(reporter.failed) == 1  # C


# ---------------------------------------------------------------------------
# Test 9: Edge cases — empty list, all-fail, all-skip
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Boundary conditions for the orchestrator."""

    def test_empty_book_list_returns_zero_result(self):
        """No books → OrchestratorResult with all zeros and empty lists."""
        def download_fn(book: Book, **_kwargs) -> Path | None:
            raise AssertionError("should never be called")  # noqa: TRY003

        result = download_all_books(
            [],
            workers=3,
            download_fn=download_fn,
            reporter=FakeReporter(),
        )

        assert isinstance(result, OrchestratorResult)
        assert result.downloaded_count == 0
        assert result.skipped_count == 0
        assert result.failed_count == 0
        assert result.failed_books == []
        assert result.skipped_books == []

    def test_all_books_fail(self):
        """Every book raises → failed_count=N, others zero."""
        def download_fn(book: Book, **_kwargs) -> Path | None:
            raise RuntimeError(f"fail {book.isbn}")

        raw_books = [
            _make_raw_book(isbn=f"97800{i}", title=f"Fail {i}")
            for i in range(4)
        ]

        result = download_all_books(
            raw_books,
            workers=2,
            download_fn=download_fn,
            reporter=FakeReporter(),
        )

        assert result.failed_count == 4
        assert result.downloaded_count == 0
        assert result.skipped_count == 0
        # All ISBNs present in failed books, in original order
        assert [b.isbn for b, _ in result.failed_books] == [
            "978000", "978001", "978002", "978003",
        ]

    def test_all_books_skipped(self):
        """Every book returns None → skipped_count=N."""
        def download_fn(book: Book, **_kwargs) -> Path | None:
            return None

        raw_books = [
            _make_raw_book(isbn=f"97800{i}", title=f"Skip {i}")
            for i in range(3)
        ]

        result = download_all_books(
            raw_books,
            workers=2,
            download_fn=download_fn,
            reporter=FakeReporter(),
        )

        assert result.skipped_count == 3
        assert result.downloaded_count == 0
        assert result.failed_count == 0


# ---------------------------------------------------------------------------
# Issue #17: Graceful Ctrl+C drain — orchestrator-level tests
# ---------------------------------------------------------------------------


class TestCtrlCDrain:
    """KeyboardInterrupt during parallel downloads triggers graceful drain.

    - Catches KeyboardInterrupt inside the executor block
    - Prints 'Aborting...'
    - Drains in-flight downloads (shutdown(wait=True))
    - Returns partial result or re-raises for CLI to handle exit code
    """

    def test_ctrl_c_returns_partial_result_with_completed_downloads(self):
        """Worker-thread exceptions are wrapped as failures, returns partial result.

        _download_one uses except BaseException so all exceptions including
        BaseException subclasses are captured and returned as error tuples.
        """
        import threading

        cancel_event = threading.Event()

        def download_fn(book: Book, **_kwargs) -> Path | None:
            if book.isbn == "978111":
                raise RuntimeError("Simulated download failure")
            return Path(f"/fake/{book.isbn}.m4b")

        raw_books = [
            _make_raw_book(isbn="978111", title="Failed Book"),
            _make_raw_book(isbn="978222", title="OK"),
        ]

        result = download_all_books(
            raw_books,
            workers=2,
            download_fn=download_fn,
            reporter=FakeReporter(),
            cancel_event=cancel_event,
        )

        assert result.failed_count == 1
        assert result.downloaded_count == 1
        failed_isbns = [book.isbn for (book, reason) in result.failed_books]
        assert "978111" in failed_isbns
    def test_ctrl_c_calls_reporter_stop_before_messages(self):
        """Real SIGINT must call reporter.stop() before printing any message.

        This prevents Rich's Live display thread from corrupting interrupt output.
        Uses real SIGINT delivery (not worker-thread exception) to test the actual path.
        """
        import signal
        import threading
        import time
        import os

        cancel_event = threading.Event()

        class SpyReporter:
            def __init__(self) -> None:
                self.stop_called = False

            def start_download(self, book, total_bytes: int = 0) -> None:
                pass

            def complete(self, book) -> None:
                pass

            def fail(self, book, reason: str = "") -> None:
                pass

            def stop(self) -> None:
                self.stop_called = True

            def summary(self, **kwargs) -> None:
                pass

        def slow_download_fn(book: Book) -> Path | None:
            for _ in range(50):
                time.sleep(0.1)
                if cancel_event.is_set():
                    break
            return Path(f"/fake/{book.isbn}.m4b")

        raw_books = [_make_raw_book(isbn="978111", title="Slow")]
        reporter = SpyReporter()

        def send_sigint():
            time.sleep(0.1)
            os.kill(os.getpid(), signal.SIGINT)

        original_handler = signal.getsignal(signal.SIGINT)
        try:
            t = threading.Thread(target=send_sigint, daemon=True)
            t.start()

            result = download_all_books(
                raw_books,
                workers=1,
                download_fn=slow_download_fn,
                reporter=reporter,
                cancel_event=cancel_event,
            )
            t.join(timeout=2)
        finally:
            signal.signal(signal.SIGINT, original_handler)

        assert reporter.stop_called is True, (
            "reporter.stop() was not called during SIGINT handling"
        )

    def test_double_ctrl_c_during_drain_exits_immediately(self):
        """Second SIGINT during cooperative drain forces immediate KeyboardInterrupt exit.

        The cooperative drain waits up to 2 seconds for tasks to notice
        cancel_event. A second SIGINT during that window bypasses the wait
        and raises KeyboardInterrupt immediately.
        """
        import signal
        import threading
        import time
        import os

        cancel_event = threading.Event()
        force_exit_event = threading.Event()

        def slow_download_fn(book: Book) -> Path | None:
            # Check cancel_event to allow cooperative cancellation to start
            for _ in range(100):
                time.sleep(0.1)
                if cancel_event.is_set():
                    force_exit_event.wait(timeout=1.0)
            return Path(f"/fake/{book.isbn}.m4b")

        raw_books = [_make_raw_book(isbn="978111", title="Slow")]

        interrupts_sent = [0]

        def send_interrupts():
            time.sleep(0.05)  # let download start
            os.kill(os.getpid(), signal.SIGINT)  # first Ctrl+C → starts drain
            interrupts_sent[0] += 1
            time.sleep(0.2)  # wait for drain to begin (inside f.result timeout loop)
            os.kill(os.getpid(), signal.SIGINT)  # second Ctrl+C → force quit
            interrupts_sent[0] += 1

        def fake_hard_exit(code: int) -> None:
            force_exit_event.set()
            raise SystemExit(code)
        original_handler = signal.getsignal(signal.SIGINT)
        try:
            t = threading.Thread(target=send_interrupts, daemon=True)
            t.start()

            start = time.monotonic()
            with pytest.raises(SystemExit) as exc_info:
                download_all_books(
                    raw_books,
                    workers=1,
                    download_fn=slow_download_fn,
                    reporter=FakeReporter(),
                    cancel_event=cancel_event,
                    hard_exit=fake_hard_exit,
                )

            elapsed = time.monotonic() - start
            assert elapsed < 5.0, f"Double-Ctrl+C took {elapsed:.1f}s — should exit quickly"
            assert interrupts_sent[0] == 2, "Both SIGINTs should have been sent"
            assert exc_info.value.code == 130
        finally:
            signal.signal(signal.SIGINT, original_handler)
    def test_cooperative_cancel_stops_downloads_promptly(self):
        """When cancel_event is set during download, orchestrator cancels pending work.

        Verifies that:
        - Pending (not-yet-started) futures are cancelled
        - The function returns promptly (doesn't wait for full queue)
        - Partial results are returned for completed downloads
        """
        import threading
        import time

        cancel_event = threading.Event()
        completed_isbns: list[str] = []
        download_order: list[str] = []

        def tracking_download_fn(book: Book) -> Path | None:
            download_order.append(book.isbn)
            # Simulate work that checks cancel_event
            if book.isbn == "978111":
                # First book: completes before cancellation
                time.sleep(0.01)
                completed_isbns.append(book.isbn)
                return Path(f"/fake/{book.isbn}.m4b")
            else:
                # Other books: check cancel_event and exit if set
                time.sleep(0.05)  # long enough for cancel to fire
                if cancel_event.is_set():
                    from librofm_downloader.downloader import InterruptedDownload
                    raise InterruptedDownload(f"Cancelled {book.isbn}")
                completed_isbns.append(book.isbn)
                return Path(f"/fake/{book.isbn}.m4b")

        raw_books = [
            _make_raw_book(isbn="978111", title="Fast Book"),
            _make_raw_book(isbn="978222", title="Slow Book 1"),
            _make_raw_book(isbn="978333", title="Slow Book 2"),
        ]

        # Set cancel after first book starts but before others complete
        def set_cancel_soon():
            time.sleep(0.02)  # let first book start
            cancel_event.set()

        t = threading.Thread(target=set_cancel_soon, daemon=True)
        t.start()

        result = download_all_books(
            raw_books,
            workers=1,  # sequential to make ordering predictable
            download_fn=tracking_download_fn,
            reporter=FakeReporter(),
            cancel_event=cancel_event,
        )

        t.join(timeout=2)

        # First book should have completed
        assert "978111" in completed_isbns, "First book should complete before cancel"
        # Should NOT have waited for all 3 books
        assert len(completed_isbns) < 3, (
            f"Cooperative cancel should stop early; got {len(completed_isbns)} completions"
        )