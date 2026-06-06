"""Tests for selector.py — interactive book selection."""

import unittest.mock as mock

from librofm_downloader.book import Book
from librofm_downloader.selector import _format_row, select_books


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _book(title, authors=None, **kw):
    """Convenience Book factory for tests."""
    return Book(
        title=title,
        authors=authors or ["Author"],
        narrators=[],
        isbn=kw.pop("isbn", "0000"),
        **kw,
    )


# ---------------------------------------------------------------------------
# _format_row
# ---------------------------------------------------------------------------

def test_format_row_with_series():
    book = Book(
        title="The Way of Kings",
        authors=["Brandon Sanderson"],
        narrators=["Michael Kramer"],
        isbn="9780765365279",
        series="Stormlight Archive",
        series_num=1,
    )
    assert _format_row(book, 3) == "3. The Way of Kings — Brandon Sanderson [Stormlight Archive #1]"


def test_format_row_without_series():
    book = Book(
        title="Project Hail Mary",
        authors=["Andy Weir"],
        narrators=["Ray Porter"],
        isbn="9780593135204",
    )
    assert _format_row(book, 1) == "1. Project Hail Mary — Andy Weir"


def test_format_row_no_authors_falls_back_to_unknown():
    book = Book(
        title="Mystery Book",
        authors=[],
        narrators=[],
        isbn="0000000000",
    )
    assert _format_row(book, 5) == "5. Mystery Book — Unknown"


# ---------------------------------------------------------------------------
# select_books
# ---------------------------------------------------------------------------

def test_select_books_returns_selected_in_original_order():
    books = [_book("A"), _book("B"), _book("C"), _book("D")]
    with mock.patch("librofm_downloader.selector.questionary") as q:
        q.checkbox.return_value.unsafe_ask.return_value = ["3. C — Author", "1. A — Author"]
        q.confirm.return_value.ask.return_value = True
        result = select_books(books)
    assert [b.title for b in result] == ["A", "C"]


def test_select_books_returns_empty_on_zero_selection(capsys):
    books = [_book("A"), _book("B")]
    with mock.patch("librofm_downloader.selector.questionary") as q:
        q.checkbox.return_value.unsafe_ask.return_value = []
        result = select_books(books)
    assert result == []
    assert "No books selected" in capsys.readouterr().out


def test_select_books_returns_empty_on_confirm_rejection():
    books = [_book("A"), _book("B")]
    with mock.patch("librofm_downloader.selector.questionary") as q:
        q.checkbox.return_value.unsafe_ask.return_value = ["1. A — Author"]
        q.confirm.return_value.ask.return_value = False  # N / bare Enter
        result = select_books(books)
    assert result == []


def test_select_books_returns_books_on_confirm_acceptance(capsys):
    books = [_book("Alpha"), _book("Beta")]
    with mock.patch("librofm_downloader.selector.questionary") as q:
        q.checkbox.return_value.unsafe_ask.return_value = ["2. Beta — Author"]
        q.confirm.return_value.ask.return_value = True  # y/Y
        result = select_books(books)
    assert [b.title for b in result] == ["Beta"]
    out = capsys.readouterr().out
    assert "1 book(s) selected" in out
    assert "- Beta" in out


def test_select_books_propagates_keyboard_interrupt():
    books = [_book("A")]
    with mock.patch("librofm_downloader.selector.questionary") as q:
        q.checkbox.return_value.unsafe_ask.side_effect = KeyboardInterrupt
        try:
            select_books(books)
        except KeyboardInterrupt:
            pass  # expected
        else:
            raise AssertionError("Should have propagated KeyboardInterrupt")


def test_select_books_single_book_library():
    books = [_book("Solo")]
    with mock.patch("librofm_downloader.selector.questionary") as q:
        q.checkbox.return_value.unsafe_ask.return_value = ["1. Solo — Author"]
        q.confirm.return_value.ask.return_value = True
        result = select_books(books)
    assert [b.title for b in result] == ["Solo"]
