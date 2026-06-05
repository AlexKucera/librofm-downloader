"""Tests for librofm_downloader.downloader — TDD vertical slices."""

import httpx
import pytest
import unittest
from pathlib import Path
import tempfile

from librofm_downloader.book import Book
from librofm_downloader.path import (
    sanitize,
    resolve_path,
    needs_subdirectory,
    _resolve_output_dir,
    OutputPlan,
    resolve_output_plan,
)
from librofm_downloader.downloader import (
    DownloadResult,
    _write_history,
    download_m4b,
    download_zip_part,
    download_book,
    download_accompanying_files,
    rename_chapters,
)
from librofm_downloader.progress import DownloadReporter
from librofm_downloader.session import LibroFmSession
from librofm_downloader.history import DownloadHistory


# ---------------------------------------------------------------------------
# Issue #29: DownloadResult dataclass
# ---------------------------------------------------------------------------


class TestDownloadResult:
    """DownloadResult frozen dataclass — shape and immutability."""

    def test_instantiates_with_each_status_value(self):
        """All three status values produce valid instances."""
        downloaded = DownloadResult(status="downloaded", path=Path("/tmp/a.m4b"), format="m4b")
        skipped = DownloadResult(status="skipped")
        failed = DownloadResult(status="failed", error="network error")

        assert downloaded.status == "downloaded"
        assert skipped.status == "skipped"
        assert failed.status == "failed"

    def test_optional_fields_default_to_none(self):
        """path, format, error all default to None when omitted."""
        result = DownloadResult(status="skipped")

        assert result.path is None
        assert result.format is None
        assert result.error is None

    def test_is_frozen(self):
        """Assigning to an attribute raises FrozenInstanceError."""
        from dataclasses import FrozenInstanceError

        result = DownloadResult(status="downloaded")
        with pytest.raises(FrozenInstanceError):
            result.status = "failed"  # type: ignore[misc]

    def test_all_four_fields_present_on_downloaded_result(self):
        """A fully-populated 'downloaded' result has all fields set."""
        result = DownloadResult(
            status="downloaded",
            path=Path("/out/book.m4b"),
            format="m4b",
        )

        assert result.status == "downloaded"
        assert result.path == Path("/out/book.m4b")
        assert result.format == "m4b"
        assert result.error is None

    def test_failed_result_carries_error_message(self):
        """A 'failed' result includes the error string."""
        result = DownloadResult(
            status="failed",
            error="HTTP 500 Internal Server Error",
        )

        assert result.status == "failed"
        assert result.path is None
        assert result.format is None
        assert result.error == "HTTP 500 Internal Server Error"


class TestDownloadBookNewInterface:
    """download_book() with 4 domain-aligned params returning DownloadResult."""

    def test_returns_download_result_on_successful_m4b(self):
        """New 4-param signature returns DownloadResult(status='downloaded') for M4B."""
        import io

        m4b_payload = b"new-interface-test-data"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/audiobooks/9781111111111/packaged_m4b":
                return httpx.Response(
                    200,
                    json={"m4b_url": "https://cdn.example.com/book.m4b"},
                )
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=m4b_payload)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(
            title="Interface Test Book",
            authors=["Test Author"],
            narrators=["Test Narr"],
            isbn="9781111111111",
        )

        from librofm_downloader.progress import DownloadReporter

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            plan = resolve_output_plan(book, base_dir, format_strategy="m4b_mp3_fallback")
            reporter = DownloadReporter()

            result = download_book(book, client, plan, reporter)

            # Returns DownloadResult, not Path | None
            assert isinstance(result, DownloadResult)
            assert result.status == "downloaded"
            assert result.path is not None
            assert result.path.exists()
            assert result.format == "m4b"

    def test_uses_provided_progress_callback_over_reporter_update(self):
        """When progress= is passed, download_book uses it instead of reporter.update.

        Issue #30: The orchestrator passes a bound callable from start_download().
        download_book must thread it through to the chunk loop, not ignore it.
        """
        import httpx
        from unittest.mock import MagicMock
        from librofm_downloader.downloader import download_book

        m4b_payload = b"progress-callback-test-data" * 10  # 240 bytes
        received: list[int] = []

        def my_callback(completed: int, *, total: int | None = None) -> None:
            received.append(completed)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok", "token_type": "bearer", "expires_in": 7200},
                )
            if "/packaged_m4b" in request.url.path:
                return httpx.Response(
                    200,
                    json={"m4b_url": "https://cdn.example.com/book.m4b"},
                )
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=m4b_payload, headers={"Content-Length": str(len(m4b_payload))})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        session = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        session.authenticate()

        book = Book(title="Callback Test", authors=["Author"], narrators=["N"], isbn="9789900000000")
        reporter = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            plan = resolve_output_plan(book, Path(tmpdir), format_strategy="m4b_only")
            result = download_book(book, session, plan, reporter, progress=my_callback)

            assert result.status == "downloaded"
            # Our callback should have been called (not reporter.update)
            assert len(received) >= 1, "Bound callback should receive progress updates"
            # reporter.update should NOT have been called
            reporter.update.assert_not_called()

class TestSanitizeIllegalChars:
    """Sanitization strips characters that are unsafe in filesystem paths."""

    def test_strips_angle_brackets(self):
        assert sanitize("Foo<Bar>") == "FooBar"

    def test_strips_forward_slash(self):
        assert sanitize("Foo/Bar") == "FooBar"

    def test_strips_backslash(self):
        assert sanitize("Foo\\Bar") == "FooBar"

    def test_strips_pipe(self):
        assert sanitize("Foo|Bar") == "FooBar"

    def test_strips_question_mark(self):
        assert sanitize("Foo?Bar") == "FooBar"

    def test_strips_asterisk(self):
        assert sanitize("Foo*Bar") == "FooBar"


class TestSanitizeColonReplacement:
    """Colons are replaced with ' -' (space-dash), not stripped."""

    def test_single_colon_replaced(self):
        assert sanitize("Part A: Part B") == "Part A - Part B"

    def test_multiple_colons_replaced(self):
        assert sanitize("A:B:C") == "A -B -C"

    def test_colon_with_illegal_chars(self):
        # Colon replaced first, then illegal chars stripped
        assert sanitize("Foo:<>Bar") == "Foo -Bar"


class TestSanitizeControlChars:
    """Control characters U+0000–U+001F are stripped."""

    def test_strips_null_byte(self):
        assert sanitize("Foo\x00Bar") == "FooBar"

    def test_strips_tab(self):
        assert sanitize("Foo\tBar") == "FooBar"

    def test_strips_newline(self):
        assert sanitize("Foo\nBar") == "FooBar"

    def test_strips_carriage_return(self):
        assert sanitize("Foo\rBar") == "FooBar"

    def test_strips_multiple_control_chars(self):
        assert sanitize("\x01\x02Hello\x1F\x1E") == "Hello"


class TestSanitizeTrailingDots:
    """Trailing dots are removed (problematic on Windows)."""

    def test_removes_single_trailing_dot(self):
        assert sanitize("filename.") == "filename"

    def test_removes_multiple_trailing_dots(self):
        assert sanitize("filename...") == "filename"

    def test_preserves_internal_dots(self):
        assert sanitize("file.name.txt") == "file.name.txt"

    def test_trailing_dot_after_whitespace_trim(self):
        assert sanitize("  filename.  ") == "filename"


class TestSanitizeTrimWhitespace:
    """Leading and trailing whitespace is trimmed."""

    def test_trims_leading_space(self):
        assert sanitize("  filename") == "filename"

    def test_trims_trailing_space(self):
        assert sanitize("filename  ") == "filename"

    def test_trims_both_ends(self):
        assert sanitize("  filename  ") == "filename"

    def test_preserves_internal_spaces(self):
        assert sanitize("my filename") == "my filename"


class TestSanitizeLengthCap:
    """Components are capped at 255 characters."""

    def test_short_string_unchanged(self):
        short = "a" * 100
        assert sanitize(short) == short

    def test_capped_at_255_chars(self):
        long = "a" * 300
        assert len(sanitize(long)) == 255

    def test_exact_255_unchanged(self):
        exact = "a" * 255
        assert len(sanitize(exact)) == 255


class TestSanitizePreservedChars:
    """Safe characters that must be preserved through sanitization."""

    def test_preserves_dashes(self):
        assert sanitize("some-name") == "some-name"

    def test_preserves_commas(self):
        assert sanitize("Last, First") == "Last, First"

    def test_preserves_apostrophes(self):
        assert sanitize("O'Brien") == "O'Brien"

    def test_preserves_parentheses(self):
        assert sanitize("Book (subtitle)") == "Book (subtitle)"

    def test_preserves_internal_periods(self):
        assert sanitize("Dr. Jekyll") == "Dr. Jekyll"

    def test_combined_safe_and_unsafe(self):
        assert sanitize("O'Brien, Pat (Author): A Life*") == "O'Brien, Pat (Author) - A Life"


class TestSanitizeEdgeCases:
    """Edge cases: empty strings, unicode, all-illegal input."""

    def test_empty_string_returns_empty(self):
        assert sanitize("") == ""

    def test_only_illegal_chars_returns_empty(self):
        assert sanitize("<>/\\|?*") == ""

    def test_only_whitespace_returns_empty(self):
        assert sanitize("   ") == ""

    def test_unicode_preserved(self):
        assert sanitize("日本語タイトル") == "日本語タイトル"

    def test_unicode_with_illegal_ascii(self):
        assert sanitize("日本語<title>") == "日本語title"


# ---------------------------------------------------------------------------
# Default path resolution
# ---------------------------------------------------------------------------

