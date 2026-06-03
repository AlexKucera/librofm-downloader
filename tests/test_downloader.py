"""Tests for librofm_downloader.downloader — TDD vertical slices."""

import pytest

from librofm_downloader.downloader import Book, needs_subdirectory, resolve_path, sanitize


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
