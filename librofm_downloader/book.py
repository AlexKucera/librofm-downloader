"""Book domain model and API-shape intake for librofm-downloader.

Owns the Book dataclass and the from_library_row() intake function that
converts raw Libro.fm API dicts into Book objects. No knowledge of raw
API dict shape should exist outside this module.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Book:
    """Immutable book metadata record from Libro.fm."""

    title: str
    authors: list[str]
    narrators: list[str]
    isbn: str
    series: str = ""
    series_num: int | None = None
    cover_url: str = ""
    pdf_extras: bool = False
    publication_year: int | None = None
    publication_month: int | None = None
    publication_day: int | None = None


def from_library_row(raw: dict) -> Book:
    """Convert a Libro.fm API dict to a Book object.

    Handles ISBN str coercion (API sometimes returns int),
    nested narrator resolution, PDF extras bool coercion,
    and default values for missing fields.
    """
    audiobook_info = raw.get("audiobook_info", {}) or {}
    narrators = audiobook_info.get("narrators", []) or raw.get("narrators", [])

    raw_isbn = raw.get("isbn", "?")
    isbn = str(raw_isbn) if raw_isbn is not None else "?"

    return Book(
        title=raw.get("title", "Unknown"),
        authors=raw.get("authors", []),
        narrators=narrators,
        isbn=isbn,
        series=raw.get("series", ""),
        series_num=raw.get("series_num"),
        cover_url=raw.get("cover_url", ""),
        pdf_extras=bool(audiobook_info.get("pdf_extras")) if audiobook_info else False,
        publication_year=raw.get("publication_year"),
        publication_month=raw.get("publication_month"),
        publication_day=raw.get("publication_day"),
    )