class TestDefaultPathSeriesWithNumber:
    """Book with series AND series_num: Author/Series/Book N Title."""

    def test_basic_series_with_number(self):
        book = Book(
            title="The Final Empire",
            authors=["Brandon Sanderson"],
            narrators=["Michael Kramer"],
            isbn="9780765374991",
            series="Mistborn",
            series_num=1,
        )
        path = resolve_path(book)
        assert path == "Brandon Sanderson/Mistborn/Book 1 The Final Empire"

    def test_sanitizes_author_name(self):
        book = Book(
            title="The Final Empire",
            authors=["O'Brien, Brandon <Author>"],
            narrators=["Michael Kramer"],
            isbn="9780765374991",
            series="Mistborn: Era 1",
            series_num=1,
        )
        path = resolve_path(book)
        # Angle brackets stripped from author, colon replaced in series
        assert path == "O'Brien, Brandon Author/Mistborn - Era 1/Book 1 The Final Empire"

    def test_sanitizes_series_and_title(self):
        book = Book(
            title="The Way of Kings (Book 1)",
            authors=["Brandon Sanderson"],
            narrators=["Kate Reading", "Michael Kramer"],
            isbn="9780765398270",
            series="Stormlight Archive*",
            series_num=1,
        )
        path = resolve_path(book)
        assert path == "Brandon Sanderson/Stormlight Archive/Book 1 The Way of Kings (Book 1)"


class TestDefaultPathSeriesWithoutNumber:
    """Book with series but no series_num: Author/Series/Title."""

    def test_basic_series_no_number(self):
        book = Book(
            title="Warbreaker",
            authors=["Brandon Sanderson"],
            narrators=["Alyssa Bresnahan"],
            isbn="9781433232829",
            series="Cosmere: Standalones",
            series_num=None,
        )
        path = resolve_path(book)
        assert path == "Brandon Sanderson/Cosmere - Standalones/Warbreaker"


class TestDefaultPathNoSeries:
    """Book without series: Author/Title."""

    def test_standalone_book(self):
        book = Book(
            title="Skyward",
            authors=["Brandon Sanderson"],
            narrators=["Sophie Aldred"],
            isbn="9781509697815",
            series="",
            series_num=None,
        )
        path = resolve_path(book)
        assert path == "Brandon Sanderson/Skyward"


class TestCustomPathPattern:
    """Custom path_pattern with token substitution overrides default logic."""

    def test_basic_custom_pattern(self):
        book = Book(
            title="The Final Empire",
            authors=["Brandon Sanderson"],
            narrators=["Michael Kramer"],
            isbn="9780765374991",
            series="Mistborn",
            series_num=1,
        )
        pattern = "{FIRST_AUTHOR}/{SERIES_NAME}/{BOOK_TITLE}"
        path = resolve_path(book, pattern=pattern)
        assert path == "Brandon Sanderson/Mistborn/The Final Empire"

    def test_custom_pattern_overrides_default(self):
        """When pattern is set, default conditional logic is NOT used."""
        book = Book(
            title="The Final Empire",
            authors=["Brandon Sanderson"],
            narrators=["Michael Kramer"],
            isbn="9780765374991",
            series="Mistborn",
            series_num=1,
        )
        # Custom pattern without series_num — should NOT get "Book 1" prefix
        pattern = "{FIRST_AUTHOR}/{BOOK_TITLE}"
        path = resolve_path(book, pattern=pattern)
        assert path == "Brandon Sanderson/The Final Empire"

    def test_all_authors_token(self):
        book = Book(
            title="Good Omens",
            authors=["Neil Gaiman", "Terry Pratchett"],
            narrators=["Martin Jarvis", "Stephen Briggs"],
            isbn="9780062982360",
        )
        pattern = "{ALL_AUTHORS}/{BOOK_TITLE}"
        path = resolve_path(book, pattern=pattern)
        assert path == "Neil Gaiman, Terry Pratchett/Good Omens"

    def test_series_num_token(self):
        book = Book(
            title="The Final Empire",
            authors=["Brandon Sanderson"],
            narrators=["Michael Kramer"],
            isbn="9780765374991",
            series="Mistborn",
            series_num=1,
        )
        pattern = "{SERIES_NAME} {SERIES_NUM} - {BOOK_TITLE}"
        path = resolve_path(book, pattern=pattern)
        assert path == "Mistborn 1 - The Final Empire"

    def test_isbn_token(self):
        book = Book(
            title="The Final Empire",
            authors=["Brandon Sanderson"],
            narrators=["Michael Kramer"],
            isbn="9780765374991",
        )
        pattern = "{ISBN}/{BOOK_TITLE}"
        path = resolve_path(book, pattern=pattern)
        assert path == "9780765374991/The Final Empire"

    def test_narrator_tokens(self):
        book = Book(
            title="Good Omens",
            authors=["Neil Gaiman"],
            narrators=["Martin Jarvis", "Stephen Briggs"],
            isbn="9780062982360",
        )
        pattern = "{FIRST_AUTHOR} - {FIRST_NARRATOR}/{BOOK_TITLE}"
        path = resolve_path(book, pattern=pattern)
        assert path == "Neil Gaiman - Martin Jarvis/Good Omens"

    def test_all_narrators_token(self):
        book = Book(
            title="Good Omens",
            authors=["Neil Gaiman"],
            narrators=["Martin Jarvis", "Stephen Briggs"],
            isbn="9780062982360",
        )
        pattern = "{ALL_NARRATORS}/{BOOK_TITLE}"
        path = resolve_path(book, pattern=pattern)
        assert path == "Martin Jarvis, Stephen Briggs/Good Omens"

    def test_publication_date_tokens(self):
        book = Book(
            title="The Final Empire",
            authors=["Brandon Sanderson"],
            narrators=["Michael Kramer"],
            isbn="9780765374991",
            publication_year=2006,
            publication_month=7,
            publication_day=17,
        )
        pattern = "{PUBLICATION_YEAR}/{PUBLICATION_MONTH}/{PUBLICATION_DAY}/{BOOK_TITLE}"
        path = resolve_path(book, pattern=pattern)
        assert path == "2006/7/17/The Final Empire"

    def test_missing_optional_tokens_omitted(self):
        """Tokens with no value produce empty string (not error)."""
        book = Book(
            title="Standalone",
            authors=["Some Author"],
            narrators=[],
            isbn="9780000000001",
        )
        pattern = "{SERIES_NAME}/{BOOK_TITLE}"
        path = resolve_path(book, pattern=pattern)
        assert path == "/Standalone"

    def test_sanitizes_custom_pattern_output(self):
        book = Book(
            title="Book: A Subtitle<Extra>",
            authors=["O'Brien, Author"],
            narrators=["Narrator"],
            isbn="9780000000001",
        )
        pattern = "{FIRST_AUTHOR}/{BOOK_TITLE}"
        path = resolve_path(book, pattern=pattern)
        assert path == "O'Brien, Author/Book - A SubtitleExtra"


# ---------------------------------------------------------------------------
# Subdirectory decision
# ---------------------------------------------------------------------------

class TestNeedsSubdirectory:
    """Subdirectory is needed when PDF extras or cover art are present."""

    def test_true_when_pdf_extras_present(self):
        book = Book(
            title="Some Book",
            authors=["Author"],
            narrators=["Narrator"],
            isbn="9780000000001",
            pdf_extras=True,
            cover_url="",
        )
        assert needs_subdirectory(book) is True

    def test_false_when_cover_url_only(self):
        """cover_url alone does NOT trigger subdirectory — config-gated."""
        book = Book(
            title="Some Book",
            authors=["Author"],
            narrators=["Narrator"],
            isbn="9780000000001",
            pdf_extras=False,
            cover_url="https://example.com/cover.jpg",
        )
        assert needs_subdirectory(book) is False

    def test_true_when_both_present(self):
        book = Book(
            title="Some Book",
            authors=["Author"],
            narrators=["Narrator"],
            isbn="9780000000001",
            pdf_extras=True,
            cover_url="https://example.com/cover.jpg",
        )
        assert needs_subdirectory(book) is True

    def test_false_when_neither_present(self):
        book = Book(
            title="Some Book",
            authors=["Author"],
            narrators=["Narrator"],
            isbn="9780000000001",
            pdf_extras=False,
            cover_url="",
        )
        assert needs_subdirectory(book) is False

    def test_false_with_defaults(self):
        """Book created with default fields (no extras, no cover)."""
        book = Book(
            title="Some Book",
            authors=["Author"],
            narrators=["Narrator"],
            isbn="9780000000001",
        )
        assert needs_subdirectory(book) is False


# ---------------------------------------------------------------------------
# M4B streaming download
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# MP3 ZIP download + extraction — Issue #6
# ---------------------------------------------------------------------------

import zipfile
import io


