"""Tests for librofm_downloader.path — TDD vertical slices."""

import tempfile
import unittest
from pathlib import Path

import pytest

from librofm_downloader.book import Book
from librofm_downloader.path import (
    OutputPlan,
    needs_subdirectory,
    _resolve_output_dir,
    resolve_output_plan,
    resolve_path,
    sanitize,
)


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

    def test_truthy_int_pdf_extras_is_true(self):
        """pdf_extras=1 (int from API) coerces to bool True."""
        book = Book(
            title="Int Extras",
            authors=["Author"],
            narrators=["Narrator"],
            isbn="9780000000002",
            pdf_extras=1,
        )
        assert needs_subdirectory(book) is True


# ---------------------------------------------------------------------------
# Output directory resolution
# ---------------------------------------------------------------------------


class TestResolveOutputDir:
    """Integration tests for output directory structure with/without extras."""

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

    def test_resolve_output_dir_subdir_for_cover_with_download_covers(self):
        """download_covers=True + cover_url → creates subdirectory for accompaniment."""
        from librofm_downloader.config import Config

        book = Book(
            title="Cover Subdir Book",
            authors=["Author Name"],
            narrators=["Narrator"],
            isbn="9787777777779",
            pdf_extras=False,
            cover_url="https://cdn.example.com/cover.jpg",
        )

        config = Config(
            username="u", password="p", format="m4b_mp3_fallback",
            output_dir="/tmp", download_covers=True, download_extras=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "audiobooks"
            output_dir = _resolve_output_dir(book, base, config=config)

            # With download_covers + cover_url → subdirectory
            expected = base / "Author Name" / "Cover Subdir Book"
            assert output_dir == expected

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
            assert output_dir == base / "Author Name"

    def test_resolve_output_dir_string_base(self):
        """Accepts string output_base (converted to Path internally)."""
        book = Book(
            title="String Base",
            authors=["Author Name"],
            narrators=["Narrator"],
            isbn="9781111111111",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = _resolve_output_dir(book, tmpdir)
            assert output_dir == Path(tmpdir) / "Author Name"


# ---------------------------------------------------------------------------
# OutputPlan resolution
# ---------------------------------------------------------------------------


class TestResolveOutputPlan:
    """OutputPlan frozen dataclass and resolve_output_plan() function."""

    def test_happy_path_all_enabled(self):
        """Default pattern with all flags enabled produces all 4 paths."""
        from librofm_downloader.config import Config
        from librofm_downloader.path import OutputPlan, resolve_output_plan

        book = Book(
            title="The Final Empire",
            authors=["Brandon Sanderson"],
            narrators=["Michael Kramer"],
            isbn="9780765374991",
            series="Mistborn",
            series_num=1,
            cover_url="https://covers.libro.fm/cover.jpg",
            pdf_extras=True,
        )

        config = Config(
            username="u", password="p", format="m4b_mp3_fallback",
            output_dir="/tmp", download_covers=True, download_extras=True,
        )

        plan = resolve_output_plan(book, "/audiobooks", config)

        # OutputPlan is a frozen dataclass with expected fields
        assert isinstance(plan, OutputPlan)

        # Audio path: sanitized title + .m4b extension
        assert plan.audio_path.name == "The Final Empire.m4b"
        assert plan.audio_path.suffix == ".m4b"

        # Partial path is audio_path + ".partial"
        assert str(plan.partial_path) == f"{str(plan.audio_path)}.partial"

        # Cover path populated (covers enabled + cover_url present)
        assert plan.cover_path is not None
        assert plan.cover_path.name == "cover.jpg"

        # PDF path populated (extras enabled + pdf_extras True)
        assert plan.pdf_path is not None
        assert plan.pdf_path.name == "map.pdf"

        # All file paths share the same parent directory (resolved output dir)
        assert plan.audio_path.parent == plan.cover_path.parent
        assert plan.audio_path.parent == plan.pdf_path.parent

        # Subdirectory layout because pdf_extras=True
        assert plan.audio_path.is_relative_to(Path("/audiobooks"))

    def test_custom_output_pattern(self):
        """Custom pattern overrides default path structure."""
        from librofm_downloader.config import Config

        book = Book(
            title="The Final Empire",
            authors=["Brandon Sanderson"],
            narrators=["Michael Kramer"],
            isbn="9780765374991",
            series="Mistborn",
            series_num=1,
        )

        config = Config(
            username="u", password="p", format="m4b_mp3_fallback",
            output_dir="/tmp", download_covers=False, download_extras=False,
        )

        plan = resolve_output_plan(book, "/audiobooks", config)

        # Audio path should exist even without extras
        assert plan.audio_path.name == "The Final Empire.m4b"
        # Flat layout (no extras) → under author directory
        assert "Brandon" in str(plan.audio_path)

    def test_cover_disabled_returns_none(self):
        """download_covers=False → cover_path is None regardless of cover_url."""
        from librofm_downloader.config import Config

        book = Book(
            title="No Cover Book",
            authors=["Author"],
            narrators=["Nar"],
            isbn="9780000000001",
            cover_url="https://covers.libro.fm/cover.jpg",
        )

        config = Config(
            username="u", password="p", format="m4b_mp3_fallback",
            output_dir="/tmp", download_covers=False, download_extras=False,
        )

        plan = resolve_output_plan(book, "/audiobooks", config)
        assert plan.cover_path is None

    def test_pdf_disabled_returns_none(self):
        """download_extras=False → pdf_path is None regardless of pdf_extras."""
        from librofm_downloader.config import Config

        book = Book(
            title="No PDF Book",
            authors=["Author"],
            narrators=["Nar"],
            isbn="9780000000002",
            pdf_extras=True,
        )

        config = Config(
            username="u", password="p", format="m4b_mp3_fallback",
            output_dir="/tmp", download_covers=False, download_extras=False,
        )

        plan = resolve_output_plan(book, "/audiobooks", config)
        assert plan.pdf_path is None

    def test_no_cover_url_returns_none(self):
        """Empty cover_url → cover_path is None even with download_covers=True."""
        from librofm_downloader.config import Config

        book = Book(
            title="No URL Book",
            authors=["Author"],
            narrators=["Nar"],
            isbn="9780000000003",
            cover_url="",  # empty string = no cover available
        )

        config = Config(
            username="u", password="p", format="m4b_mp3_fallback",
            output_dir="/tmp", download_covers=True, download_extras=False,
        )

        plan = resolve_output_plan(book, "/audiobooks", config)
        assert plan.cover_path is None

    def test_no_pdf_extras_returns_none(self):
        """pdf_extras=False → pdf_path is None even with download_extras=True."""
        from librofm_downloader.config import Config

        book = Book(
            title="No Extras Book",
            authors=["Author"],
            narrators=["Nar"],
            isbn="9780000000004",
            pdf_extras=False,
        )

        config = Config(
            username="u", password="p", format="m4b_mp3_fallback",
            output_dir="/tmp", download_covers=False, download_extras=True,
        )

        plan = resolve_output_plan(book, "/audiobooks", config)
        assert plan.pdf_path is None

    def test_string_output_base_accepted(self):
        """String output_base works (converted to Path internally)."""
        from librofm_downloader.config import Config

        book = Book(
            title="String Base Book",
            authors=["Author"],
            narrators=["Nar"],
            isbn="9780000000005",
        )

        config = Config(
            username="u", password="p", format="m4b_mp3_fallback",
            output_dir="/tmp", download_covers=False, download_extras=False,
        )

        # Should not raise; should return a plan with absolute paths
        plan = resolve_output_plan(book, "/some/string/base", config)
        assert isinstance(plan.audio_path, Path)
        assert plan.audio_path.is_absolute()

    def test_subdirectory_layout_when_pdf_extras_true(self):
        """pdf_extras=True creates subdirectory layout (Author/Title/)."""
        from librofm_downloader.config import Config

        book = Book(
            title="Subdir Layout",
            authors=["Author Name"],
            narrators=["Nar"],
            isbn="9780000000006",
            pdf_extras=True,
        )

        config = Config(
            username="u", password="p", format="m4b_mp3_fallback",
            output_dir="/tmp", download_covers=True, download_extras=True,
        )

        plan = resolve_output_plan(book, "/audiobooks", config)

        # Should be /audiobooks/Author Name/Subdir Layout/The Final Empire.m4b
        expected_parent = Path("/audiobooks") / "Author Name" / "Subdir Layout"
        assert plan.audio_path.parent == expected_parent

    def test_flat_layout_when_no_extras(self):
        """No extras + no cover → flat layout (audio file under author dir)."""
        from librofm_downloader.config import Config

        book = Book(
            title="Flat Layout",
            authors=["Author Name"],
            narrators=["Nar"],
            isbn="9780000000007",
        )

        config = Config(
            username="u", password="p", format="m4b_mp3_fallback",
            output_dir="/tmp", download_covers=False, download_extras=False,
        )

        plan = resolve_output_plan(book, "/audiobooks", config)

        # Flat: audio is leaf under author dir
        expected_parent = Path("/audiobooks") / "Author Name"
        assert plan.audio_path.parent == expected_parent

    def test_output_plan_is_frozen(self):
        """OutputPlan is immutable (frozen dataclass)."""
        from dataclasses import FrozenInstanceError
        from librofm_downloader.config import Config

        book = Book(title="Test", authors=["A"], narrators=["N"], isbn="9780000000008")
        config = Config(
            username="u", password="p", format="m4b_mp3_fallback",
            output_dir="/tmp", download_covers=False, download_extras=False,
        )
        plan = resolve_output_plan(book, "/base", config)

        with pytest.raises(FrozenInstanceError):
            plan.audio_path = Path("/other")  # type: ignore[misc]
