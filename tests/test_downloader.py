"""Tests for librofm_downloader.downloader — TDD vertical slices."""

import httpx
import pytest
from pathlib import Path
import tempfile

from librofm_downloader.downloader import (
    Book,
    needs_subdirectory,
    resolve_path,
    sanitize,
    download_m4b,
    download_zip_part,
    download_book,
)
from librofm_downloader.client import LibroFmClient
from librofm_downloader.history import DownloadHistory


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

    def test_true_when_cover_url_present(self):
        book = Book(
            title="Some Book",
            authors=["Author"],
            narrators=["Narrator"],
            isbn="9780000000001",
            pdf_extras=False,
            cover_url="https://example.com/cover.jpg",
        )
        assert needs_subdirectory(book) is True

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
# Orchestration: resolve path → query M4B → download → update history
# ---------------------------------------------------------------------------


class TestDownloadBook:
    """End-to-end orchestration with mocked HTTP."""

    def test_writes_history_entry_after_successful_download(self):
        """After successful M4B download, history entry is persisted."""
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
        client = LibroFmClient(base_url="https://libro.fm", username="u", password="p")
        client.authenticate(transport=transport)

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

            result = download_book(
                book=book,
                client=client,
                output_base=base_dir,
                history=history,
                transport=transport,
            )

            # History was written
            assert history.is_downloaded("9781111111111")
            entry = history.find("9781111111111")
            assert entry is not None
            assert entry.format == "m4b"
            assert entry.title == "History Test Book"

    def test_skips_book_without_m4b(self):
        """Book with no M4B available → returns None, no history entry, no error."""
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
        client = LibroFmClient(base_url="https://libro.fm", username="u", password="p")
        client.authenticate(transport=transport)

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

            result = download_book(
                book=book,
                client=client,
                output_base=base_dir,
                history=history,
                transport=transport,
            )

            # Returns None (skipped)
            assert result is None
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
        client = LibroFmClient(base_url="https://libro.fm", username="u", password="p")
        client.authenticate(transport=transport)

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

            with pytest.raises(httpx.HTTPStatusError):
                download_book(
                    book=book,
                    client=client,
                    output_base=base_dir,
                    history=history,
                    transport=transport,
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
        client = LibroFmClient(base_url="https://libro.fm", username="u", password="p")
        client.authenticate(transport=transport)

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

            result = download_book(
                book=book,
                client=client,
                output_base=base_dir,
                history=history,
                transport=transport,
            )

            # File is at leaf (flat), not inside a subdirectory
            assert result is not None
            # Path should be base/Author/Title.m4b (flat) — title is filename stem
            assert result.stem == "Standalone Book"
            # No extra subdirectory between author and file
            assert result.parent.name == "Solo Author"
            assert result.exists()


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
        client = LibroFmClient(base_url="https://libro.fm", username="u", password="p")
        client.authenticate(transport=transport)

        book = Book(title="M4B Available", authors=["A"], narrators=["N"], isbn="9781111111111")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            history_path = Path(tmpdir) / "history.json"
            history = DownloadHistory(history_path)

            result = download_book(
                book=book,
                client=client,
                output_base=base_dir,
                history=history,
                format_strategy="m4b_mp3_fallback",
                transport=transport,
            )

            # M4B was downloaded (not MP3)
            assert result is not None
            assert result.suffix == ".m4b"
            # Manifest was never queried
            assert len(mp3_calls) == 0
            # History records M4B format
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
        client = LibroFmClient(base_url="https://libro.fm", username="u", password="p")
        client.authenticate(transport=transport)

        book = Book(title="MP3 Fallback Book", authors=["A"], narrators=["N"], isbn="9782222222222")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            history_path = Path(tmpdir) / "history.json"
            history = DownloadHistory(history_path)

            result = download_book(
                book=book,
                client=client,
                output_base=base_dir,
                history=history,
                format_strategy="m4b_mp3_fallback",
                transport=transport,
            )

            # MP3 files were extracted
            assert result is not None
            # At least one .mp3 file exists in output tree
            mp3_files = list(base_dir.rglob("*.mp3"))
            assert len(mp3_files) >= 1
            # History records mp3 format
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
        client = LibroFmClient(base_url="https://libro.fm", username="u", password="p")
        client.authenticate(transport=transport)

        book = Book(title="MP3 Only Book", authors=["A"], narrators=["N"], isbn="9783333333333")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            history_path = Path(tmpdir) / "history.json"
            history = DownloadHistory(history_path)

            result = download_book(
                book=book,
                client=client,
                output_base=base_dir,
                history=history,
                format_strategy="mp3_only",
                transport=transport,
            )

            # MP3 files extracted
            assert result is not None
            mp3_files = list(base_dir.rglob("*.mp3"))
            assert len(mp3_files) >= 1
            # M4B was never queried
            assert len(m4b_calls) == 0
            # History records mp3 format
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
        client = LibroFmClient(base_url="https://libro.fm", username="u", password="p")
        client.authenticate(transport=transport)

        book = Book(title="No M4B Skip", authors=["A"], narrators=["N"], isbn="9780000000000")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "audiobooks"
            history_path = Path(tmpdir) / "history.json"
            history = DownloadHistory(history_path)

            result = download_book(
                book=book,
                client=client,
                output_base=base_dir,
                history=history,
                format_strategy="m4b_only",
                transport=transport,
            )

            # Skipped (no M4B)
            assert result is None
            # Manifest was never queried
            assert len(manifest_calls) == 0
            # No history entry
            assert history.is_downloaded("9780000000000") is False