class TestDownloadZipPart:
    """Download a single ZIP part with .partial tracking and extraction."""

    def test_downloads_zip_and_extracts_mp3_files(self):
        """Successful ZIP download writes .partial, renames, extracts .mp3 files."""
        # Create a valid ZIP containing two MP3 files
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("track01.mp3", b"fake-audio-data-01")
            zf.writestr("track02.mp3", b"fake-audio-data-02")
        zip_payload = zip_buf.getvalue()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=zip_payload)

        transport = httpx.MockTransport(handler)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "extracted"
            output_dir.mkdir()
            zip_url = "https://cdn.libro.fm/part1.zip"

            result = download_zip_part(
                url=zip_url,
                output_dir=output_dir,
                transport=transport,
            )

            # MP3 files extracted
            assert (output_dir / "track01.mp3").exists()
            assert (output_dir / "track02.mp3").exists()
            assert (output_dir / "track01.mp3").read_bytes() == b"fake-audio-data-01"
            assert (output_dir / "track02.mp3").read_bytes() == b"fake-audio-data-02"
            # No .partial left behind
            assert not list(output_dir.glob("*.partial"))

    def test_handles_corrupt_zip_gracefully(self):
        """Corrupt/invalid ZIP data → raises error, no crash, no partial left."""
        corrupt_payload = b"this-is-not-a-zip-file-at-all"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=corrupt_payload)

        transport = httpx.MockTransport(handler)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "extracted"
            output_dir.mkdir()

            with pytest.raises((zipfile.BadZipFile, Exception)):
                download_zip_part(
                    url="https://cdn.libro.fm/corrupt.zip",
                    output_dir=output_dir,
                    transport=transport,
                )

            # No partial file left behind
            assert not list(output_dir.glob("*.partial"))

    def test_resumes_from_partial_zip_file(self):
        """Existing .partial file → sends Range header, appends, then extracts."""
        # Full ZIP payload (one MP3)
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("resume_track.mp3", b"complete-audio")
        full_payload = zip_buf.getvalue()

        # Split into first half + second half
        mid = len(full_payload) // 2
        first_half = full_payload[:mid]
        second_half = full_payload[mid:]
        range_header_seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            range_header_seen.append(request.headers.get("range", ""))
            rh = request.headers.get("range")
            if rh == f"bytes={mid}-":
                return httpx.Response(
                    206,
                    content=second_half,
                    headers={
                        "content-range": f"bytes {mid}-{len(full_payload)-1}/{len(full_payload)}",
                        "content-length": str(len(second_half)),
                    },
                )
            return httpx.Response(400, text="Expected Range header")

        transport = httpx.MockTransport(handler)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "extracted"
            output_dir.mkdir()
            # _part_filename_from_url("https://cdn.libro.fm/resume.zip") → "resume"
            partial_path = output_dir / "resume.zip.partial"

            # Pre-create partial file simulating interrupted download
            partial_path.write_bytes(first_half)

            result = download_zip_part(
                url="https://cdn.libro.fm/resume.zip",
                output_dir=output_dir,
                transport=transport,
            )

            # Range header was sent with correct offset
            assert f"bytes={mid}-" in range_header_seen
            # Extracted file exists with correct content
            assert (output_dir / "resume_track.mp3").exists()
            assert (output_dir / "resume_track.mp3").read_bytes() == b"complete-audio"
            # No .partial left behind
            assert not partial_path.exists()


class TestDownloadM4B:
    """Streaming chunked download with .partial → atomic rename to .m4b."""

    def test_downloads_and_renames_to_m4b(self):
        """Successful download writes .partial then renames to final .m4b file."""
        import io

        # 24 bytes of fake M4B data (3 chunks of 8 bytes each)
        payload = b"fake-m4b-audio-data-!!" * 3  # 72 bytes

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=payload, headers={"content-length": str(len(payload))})

        transport = httpx.MockTransport(handler)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.m4b"
            result = download_m4b(
                url="https://cdn.example.com/book.m4b",
                output_path=output_path,
                transport=transport,
            )

            # Final .m4b file exists with correct content
            assert output_path.exists()
            assert output_path.read_bytes() == payload
            # No .partial file left behind
            assert not Path(str(output_path) + ".partial").exists()
            # Result is the final path
            assert result == output_path

    def test_resumes_from_partial_file(self):
        """Existing .partial file → sends Range header, appends from offset."""
        # First "download" writes 30 bytes
        first_chunk = b"A" * 30
        # Server has 72 bytes total; client needs last 42
        remaining = b"B" * 42
        full_payload = first_chunk + remaining
        range_header_seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            range_header_seen.append(request.headers.get("range", ""))
            # Only accept requests with correct Range header for resume
            rh = request.headers.get("range")
            if rh == "bytes=30-":
                return httpx.Response(
                    206,
                    content=remaining,
                    headers={
                        "content-range": f"bytes 30-{len(full_payload)-1}/{len(full_payload)}",
                        "content-length": str(len(remaining)),
                    },
                )
            # Reject any request without proper Range header
            return httpx.Response(400, text="Expected Range header")

        transport = httpx.MockTransport(handler)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "resume_test.m4b"
            partial_path = Path(str(output_path) + ".partial")

            # Pre-create partial file simulating interrupted download
            output_path.parent.mkdir(parents=True, exist_ok=True)
            partial_path.write_bytes(first_chunk)

            result = download_m4b(
                url="https://cdn.example.com/book.m4b",
                output_path=output_path,
                transport=transport,
            )

            # Verify Range header was sent with correct offset
            assert "bytes=30-" in range_header_seen
            # Final file has complete content
            assert output_path.exists()
            assert output_path.read_bytes() == full_payload
            # No .partial left behind
            assert not partial_path.exists()

    def test_output_path_uses_resolved_sanitized_path(self):
        """Download goes to the resolved+sanitized path for the book's metadata."""
        payload = b"m4b-data-here"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=payload)

        transport = httpx.MockTransport(handler)

        book = Book(
            title="Test: A Story",
            authors=["O'Brien, Jane"],
            narrators=["Narrator One"],
            isbn="9789876543210",
            series="Cool Series",
            series_num=3,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            # Resolve path using Slice 3a logic
            relative = resolve_path(book)
            # Apply subdirectory decision
            if needs_subdirectory(book):
                output_path = base_dir / relative / f"{sanitize(book.title)}.m4b"
            else:
                output_path = base_dir / f"{relative}.m4b"

            result = download_m4b(
                url="https://cdn.example.com/book.m4b",
                output_path=output_path,
                transport=transport,
            )

            assert result.exists()
            assert result.read_bytes() == payload
            # Path should be sanitized (colon replaced, apostrophe preserved)
            assert "O'Brien" in str(result)  # apostrophe preserved
            assert ":" not in str(result.parent)  # colon removed from parent dirs


    def test_creates_subdirectory_when_extras_present(self):
        """Book with PDF extras → file inside subdirectory, not flat."""
        payload = b"m4b-with-extras"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=payload)

        transport = httpx.MockTransport(handler)

        book = Book(
            title="Book With Extras",
            authors=["Author Name"],
            narrators=["Narrator"],
            isbn="9785555555555",
            pdf_extras=True,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            relative = resolve_path(book)
            # needs_subdirectory is True → file goes inside subdirectory
            output_path = base_dir / relative / f"{sanitize(book.title)}.m4b"

            result = download_m4b(
                url="https://cdn.example.com/book.m4b",
                output_path=output_path,
                transport=transport,
            )

            # File is inside subdirectory (not at leaf)
            assert result.parent.name == sanitize(book.title)
            assert result.exists()
            assert result.read_bytes() == payload


# ---------------------------------------------------------------------------
# Cooperative cancellation — download loops check cancel_event between chunks
# ---------------------------------------------------------------------------


class TestCooperativeCancellation:
    """Download functions check cancel_event between chunks and exit promptly.

    This is the fix for Ctrl+C downloading entire books: instead of waiting
    for shutdown(wait=True) to complete full futures, each download loop checks
    a threading.Event between 8 MB chunks and raises InterruptedDownload.
    """

    def test_download_book_forwards_cancel_event(self):
        """download_book() accepts cancel_event explicitly and forwards it.

        Regression test for Issue #39: cancel_event must flow through the
        explicit parameter chain (sync_run → download_book → streaming calls),
        NOT through reporter.cancel_event.
        """
        import threading
        import time

        cancel_event = threading.Event()

        from librofm_downloader.downloader import CHUNK_SIZE

        # Payload > CHUNK_SIZE so iter_bytes produces multiple chunks,
        # giving the cancel check a chance to fire mid-stream.
        payload = b"\x00" * (CHUNK_SIZE + 1024)

        def handler(request):
            if "/oauth/token" in request.url.path:
                return httpx.Response(200, json={"access_token": "tok", "token_type": "bearer"})
            if "/audiobooks/" in request.url.path and "packaged_m4b" in request.url.path:
                return httpx.Response(200, json={"m4b_url": "https://cdn.example.com/book.m4b"})
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=payload, headers={"Content-Length": str(len(payload))})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        session = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        session.authenticate()

        from unittest.mock import MagicMock
        from librofm_downloader.downloader import InterruptedDownload

        book = Book(title="Cancel Test", authors=["Author"], narrators=["N"], isbn="9789900000001")
        reporter = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            plan = resolve_output_plan(book, Path(tmpdir), format_strategy="m4b_only")

            # Set cancel_event shortly after download starts so the chunk loop
            # sees it between iterations.
            def set_cancel_soon():
                time.sleep(0)  # yield to ensure thread runs before download starts
                cancel_event.set()

            t = threading.Thread(target=set_cancel_soon, daemon=True)
            t.start()
            try:
                download_book(
                    book, session, plan, reporter,
                    cancel_event=cancel_event,
                )
                assert False, "Expected InterruptedDownload"
            except InterruptedDownload:
                pass

            t.join(timeout=2)

    def test_m4b_raises_interrupted_when_cancelled_mid_download(self):
        """download_m4b raises InterruptedDownload when cancel_event is set mid-stream.

        Uses payload > CHUNK_SIZE (8 MB) so iter_bytes actually produces
        multiple iterations, giving the cancel check a chance to fire.
        """
        import threading
        import time

        cancel_event = threading.Event()

        # Payload must exceed CHUNK_SIZE (8 MB) for iter_bytes to chunk it
        from librofm_downloader.downloader import CHUNK_SIZE
        payload = b"X" * (CHUNK_SIZE + 1024)  # 8 MB + 1 KB → 2 iterations

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=payload,
                headers={"content-length": str(len(payload))},
            )

        transport = httpx.MockTransport(handler)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "cancelled.m4b"

            # Set cancel from another thread after a brief delay
            # (gives time for first chunk to start processing)
            def set_cancel_soon():
                time.sleep(0)  # yield to ensure thread runs before download starts
                cancel_event.set()

            t = threading.Thread(target=set_cancel_soon, daemon=True)
            t.start()

            from librofm_downloader.downloader import InterruptedDownload

            with pytest.raises(InterruptedDownload):
                download_m4b(
                    url="https://cdn.example.com/slow.m4b",
                    output_path=output_path,
                    transport=transport,
                    cancel_event=cancel_event,
                )

            t.join(timeout=2)
            # File should NOT be renamed to .m4b (only .partial remains)
            assert not output_path.exists(), (
                "Cancelled download should not produce final file"
            )

    def test_zip_part_raises_interrupted_when_cancelled(self):
        """download_zip_part raises InterruptedDownload when cancel_event is set.

        Uses valid ZIP payload > CHUNK_SIZE so iter_bytes chunks it,
        giving the cancel check a chance to fire mid-stream.
        """
        import threading
        import time
        import zipfile as _zipfile
        import io

        cancel_event = threading.Event()

        # Create valid ZIP content larger than CHUNK_SIZE (8 MB)
        from librofm_downloader.downloader import CHUNK_SIZE
        zip_buf = io.BytesIO()
        with _zipfile.ZipFile(zip_buf, "w") as zf:
            # Write enough data to exceed 8 MB
            zf.writestr("test.txt", "x" * (CHUNK_SIZE + 1024))
        valid_zip_data = zip_buf.getvalue()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=valid_zip_data,
                headers={"content-length": str(len(valid_zip_data))},
            )

        transport = httpx.MockTransport(handler)

        with tempfile.TemporaryDirectory() as tmpdir:
            def set_cancel_soon():
                time.sleep(0)  # yield to ensure thread runs before download starts
                cancel_event.set()

            t = threading.Thread(target=set_cancel_soon, daemon=True)
            t.start()

            from librofm_downloader.downloader import InterruptedDownload

            with pytest.raises(InterruptedDownload):
                download_zip_part(
                    url="https://cdn.example.com/part.zip",
                    output_dir=tmpdir,
                    transport=transport,
                    cancel_event=cancel_event,
                )

            t.join(timeout=2)
            # ZIP should NOT have been extracted (extraction happens after download loop)
            extracted_files = list(Path(tmpdir).iterdir())
            assert not any(f.suffix == ".txt" for f in extracted_files), (
                "ZIP should NOT have been extracted after cancellation"
            )
    def test_no_cancel_event_means_normal_behavior(self):
        """cancel_event=None (default) downloads normally without interruption."""

        payload = b"normal-download-data" * 3

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=payload, headers={"content-length": str(len(payload))})

        transport = httpx.MockTransport(handler)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "normal.m4b"
            result = download_m4b(
                url="https://cdn.example.com/normal.m4b",
                output_path=output_path,
                transport=transport,
                cancel_event=None,  # explicit None = no cancellation
            )

            assert result == output_path
            assert output_path.read_bytes() == payload
