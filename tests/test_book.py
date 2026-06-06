"""Tests for librofm_downloader.book — Book dataclass and from_library_row() intake."""

from librofm_downloader.book import Book, from_library_row


class TestFromLibraryRowComplete:
    """Tracer bullet: from_library_row converts a full API dict to Book correctly."""

    def test_all_fields_populated(self):
        raw = {
            "title": "The Great Adventure",
            "authors": ["Jane Author"],
            "narrators": ["Bob Narrator"],
            "isbn": "9781234567890",
            "series": "Adventure Series",
            "series_num": 3,
            "cover_url": "https://cdn.libro.fm/covers/123.jpg",
            "audiobook_info": {
                "narrators": ["Carol Narrator"],
                "pdf_extras": True,
            },
            "publication_year": 2024,
            "publication_month": 6,
            "publication_day": 15,
        }

        book = from_library_row(raw)

        assert book == Book(
            title="The Great Adventure",
            authors=["Jane Author"],
            narrators=["Carol Narrator"],  # audiobook_info.narrators takes priority
            isbn="9781234567890",
            series="Adventure Series",
            series_num=3,
            cover_url="https://cdn.libro.fm/covers/123.jpg",
            pdf_extras=True,
            publication_year=2024,
            publication_month=6,
            publication_day=15,
        )


class TestMissingFields:
    """from_library_row applies correct defaults when raw dict is empty."""

    def test_all_defaults_when_empty(self):
        book = from_library_row({})

        assert book.title == "Unknown"
        assert book.authors == []
        assert book.narrators == []
        assert book.isbn == "?"
        assert book.series == ""
        assert book.series_num is None
        assert book.cover_url == ""
        assert book.pdf_extras is False
        assert book.publication_year is None
        assert book.publication_month is None
        assert book.publication_day is None


class TestIsbnCoercion:
    """API sometimes returns ISBN as int; from_library_row always stores str."""

    def test_int_isbn_coerced_to_string(self):
        raw = {"isbn": 9781234567890}
        book = from_library_row(raw)
        assert book.isbn == "9781234567890"
        assert isinstance(book.isbn, str)

    def test_string_isbn_passthrough(self):
        raw = {"isbn": "9781234567890"}
        book = from_library_row(raw)
        assert book.isbn == "9781234567890"

    def test_missing_isbn_default(self):
        book = from_library_row({})
        assert book.isbn == "?"


class TestNarratorResolution:
    """Narrators can live in audiobook_info.narrators (priority) or top-level."""

    def test_audiobook_info_narrators_takes_priority(self):
        raw = {
            "narrators": ["Top-Level Narrator"],
            "audiobook_info": {"narrators": ["Nested Narrator"]},
        }
        book = from_library_row(raw)
        assert book.narrators == ["Nested Narrator"]

    def test_fallback_to_top_level_narrators(self):
        raw = {
            "narrators": ["Top-Level Narrator"],
            "audiobook_info": {},  # no narrators key inside
        }
        book = from_library_row(raw)
        assert book.narrators == ["Top-Level Narrator"]

    def test_both_missing_gives_empty_list(self):
        raw = {"audiobook_info": {}}
        book = from_library_row(raw)
        assert book.narrators == []

    def test_no_audiobook_info_uses_top_level(self):
        raw = {"narrators": ["Only Narrator"]}
        book = from_library_row(raw)
        assert book.narrators == ["Only Narrator"]

    def test_no_audiobook_info_and_no_top_level_gives_empty(self):
        book = from_library_row({})
        assert book.narrators == []


class TestPdfExtrasBoolCoercion:
    """PDF extras field needs robust bool coercion from various API shapes."""

    def test_true_bool(self):
        raw = {"audiobook_info": {"pdf_extras": True}}
        assert from_library_row(raw).pdf_extras is True

    def test_false_bool(self):
        raw = {"audiobook_info": {"pdf_extras": False}}
        assert from_library_row(raw).pdf_extras is False

    def test_truthy_int_one(self):
        raw = {"audiobook_info": {"pdf_extras": 1}}
        assert from_library_row(raw).pdf_extras is True

    def test_falsy_int_zero(self):
        raw = {"audiobook_info": {"pdf_extras": 0}}
        assert from_library_row(raw).pdf_extras is False

    def test_pdf_extras_key_missing(self):
        raw = {"audiobook_info": {}}
        assert from_library_row(raw).pdf_extras is False

    def test_audiobook_info_key_missing(self):
        assert from_library_row({}).pdf_extras is False