# ---------------------------------------------------------------------------
# Orchestration: resolve path → query M4B → download → update history
# ---------------------------------------------------------------------------


class TestDownloadBook:
    """End-to-end orchestration with mocked HTTP."""

    def test_writes_history_entry_after_successful_download(self):
        """After successful M4B download, caller writes history entry."""
        m4b_payload = b"complete-m4b-audio-data"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/audiobooks/9781111111111/packaged_m4b":
                return httpx.Response(
                    200,
                    json={"m4b_url": "https://cdn.example.com/book.m4b"},
                )
            # CDN download
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=m4b_payload)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(
            title="History Test Book",
            authors=["Hist Author"],
            narrators=["H Narr"],
            isbn="9781111111111",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            history_path = Path(tmpdir) / "history.json"
            history = DownloadHistory(history_path)

            plan = resolve_output_plan(book, base_dir)
            reporter = DownloadReporter()
            result = download_book(
                book=book,
                session=client,
                plan=plan,
                reporter=reporter,
            )

            # History is caller's responsibility now
            assert result.status == "downloaded"
            _write_history(history, book, result.format or "m4b", str(result.path))

            # History was written
            assert history.is_downloaded("9781111111111")
            entry = history.find("9781111111111")
            assert entry is not None
            assert entry.format == "m4b"
            assert entry.title == "History Test Book"
    def test_skips_book_without_m4b(self):
        """Book with no M4B available → DownloadResult(skipped), no history entry."""
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/audiobooks/9780000000000/packaged_m4b":
                return httpx.Response(404)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(
            title="No M4B Book",
            authors=["Author"],
            narrators=["Narr"],
            isbn="9780000000000",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            history_path = Path(tmpdir) / "history.json"
            history = DownloadHistory(history_path)

            plan = resolve_output_plan(book, base_dir)
            reporter = DownloadReporter()
            result = download_book(
                book=book,
                session=client,
                plan=plan,
                reporter=reporter,
            )

            # Returns skipped (no M4B in m4b_mp3_fallback → tries MP3 manifest → also 404)
            assert result.status == "skipped"
            # No history entry written
            assert history.is_downloaded("9780000000000") is False

    def test_no_history_entry_on_download_failure(self):
        """If download fails after M4B query, no history entry is written."""
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/audiobooks/9789999999999/packaged_m4b":
                return httpx.Response(
                    200,
                    json={"m4b_url": "https://cdn.example.com/fail.m4b"},
                )
            # CDN returns 500 error
            if "cdn.example.com" in request.url.host:
                return httpx.Response(500, text="Server Error")
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(
            title="Fail Book",
            authors=["Author"],
            narrators=["Narr"],
            isbn="9789999999999",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            history_path = Path(tmpdir) / "history.json"
            history = DownloadHistory(history_path)

            plan = resolve_output_plan(book, base_dir)
            reporter = DownloadReporter()
            with pytest.raises(httpx.HTTPStatusError):
                download_book(
                    book=book,
                    session=client,
                    plan=plan,
                    reporter=reporter,
                )

            # No history entry written for failed download
            assert history.is_downloaded("9789999999999") is False

    def test_flat_path_when_no_accompanying_files(self):
        """Book without extras/cover → flat path, no subdirectory created."""
        payload = b"flat-m4b-data"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/audiobooks/9782222222222/packaged_m4b":
                return httpx.Response(200, json={"m4b_url": "https://cdn.example.com/flat.m4b"})
            return httpx.Response(200, content=payload)

        transport = httpx.MockTransport(handler)
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(
            title="Standalone Book",
            authors=["Solo Author"],
            narrators=["Solo Narr"],
            isbn="9782222222222",
            # No pdf_extras, no cover_url → needs_subdirectory() returns False
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            history_path = Path(tmpdir) / "history.json"
            history = DownloadHistory(history_path)

            plan = resolve_output_plan(book, base_dir)
            reporter = DownloadReporter()
            result = download_book(
                book=book,
                session=client,
                plan=plan,
                reporter=reporter,
            )

            # File is at leaf (flat), not inside a subdirectory
            assert result.status == "downloaded"
            assert result.path is not None
            # Path should be base/Author/Title.m4b (flat) — title is filename stem
            assert result.path.stem == "Standalone Book"
            # No extra subdirectory between author and file
            assert result.path.parent.name == "Solo Author"
            assert result.path.exists()


# ---------------------------------------------------------------------------
# Format strategy selector — Issue #6
# ---------------------------------------------------------------------------


class TestFormatStrategy:
    """download_book respects the format strategy config."""

    @staticmethod
    def _make_mp3_zip() -> bytes:
        """Create a valid ZIP with one MP3 file for testing."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("chapter01.mp3", b"mp3-audio-data")
        return buf.getvalue()

    def test_m4b_mp3_fallback_tries_m4b_first(self):
        """m4b_mp3_fallback: M4B available → downloads M4B, never queries MP3."""
        m4b_payload = b"real-m4b-data"
        mp3_calls: list[None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 7200},
                )
            # M4B is available
            if request.url.path == "/api/v10/audiobooks/9781111111111/packaged_m4b":
                return httpx.Response(200, json={"m4b_url": "https://cdn.example.com/book.m4b"})
            # CDN serves M4B
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=m4b_payload)
            # Track that manifest endpoint was called (should NOT happen)
            if request.url.path == "/api/v10/download-manifest":
                mp3_calls.append(None)
                return httpx.Response(
                    200,
                    json={"parts": [{"url": "https://cdn.example.com/p1.zip", "name": "p1"}], "tracks": []},
                )
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(title="M4B Available", authors=["A"], narrators=["N"], isbn="9781111111111")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            history_path = Path(tmpdir) / "history.json"
            history = DownloadHistory(history_path)

            plan = resolve_output_plan(book, base_dir, format_strategy="m4b_mp3_fallback")
            reporter = DownloadReporter()
            result = download_book(
                book=book,
                session=client,
                plan=plan,
                reporter=reporter,
            )

            # M4B was downloaded (not MP3)
            assert result.status == "downloaded"
            assert result.path is not None
            assert result.path.suffix == ".m4b"
            assert result.format == "m4b"
            # Manifest was never queried
            assert len(mp3_calls) == 0
            # History is caller's responsibility now
            _write_history(history, book, result.format, str(result.path))
            entry = history.find("9781111111111")
            assert entry is not None
            assert entry.format == "m4b"

    def test_m4b_mp3_fallback_falls_back_to_mp3_on_404(self):
        """m4b_mp3_fallback: M4B returns 404 → fetches manifest, downloads ZIP."""
        mp3_zip_payload = self._make_mp3_zip()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 7200},
                )
            # M4B NOT available
            if request.url.path == "/api/v10/audiobooks/9782222222222/packaged_m4b":
                return httpx.Response(404)
            # MP3 manifest available
            if request.url.path == "/api/v10/download-manifest":
                return httpx.Response(
                    200,
                    json={
                        "parts": [
                            {"url": "https://cdn.example.com/p1.zip", "name": "p1"},
                        ],
                        "tracks": [{"number": 1, "chapter_title": "Ch 1"}],
                    },
                )
            # CDN serves ZIP
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=mp3_zip_payload)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(title="MP3 Fallback Book", authors=["A"], narrators=["N"], isbn="9782222222222")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            history_path = Path(tmpdir) / "history.json"
            history = DownloadHistory(history_path)

            plan = resolve_output_plan(book, base_dir, format_strategy="m4b_mp3_fallback")
            reporter = DownloadReporter()
            result = download_book(
                book=book,
                session=client,
                plan=plan,
                reporter=reporter,
            )

            # MP3 files were extracted
            assert result.status == "downloaded"
            assert result.path is not None
            assert result.format == "mp3"
            # At least one .mp3 file exists in output tree
            mp3_files = list(base_dir.rglob("*.mp3"))
            assert len(mp3_files) >= 1
            # History is caller's responsibility now
            _write_history(history, book, result.format, str(result.path))
            entry = history.find("9782222222222")
            assert entry is not None
            assert entry.format == "mp3"

    def test_mp3_only_skips_m4b_query(self):
        """mp3_only: Never queries M4B endpoint, goes straight to manifest."""
        mp3_zip_payload = self._make_mp3_zip()
        m4b_calls: list[None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 7200},
                )
            # Track M4B calls (should NOT happen in mp3_only mode)
            if "/packaged_m4b" in request.url.path:
                m4b_calls.append(None)
                return httpx.Response(200, json={"m4b_url": "https://cdn.example.com/book.m4b"})
            # MP3 manifest
            if request.url.path == "/api/v10/download-manifest":
                return httpx.Response(
                    200,
                    json={
                        "parts": [
                            {"url": "https://cdn.example.com/p1.zip", "name": "p1"},
                        ],
                        "tracks": [],
                    },
                )
            # CDN serves ZIP
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=mp3_zip_payload)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(title="MP3 Only Book", authors=["A"], narrators=["N"], isbn="9783333333333")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            history_path = Path(tmpdir) / "history.json"
            history = DownloadHistory(history_path)

            plan = resolve_output_plan(book, base_dir, format_strategy="mp3_only")
            reporter = DownloadReporter()
            result = download_book(
                book=book,
                session=client,
                plan=plan,
                reporter=reporter,
            )

            # MP3 files extracted
            assert result.status == "downloaded"
            assert result.path is not None
            assert result.format == "mp3"
            mp3_files = list(base_dir.rglob("*.mp3"))
            assert len(mp3_files) >= 1
            # M4B was never queried
            assert len(m4b_calls) == 0
            # History is caller's responsibility now
            _write_history(history, book, result.format, str(result.path))
            entry = history.find("9783333333333")
            assert entry is not None
            assert entry.format == "mp3"

    def test_m4b_only_skips_when_unavailable(self):
        """m4b_only: No M4B available → returns None (skip), no MP3 fallback."""
        manifest_calls: list[None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/audiobooks/9780000000000/packaged_m4b":
                return httpx.Response(404)
            # Track manifest calls (should NOT happen in m4b_only mode)
            if request.url.path == "/api/v10/download-manifest":
                manifest_calls.append(None)
                return httpx.Response(200, json={"parts": [], "tracks": []})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(title="No M4B Skip", authors=["A"], narrators=["N"], isbn="9780000000000")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            history_path = Path(tmpdir) / "history.json"
            history = DownloadHistory(history_path)

            plan = resolve_output_plan(book, base_dir, format_strategy="m4b_only")
            reporter = DownloadReporter()
            result = download_book(
                book=book,
                session=client,
                plan=plan,
                reporter=reporter,
            )

            # Skipped (no M4B)
            assert result.status == "skipped"
            # Manifest was never queried
            assert len(manifest_calls) == 0
            # No history entry
            assert history.is_downloaded("9780000000000") is False


# ---------------------------------------------------------------------------
# Accompanying files download — Issue #7
# ---------------------------------------------------------------------------


class TestDownloadAccompanyingFiles:
    """PDF extras and cover art download with config toggles and .partial pattern."""

    def test_downloads_cover_art_to_correct_location(self):
        """Book with cover_url → downloads image into book's output directory."""
        cover_payload = b"fake-jpeg-cover-data"

        def handler(request: httpx.Request) -> httpx.Response:
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=cover_payload)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)

        book = Book(
            title="Book With Cover",
            authors=["Author Name"],
            narrators=["Narrator"],
            isbn="9789999999999",
            cover_url="https://cdn.example.com/cover.jpg",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir()

            from librofm_downloader.config import Config
            config = Config(
                username="u", password="p", format="m4b_mp3_fallback",
                output_dir=str(tmpdir), download_extras=True, download_covers=True,
                rename_chapters=True,
            )

            plan = resolve_output_plan(book, output_dir, config=config)
            download_accompanying_files(book, plan, transport=transport)

            # Cover file exists at plan.resolved location
            cover_path = plan.cover_path
            assert cover_path is not None
            assert cover_path.exists()
            assert cover_path.read_bytes() == cover_payload

    def test_downloads_pdf_extra_to_correct_location(self):
        """Book with pdf_extras → downloads PDF into book's output directory."""
        pdf_payload = b"fake-pdf-data-for-map"

        def handler(request: httpx.Request) -> httpx.Response:
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=pdf_payload)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)

        book = Book(
            title="Book With Map",
            authors=["Author Name"],
            narrators=["Narrator"],
            isbn="9788888888888",
            pdf_extras=True,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir()

            from librofm_downloader.config import Config
            config = Config(
                username="u", password="p", format="m4b_mp3_fallback",
                output_dir=str(tmpdir), download_extras=True, download_covers=True,
                rename_chapters=True,
            )

            # Create a mock client that returns a PDF URL
            mock_client = unittest.mock.MagicMock()
            mock_client.fetch_pdf_extra_url.return_value = "https://cdn.example.com/map.pdf"

            plan = resolve_output_plan(book, output_dir, config=config)
            downloaded = download_accompanying_files(book, plan, client=mock_client, transport=transport)

            # PDF file exists at plan.resolved location
            pdf_path = plan.pdf_path
            assert pdf_path is not None
            assert pdf_path.exists()
            assert pdf_path.read_bytes() == pdf_payload

    def test_uses_partial_file_then_atomic_rename(self):
        """Cover download writes .partial first, then renames atomically."""
        cover_payload = b"cover-data-for-partial-test"

        def handler(request: httpx.Request) -> httpx.Response:
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=cover_payload)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)

        book = Book(
            title="Partial Test Book",
            authors=["Author"],
            narrators=["Narrator"],
            isbn="9780000000001",
            cover_url="https://cdn.example.com/cover.jpg",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir()

            from librofm_downloader.config import Config
            config = Config(
                username="u", password="p", format="m4b_mp3_fallback",
                output_dir=str(tmpdir), download_extras=True, download_covers=True,
                rename_chapters=True,
            )

            plan = resolve_output_plan(book, output_dir, config=config)
            download_accompanying_files(book, plan, transport=transport)

            # Final file exists at plan.resolved location
            final_path = plan.cover_path
            assert final_path is not None
            assert final_path.exists()

            # No .partial file left behind
            partial_path = final_path.with_suffix(final_path.suffix + ".partial")
            assert not partial_path.exists()

    def test_download_extras_false_skips_pdf(self):
        """download_extras=False → no PDF download even when book has pdf_extras."""
        mock_client = unittest.mock.MagicMock()
        mock_client.fetch_pdf_extra_url.return_value = "https://cdn.example.com/map.pdf"

        book = Book(
            title="Extras Disabled Book",
            authors=["Author"],
            narrators=["Narrator"],
            isbn="9781111111111",
            pdf_extras=True,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir()

            from librofm_downloader.config import Config
            config = Config(
                username="u", password="p", format="m4b_mp3_fallback",
                output_dir=str(tmpdir), download_extras=False, download_covers=True,
                rename_chapters=True,
            )

            plan = resolve_output_plan(book, output_dir, config=config)
            downloaded = download_accompanying_files(book, plan, client=mock_client)

            # No files downloaded (no cover URL either)
            assert len(downloaded) == 0

            # Client was never called for PDF URL
            mock_client.fetch_pdf_extra_url.assert_not_called()

    def test_download_covers_false_skips_cover(self):
        """download_covers=False → no cover download even when book has cover_url."""
        book = Book(
            title="Covers Disabled Book",
            authors=["Author"],
            narrators=["Narrator"],
            isbn="9782222222222",
            cover_url="https://cdn.example.com/cover.jpg",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir()

            from librofm_downloader.config import Config
            config = Config(
                username="u", password="p", format="m4b_mp3_fallback",
                output_dir=str(tmpdir), download_extras=True, download_covers=False,
                rename_chapters=True,
            )

            plan = resolve_output_plan(book, output_dir, config=config)
            downloaded = download_accompanying_files(book, plan)

            # No files downloaded (no PDF extras either)
            assert len(downloaded) == 0

            # No cover file on disk
            assert not (output_dir / "cover.jpg").exists()

    def test_cover_download_failure_logs_warning_no_exception(self):
        """Cover download failure → logs warning, returns empty list, no exception."""
        def handler(request: httpx.Request) -> httpx.Response:
            # Simulate server error
            return httpx.Response(500)

        transport = httpx.MockTransport(handler)

        book = Book(
            title="Failing Cover Book",
            authors=["Author"],
            narrators=["Narrator"],
            isbn="9783333333333",
            cover_url="https://cdn.example.com/cover.jpg",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir()

            from librofm_downloader.config import Config
            config = Config(
                username="u", password="p", format="m4b_mp3_fallback",
                output_dir=str(tmpdir), download_extras=True, download_covers=True,
                rename_chapters=True,
            )

            # Should NOT raise — failure is non-critical
            plan = resolve_output_plan(book, output_dir, config=config)
            result = download_accompanying_files(book, plan, transport=transport)

            # Returns empty list (nothing downloaded)
            assert result == []


# ---------------------------------------------------------------------------
# Output structure integration — Issue #7
# ---------------------------------------------------------------------------


class TestOutputStructure:
    """Integration tests for output directory structure with/without extras."""

    def test_book_with_pdf_extras_creates_subdirectory(self):
        """Book with pdf_extras → needs_subdirectory=True."""
        book = Book(
            title="Book With Extras",
            authors=["Author Name"],
            narrators=["Narrator"],
            isbn="9785555555555",
            pdf_extras=True,
            cover_url="",
        )

        # Only pdf_extras triggers subdirectory (not cover_url)
        assert needs_subdirectory(book) is True

    def test_book_with_only_cover_does_not_create_subdirectory(self):
        """Book with only cover_url → needs_subdirectory=False (config-gated)."""
        book = Book(
            title="Book With Cover Only",
            authors=["Author Name"],
            narrators=["Narrator"],
            isbn="9785555555556",
            pdf_extras=False,
            cover_url="https://cdn.example.com/cover.jpg",
        )

        # cover_url alone doesn't trigger — needs config.download_covers too
        assert needs_subdirectory(book) is False

    def test_book_without_extras_is_flat(self):
        """Book without cover or PDF → needs_subdirectory=False, output is leaf file."""
        book = Book(
            title="Standalone Book",
            authors=["Author Name"],
            narrators=["Narrator"],
            isbn="9786666666666",
        )

        # Book without accompanying files should be flat
        assert needs_subdirectory(book) is False

    def test_resolve_output_dir_creates_subdir_for_pdf_extras(self):
        """_resolve_output_dir creates subdirectory when book has pdf_extras."""
        book = Book(
            title="Subdir Book",
            authors=["Author Name"],
            narrators=["Narrator"],
            isbn="9787777777777",
            pdf_extras=True,
            cover_url="",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "audiobooks"
            output_dir = _resolve_output_dir(book, base)

            # Should return a subdirectory path (not the base itself)
            assert output_dir != base
            assert output_dir.is_relative_to(base)

            # Creating it should work
            output_dir.mkdir(parents=True, exist_ok=True)
            assert output_dir.is_dir()

    def test_resolve_output_dir_flat_for_cover_only_without_config(self):
        """cover_url without config → flat path (no subdirectory)."""
        book = Book(
            title="Cover Only Flat",
            authors=["Author Name"],
            narrators=["Narrator"],
            isbn="9787777777778",
            pdf_extras=False,
            cover_url="https://cdn.example.com/cover.jpg",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "audiobooks"
            output_dir = _resolve_output_dir(book, base)

            # cover_url doesn't create subdirectory (covers sit alongside .m4b)
            assert output_dir == base / "Author Name"

    def test_resolve_output_dir_flat_for_cover_regardless_of_config(self):
        """cover_url never creates subdirectory — cover sits alongside .m4b.

        Even with download_covers=True in config, the cover is a single file that
        lives next to the audiobook file. No folder needed.
        """
        book = Book(
            title="Cover Flat Book",
            authors=["Author Name"],
            narrators=["Narrator"],
            isbn="9787777777779",
            pdf_extras=False,
            cover_url="https://cdn.example.com/cover.jpg",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "audiobooks"
            output_dir = _resolve_output_dir(book, base)

            # Cover URL alone → flat path, no subdirectory
            assert output_dir == base / "Author Name"

    def test_resolve_output_dir_subdir_no_title_doubling(self):
        """When pdf_extras creates a subdir, title is NOT doubled.

        resolve_path() returns 'Author/Title'. The subdir should be exactly that,
        not 'Author/Title/Title'.
        """
        book = Book(
            title="Subdir No Double",
            authors=["Author Name"],
            narrators=["Narrator"],
            isbn="9787777777780",
            pdf_extras=True,
            cover_url="",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "audiobooks"
            output_dir = _resolve_output_dir(book, base)

            # Should be base/Author/Subdir No Double — title appears once
            expected = base / "Author Name" / "Subdir No Double"
            assert output_dir == expected, f"Expected {expected}, got {output_dir}"

            # Verify no doubled title component
            parts = output_dir.parts
            # Count how many times the sanitized title appears
            title_parts = [p for p in parts if p == "Subdir No Double"]
            assert len(title_parts) == 1, f"Title doubled in path: {output_dir}"

    def test_resolve_output_dir_flat_for_no_extras(self):
        """_resolve_output_dir returns flat path when no extras (audio is leaf file)."""
        book = Book(
            title="Flat Book",
            authors=["Author Name"],
            narrators=["Narrator"],
            isbn="9788888888888",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "audiobooks"
            output_dir = _resolve_output_dir(book, base)

            # Flat layout: no extra book-level subdirectory for the audio file
            # The audio filename will be the leaf node in this directory
            assert output_dir == base / "Author Name"
        """PDF fetch/download failure → logs warning, continues without PDF."""
        mock_client = unittest.mock.MagicMock()
        mock_client.fetch_pdf_extra_url.side_effect = Exception("API error")

        book = Book(
            title="Failing PDF Book",
            authors=["Author"],
            narrators=["Narrator"],
            isbn="9784444444444",
            pdf_extras=True,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir()

            from librofm_downloader.config import Config
            config = Config(
                username="u", password="p", format="m4b_mp3_fallback",
                output_dir=str(tmpdir), download_extras=True, download_covers=True,
                rename_chapters=True,
            )

            # Should NOT raise — failure is non-critical
            plan = resolve_output_plan(book, output_dir, config=config)
            result = download_accompanying_files(book, plan, client=mock_client)

            # Returns empty list (nothing downloaded)
            assert result == []



class TestRenameChapters:
    """Tests for rename_chapters() — post-process MP3 files with chapter titles."""

    def test_basic_rename_renames_all_files_with_chapter_titles(self):
        """Given 3 MP3 files and 3 tracks with titles, renames all to '{num} - {book} - {chapter}.mp3'."""
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create 3 MP3 files with numeric prefixes (simulating extracted ZIP contents)
            for i in range(1, 4):
                Path(tmpdir, f"{i}.mp3").write_text(f"audio{i}")

            tracks = [
                {"number": 1, "chapter_title": "Prologue"},
                {"number": 2, "chapter_title": "The Beginning"},
                {"number": 3, "chapter_title": "Epilogue"},
            ]

            count = rename_chapters(tmpdir, tracks, "Test Book")

            assert count == 3
            assert Path(tmpdir, "1 - Test Book - Prologue.mp3").exists()
            assert Path(tmpdir, "2 - Test Book - The Beginning.mp3").exists()
            assert Path(tmpdir, "3 - Test Book - Epilogue.mp3").exists()
            # Original files should be gone (renamed)
            assert not Path(tmpdir, "1.mp3").exists()


    def test_natural_sort_pairs_files_numerically_not_alphabetically(self):
        """Files Track-1.mp3 through Track-10.mp3 are sorted numerically, so Track-10 pairs with track 10."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files that would sort alphabetically wrong: 10 comes before 2
            for i in [1, 2, 3, 10]:
                Path(tmpdir, f"Track - {i}.mp3").write_text(f"audio{i}")

            tracks = [
                {"number": 1, "chapter_title": "First"},
                {"number": 2, "chapter_title": "Second"},
                {"number": 3, "chapter_title": "Third"},
                {"number": 10, "chapter_title": "Tenth"},
            ]

            count = rename_chapters(tmpdir, tracks, "Sort Book")

            assert count == 4
            # Track - 1.mp3 should pair with track number 1 (First)
            assert Path(tmpdir, "1 - Sort Book - First.mp3").exists()
            # Track - 10.mp3 should pair with track number 10 (Tenth), NOT track 2
            assert Path(tmpdir, "10 - Sort Book - Tenth.mp3").exists()

    def test_null_chapter_title_falls_back_to_chapter_n(self):
        """Tracks with None or blank chapter_title use 'Chapter {n}' fallback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "1.mp3").write_text("a")
            Path(tmpdir, "2.mp3").write_text("b")
            Path(tmpdir, "3.mp3").write_text("c")

            tracks = [
                {"number": 1, "chapter_title": "Normal Title"},
                {"number": 2, "chapter_title": None},
                {"number": 3, "chapter_title": "   "},  # whitespace-only
            ]

            count = rename_chapters(tmpdir, tracks, "Fallback Book")

            assert count == 3
            assert Path(tmpdir, "1 - Fallback Book - Normal Title.mp3").exists()
            assert Path(tmpdir, "2 - Fallback Book - Chapter 2.mp3").exists()
            assert Path(tmpdir, "3 - Fallback Book - Chapter 3.mp3").exists()

    def test_zero_padding_two_digits_for_twelve_tracks(self):
        """12 tracks produce 2-digit zero-padded numbers (01, 02, ..., 12)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(1, 13):
                Path(tmpdir, f"{i}.mp3").write_text(f"audio{i}")

            tracks = [{"number": i, "chapter_title": f"Ch {i}"} for i in range(1, 13)]

            count = rename_chapters(tmpdir, tracks, "Pad Book")

            assert count == 12
            assert Path(tmpdir, "01 - Pad Book - Ch 1.mp3").exists()
            assert Path(tmpdir, "09 - Pad Book - Ch 9.mp3").exists()
            assert Path(tmpdir, "10 - Pad Book - Ch 10.mp3").exists()
            assert Path(tmpdir, "12 - Pad Book - Ch 12.mp3").exists()

    def test_sanitizes_colons_slashes_and_special_chars_in_titles(self):
        """Colons, slashes, and other illegal chars in chapter titles are cleaned via sanitize()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "1.mp3").write_text("a")

            tracks = [
                {"number": 1, "chapter_title": "Chapter 1: The Beginning / End"},
            ]

            count = rename_chapters(tmpdir, tracks, "Test: Book")

            assert count == 1
            # Colon becomes " -", slash is stripped by sanitize()
            result_file = list(Path(tmpdir).glob("*.mp3"))[0]
            assert "Chapter 1 - The Beginning  End" in result_file.name  # colon replaced, slash removed
            # Also verify book title was sanitized
            assert "Test - Book" in result_file.name  # colon in book title replaced


    def test_non_mp3_files_are_ignored(self):
        """Non-MP3 files in directory are left untouched; only .mp3 files renamed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "1.mp3").write_text("audio")
            Path(tmpdir, "readme.txt").write_text("text")
            Path(tmpdir, "cover.jpg").write_bytes(b"\xff\xd8\xff")

            tracks = [{"number": 1, "chapter_title": "Only Chapter"}]

            count = rename_chapters(tmpdir, tracks, "Filter Book")

            assert count == 1
            assert Path(tmpdir, "1 - Filter Book - Only Chapter.mp3").exists()
            # Non-MP3 files untouched
            assert Path(tmpdir, "readme.txt").exists()
            assert Path(tmpdir, "cover.jpg").exists()


    def test_count_mismatch_fewer_files_than_tracks_renames_available(self):
        """When fewer MP3 files than tracks, renames only available pairs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Only 2 files but 4 tracks
            Path(tmpdir, "1.mp3").write_text("a")
            Path(tmpdir, "2.mp3").write_text("b")

            tracks = [
                {"number": 1, "chapter_title": "Ch 1"},
                {"number": 2, "chapter_title": "Ch 2"},
                {"number": 3, "chapter_title": "Ch 3"},
                {"number": 4, "chapter_title": "Ch 4"},
            ]

            count = rename_chapters(tmpdir, tracks, "Mismatch Book")

            # Should rename min(2, 4) = 2 files
            assert count == 2
            assert Path(tmpdir, "1 - Mismatch Book - Ch 1.mp3").exists()
            assert Path(tmpdir, "2 - Mismatch Book - Ch 2.mp3").exists()


    def test_empty_directory_returns_zero_no_error(self):
        """Empty directory with no MP3 files is a no-op returning 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracks = [{"number": 1, "chapter_title": "Ch 1"}]

            count = rename_chapters(tmpdir, tracks, "Empty Book")

            assert count == 0
            assert list(Path(tmpdir).glob("*.mp3")) == []


    def test_empty_tracks_list_returns_zero(self):
        """Empty tracks list is a no-op even if MP3 files exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "1.mp3").write_text("audio")

            count = rename_chapters(tmpdir, [], "No Tracks")

            assert count == 0
            # Original file should still exist (not renamed)


    def test_idempotent_running_twice_does_not_double_rename_or_error(self):
        """Running rename_chapters twice on same directory produces same result without errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "1.mp3").write_text("a")
            Path(tmpdir, "2.mp3").write_text("b")

            tracks = [
                {"number": 1, "chapter_title": "Alpha"},
                {"number": 2, "chapter_title": "Beta"},
            ]

            # First run
            count1 = rename_chapters(tmpdir, tracks, "Idem Book")
            # Second run on already-renamed files
            count2 = rename_chapters(tmpdir, tracks, "Idem Book")

            assert count1 == 2
            assert count2 == 2
            # Files exist with correct final names
            assert Path(tmpdir, "1 - Idem Book - Alpha.mp3").exists()
            assert Path(tmpdir, "2 - Idem Book - Beta.mp3").exists()
            # No extra files created
            mp3_files = list(Path(tmpdir).glob("*.mp3"))
            assert len(mp3_files) == 2


    def test_all_null_titles_use_chapter_n_fallback_for_all(self):
        """When ALL tracks have null/blank chapter_title, every file gets 'Chapter N'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "1.mp3").write_text("a")
            Path(tmpdir, "2.mp3").write_text("b")
            Path(tmpdir, "3.mp3").write_text("c")

            tracks = [
                {"number": 1, "chapter_title": None},
                {"number": 2, "chapter_title": ""},
                {"number": 3, "chapter_title": "  \t  "},
            ]

            count = rename_chapters(tmpdir, tracks, "No Titles Book")

            assert count == 3
            assert Path(tmpdir, "1 - No Titles Book - Chapter 1.mp3").exists()
            assert Path(tmpdir, "2 - No Titles Book - Chapter 2.mp3").exists()
            assert Path(tmpdir, "3 - No Titles Book - Chapter 3.mp3").exists()


# ---------------------------------------------------------------------------
# Issue #34: Wire rename_chapters() into download pipeline
# ---------------------------------------------------------------------------


class TestRenameChaptersWiring:
    """Integration tests: rename_chapters wired into download pipeline."""

    def test_mp3_only_rename_chapters_true_renames_files(self):
        """mp3_only + rename_chapters=True → MP3 files renamed after extraction."""
        import io
        import zipfile

        # Create ZIP with 2 MP3 files
        mp3_zip_payload = io.BytesIO()
        with zipfile.ZipFile(mp3_zip_payload, "w") as zf:
            zf.writestr("1.mp3", b"audio-1")
            zf.writestr("2.mp3", b"audio-2")
        mp3_zip_data = mp3_zip_payload.getvalue()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/download-manifest":
                return httpx.Response(
                    200,
                    json={
                        "parts": [{"url": "https://cdn.example.com/p1.zip", "name": "p1"}],
                        "tracks": [
                            {"number": 1, "chapter_title": "Prologue"},
                            {"number": 2, "chapter_title": "The Start"},
                        ],
                    },
                )
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=mp3_zip_data)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(title="Rename Test Book", authors=["Author"], narrators=["N"], isbn="9789900000001")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            plan = resolve_output_plan(book, base_dir, format_strategy="mp3_only")
            reporter = DownloadReporter()

            result = download_book(
                book=book,
                session=client,
                plan=plan,
                reporter=reporter,
                rename_chapters=True,  # ← THE KEY PARAMETER (doesn't exist yet — test will fail)
            )

            assert result.status == "downloaded"
            assert result.format == "mp3"

            # Files should be renamed with chapter titles
            output_dir = result.path
            assert (output_dir / "1 - Rename Test Book - Prologue.mp3").exists()
            assert (output_dir / "2 - Rename Test Book - The Start.mp3").exists()
            # Original numeric names should be gone
            assert not (output_dir / "1.mp3").exists()
            assert not (output_dir / "2.mp3").exists()

    def test_m4b_only_rename_chapters_not_called(self):
        """m4b_only + rename_chapters=True → no rename (no MP3s)."""
        m4b_content = b"fake-m4b-data"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/download-manifest":
                return httpx.Response(
                    200,
                    json={
                        "parts": [],
                        "tracks": [{"number": 1, "chapter_title": "Ch1"}],
                    },
                )
            if "/packaged_m4b" in request.url.path:
                return httpx.Response(200, json={"m4b_url": "https://cdn.example.com/book.m4b"})
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=m4b_content)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(title="M4B Only Book", authors=["Author"], narrators=["N"], isbn="9789900000002")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            plan = resolve_output_plan(book, base_dir, format_strategy="m4b_only")
            reporter = DownloadReporter()

            result = download_book(
                book=book,
                session=client,
                plan=plan,
                reporter=reporter,
                rename_chapters=True,  # even with True, M4B should not trigger rename
            )

            assert result.status == "downloaded"
            assert result.format == "m4b"
            # No MP3 files should exist at all
            mp3_files = list(result.path.glob("*.mp3"))
            assert len(mp3_files) == 0

    def test_m4b_mp3_fallback_m4b_success_no_rename_side_effects(self):
        """m4b_mp3_fallback + M4B success + rename_chapters=True → no rename side effects."""
        m4b_content = b"fake-m4b-data"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/download-manifest":
                return httpx.Response(
                    200,
                    json={
                        "parts": [],
                        "tracks": [{"number": 1, "chapter_title": "Ch1"}],
                    },
                )
            # M4B endpoint succeeds → no MP3 fallback
            if "/packaged_m4b" in request.url.path:
                return httpx.Response(200, json={"m4b_url": "https://cdn.example.com/book.m4b"})
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=m4b_content)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(title="M4B Success Fallback Book", authors=["Author"], narrators=["N"], isbn="9789900000007")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            plan = resolve_output_plan(book, base_dir, format_strategy="m4b_mp3_fallback")
            reporter = DownloadReporter()

            result = download_book(
                book=book,
                session=client,
                plan=plan,
                reporter=reporter,
                rename_chapters=True,  # even with True, M4B success should not trigger rename
            )

            assert result.status == "downloaded"
            assert result.format == "m4b"
            # No MP3 files should exist at all (M4B path taken, no fallback)
            mp3_files = list(result.path.glob("*.mp3"))
            assert len(mp3_files) == 0
            # The .m4b file should exist (proving M4B download succeeded)
            m4b_files = list(result.path.glob("*.m4b")) if result.path.is_dir() else []
            if not m4b_files:
                # result.path may be the .m4b file itself for m4b downloads
                assert result.path.exists() and result.path.suffix == ".m4b"

    def test_rename_chapters_false_skips_rename(self):
        """mp3_only + rename_chapters=False (default) → files NOT renamed."""
        import io
        import zipfile

        mp3_zip_payload = io.BytesIO()
        with zipfile.ZipFile(mp3_zip_payload, "w") as zf:
            zf.writestr("1.mp3", b"audio-1")
            zf.writestr("2.mp3", b"audio-2")
        mp3_zip_data = mp3_zip_payload.getvalue()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/download-manifest":
                return httpx.Response(
                    200,
                    json={
                        "parts": [{"url": "https://cdn.example.com/p1.zip", "name": "p1"}],
                        "tracks": [
                            {"number": 1, "chapter_title": "Prologue"},
                            {"number": 2, "chapter_title": "The Start"},
                        ],
                    },
                )
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=mp3_zip_data)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(title="No Rename Book", authors=["Author"], narrators=["N"], isbn="9789900000004")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            plan = resolve_output_plan(book, base_dir, format_strategy="mp3_only")
            reporter = DownloadReporter()

            # rename_chapters defaults to False
            result = download_book(
                book=book,
                session=client,
                plan=plan,
                reporter=reporter,
                rename_chapters=False,
            )

            assert result.status == "downloaded"
            assert result.format == "mp3"

            output_dir = result.path
            # Original numeric names should still exist (not renamed)
            assert (output_dir / "1.mp3").exists()
            assert (output_dir / "2.mp3").exists()
            # Renamed versions should NOT exist
            assert not (output_dir / "1 - No Rename Book - Prologue.mp3").exists()

    def test_m4b_mp3_fallback_renames_on_fallback(self):
        """m4b_mp3_fallback: M4B fails, MP3 fallback + rename_chapters=True → renamed."""
        import io
        import zipfile

        mp3_zip_payload = io.BytesIO()
        with zipfile.ZipFile(mp3_zip_payload, "w") as zf:
            zf.writestr("1.mp3", b"audio-1")
            zf.writestr("2.mp3", b"audio-2")
            zf.writestr("3.mp3", b"audio-3")
        mp3_zip_data = mp3_zip_payload.getvalue()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/download-manifest":
                return httpx.Response(
                    200,
                    json={
                        "parts": [{"url": "https://cdn.example.com/p1.zip", "name": "p1"}],
                        "tracks": [
                            {"number": 1, "chapter_title": "Opening"},
                            {"number": 2, "chapter_title": "Middle"},
                            {"number": 3, "chapter_title": "Closing"},
                        ],
                    },
                )
            # M4B endpoint returns error → triggers fallback
            if request.url.path == "/api/v10/m4b":
                return httpx.Response(404)
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=mp3_zip_data)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(title="Fallback Book", authors=["Author"], narrators=["N"], isbn="9789900000003")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            plan = resolve_output_plan(book, base_dir, format_strategy="m4b_mp3_fallback")
            reporter = DownloadReporter()

            result = download_book(
                book=book,
                session=client,
                plan=plan,
                reporter=reporter,
                rename_chapters=True,
            )

            assert result.status == "downloaded"
            assert result.format == "mp3"

            output_dir = result.path
            assert (output_dir / "1 - Fallback Book - Opening.mp3").exists()
            assert (output_dir / "2 - Fallback Book - Middle.mp3").exists()
            assert (output_dir / "3 - Fallback Book - Closing.mp3").exists()

    def test_count_mismatch_produces_warning(self, caplog):
        """MP3 file count != track count → warning logged (no crash)."""
        import io
        import zipfile

        mp3_zip_payload = io.BytesIO()
        with zipfile.ZipFile(mp3_zip_payload, "w") as zf:
            zf.writestr("1.mp3", b"audio-1")
            zf.writestr("2.mp3", b"audio-2")
            zf.writestr("3.mp3", b"audio-3")  # 3 files but only 2 tracks
        mp3_zip_data = mp3_zip_payload.getvalue()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/download-manifest":
                return httpx.Response(
                    200,
                    json={
                        "parts": [{"url": "https://cdn.example.com/p1.zip", "name": "p1"}],
                        "tracks": [
                            {"number": 1, "chapter_title": "Ch1"},
                            {"number": 2, "chapter_title": "Ch2"},
                        ],
                    },
                )
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=mp3_zip_data)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(title="Mismatch Book", authors=["Author"], narrators=["N"], isbn="9789900000005")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            plan = resolve_output_plan(book, base_dir, format_strategy="mp3_only")
            reporter = DownloadReporter()

            caplog.set_level("WARNING", logger="librofm_downloader.downloader")
            result = download_book(
                book=book,
                session=client,
                plan=plan,
                reporter=reporter,
                rename_chapters=True,
            )

            assert result.status == "downloaded"
            messages = [r.message for r in caplog.records]
            assert any("mismatch" in m.lower() for m in messages), \
                f"Expected count-mismatch warning, got: {messages}"

    def test_rename_logs_each_operation(self, caplog):
        """rename_chapters=True → info log shows renamed file count."""
        import io
        import zipfile
        import logging

        mp3_zip_payload = io.BytesIO()
        with zipfile.ZipFile(mp3_zip_payload, "w") as zf:
            zf.writestr("1.mp3", b"audio-1")
            zf.writestr("2.mp3", b"audio-2")
        mp3_zip_data = mp3_zip_payload.getvalue()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/download-manifest":
                return httpx.Response(
                    200,
                    json={
                        "parts": [{"url": "https://cdn.example.com/p1.zip", "name": "p1"}],
                        "tracks": [
                            {"number": 1, "chapter_title": "Alpha"},
                            {"number": 2, "chapter_title": "Beta"},
                        ],
                    },
                )
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=mp3_zip_data)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(title="Log Test Book", authors=["Author"], narrators=["N"], isbn="9789900000006")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            plan = resolve_output_plan(book, base_dir, format_strategy="mp3_only")
            reporter = DownloadReporter()

            with caplog.at_level(logging.INFO, logger="librofm_downloader.downloader"):
                result = download_book(
                    book=book,
                    session=client,
                    plan=plan,
                    reporter=reporter,
                    rename_chapters=True,
                )

            assert result.status == "downloaded"

            # Should have an INFO log about renaming
            info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
            assert any("renamed" in m.lower() for m in info_messages), \
                f"Expected 'renamed' info message, got: {info_messages}"
            assert any("log test book" in m.lower() for m in info_messages), \
                f"Expected book title in log, got: {info_messages}"

    def test_special_chars_in_chapter_titles_sanitized(self):
        """Special characters in chapter titles are sanitized through full pipeline."""
        import io
        import zipfile

        mp3_zip_payload = io.BytesIO()
        with zipfile.ZipFile(mp3_zip_payload, "w") as zf:
            zf.writestr("1.mp3", b"audio-1")
            zf.writestr("2.mp3", b"audio-2")
        mp3_zip_data = mp3_zip_payload.getvalue()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/download-manifest":
                return httpx.Response(
                    200,
                    json={
                        "parts": [{"url": "https://cdn.example.com/p1.zip", "name": "p1"}],
                        "tracks": [
                            {"number": 1, "chapter_title": "Introduction: The <Beginning>"},
                            {"number": 2, "chapter_title": 'Chapter 1: "Hello / World"?'},
                        ],
                    },
                )
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=mp3_zip_data)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(title='Test: A Book (2024)', authors=["Author"], narrators=["N"], isbn="9789900000007")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            plan = resolve_output_plan(book, base_dir, format_strategy="mp3_only")
            reporter = DownloadReporter()

            result = download_book(
                book=book,
                session=client,
                plan=plan,
                reporter=reporter,
                rename_chapters=True,
            )

            assert result.status == "downloaded"
            assert result.format == "mp3"

            output_dir = result.path
            # Original numeric names should be gone
            assert not (output_dir / "1.mp3").exists()
            assert not (output_dir / "2.mp3").exists()

            # Renamed files should exist with sanitized names (no special chars)
            mp3_files = sorted(output_dir.glob("*.mp3"))
            assert len(mp3_files) >= 2
            for f in mp3_files:
                name = f.name
                for char in '/:<>\\|?*':
                    assert char not in name, (
                        f"Special character '{char}' found in filename: {name}"
                    )

    def test_hundred_plus_chapters_three_digit_padding(self):
        """100+ chapters → zero-padded to 3 digits (001, 002, … 099, 100, 101)."""
        import io
        import zipfile

        num_tracks = 105
        mp3_zip_payload = io.BytesIO()
        with zipfile.ZipFile(mp3_zip_payload, "w") as zf:
            for i in range(1, num_tracks + 1):
                zf.writestr(f"{i}.mp3", f"audio-{i}".encode())
        mp3_zip_data = mp3_zip_payload.getvalue()

        track_titles = [f"Chapter {i}" for i in range(1, num_tracks + 1)]

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/download-manifest":
                return httpx.Response(
                    200,
                    json={
                        "parts": [{"url": "https://cdn.example.com/p1.zip", "name": "p1"}],
                        "tracks": [
                            {"number": i, "chapter_title": title}
                            for i, title in enumerate(track_titles, start=1)
                        ],
                    },
                )
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=mp3_zip_data)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(title="Big Book", authors=["Author"], narrators=["N"], isbn="9789900000007")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            plan = resolve_output_plan(book, base_dir, format_strategy="mp3_only")
            reporter = DownloadReporter()

            result = download_book(
                book=book,
                session=client,
                plan=plan,
                reporter=reporter,
                rename_chapters=True,
            )

            assert result.status == "downloaded"
            assert result.format == "mp3"

            output_dir = result.path
            # Original numeric names should all be gone
            for i in range(1, num_tracks + 1):
                assert not (output_dir / f"{i}.mp3").exists(), \
                    f"Original name {i}.mp3 should be renamed"

            # Three-digit zero-padded renamed files — spot-check boundaries
            assert (output_dir / "001 - Big Book - Chapter 1.mp3").exists()
            assert (output_dir / "005 - Big Book - Chapter 5.mp3").exists()
            assert (output_dir / "099 - Big Book - Chapter 99.mp3").exists()
            # The 99→100 transition is the critical boundary
            assert (output_dir / "100 - Big Book - Chapter 100.mp3").exists()
            assert (output_dir / "101 - Big Book - Chapter 101.mp3").exists()
            assert (output_dir / "105 - Big Book - Chapter 105.mp3").exists()

            # Exactly 105 MP3 files
            mp3_files = list(output_dir.glob("*.mp3"))
            assert len(mp3_files) == num_tracks
    def test_single_track_zero_padding(self):
        """Single-track book: zero-padding width=1, no leading zero."""
        import io
        import zipfile

        mp3_zip_payload = io.BytesIO()
        with zipfile.ZipFile(mp3_zip_payload, "w") as zf:
            zf.writestr("1.mp3", b"audio-only")
        mp3_zip_data = mp3_zip_payload.getvalue()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/download-manifest":
                return httpx.Response(
                    200,
                    json={
                        "parts": [{"url": "https://cdn.example.com/p1.zip", "name": "p1"}],
                        "tracks": [
                            {"number": 1, "chapter_title": "Only Chapter"},
                        ],
                    },
                )
            if "cdn.example.com" in request.url.host:
                return httpx.Response(200, content=mp3_zip_data)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = LibroFmSession(base_url="https://libro.fm", username="u", password="p", transport=transport)
        client.authenticate()

        book = Book(title="Single Track Book", authors=["Author"], narrators=["N"], isbn="9789900000008")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            plan = resolve_output_plan(book, base_dir, format_strategy="mp3_only")
            reporter = DownloadReporter()

            result = download_book(
                book=book,
                session=client,
                plan=plan,
                reporter=reporter,
                rename_chapters=True,
            )

            assert result.status == "downloaded"
            assert result.format == "mp3"

            output_dir = result.path
            # Original numeric name gone
            assert not (output_dir / "1.mp3").exists()
            # Renamed with single-digit (width=1 for 1 track)
            assert (output_dir / "1 - Single Track Book - Only Chapter.mp3").exists()
            # Exactly 1 MP3 file
            assert len(list(output_dir.glob("*.mp3"))) == 1