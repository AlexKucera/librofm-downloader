"""Interactive book selection via questionary checkbox prompt.

Public API: select_books(books) -> list[Book]
Internal helper: _format_row(book, index) -> str
"""

import questionary

from librofm_downloader.book import Book


def _format_row(book: Book, index: int) -> str:
    """Format a Book into a display string for the checkbox prompt.

    Format: "N. Title — First Author [Series #N]"
    Series suffix omitted when absent. Author falls back to "Unknown".
    """
    author = book.authors[0] if book.authors else "Unknown"
    base = f"{index}. {book.title} — {author}"
    if book.series and book.series_num is not None:
        base += f" [{book.series} #{book.series_num}]"
    return base


def select_books(books: list[Book]) -> list[Book]:
    """Present an interactive checkbox prompt and return selected Books.

    Returns selected Books in their original input order.
    Returns empty list on zero selection or confirmation rejection.
    Propagates KeyboardInterrupt from the checkbox prompt.
    """
    rows = [_format_row(b, i + 1) for i, b in enumerate(books)]
    chosen = questionary.checkbox(
        "Select books to download:",
        choices=rows,
    ).unsafe_ask()

    if not chosen:
        print("No books selected. Exiting.")
        return []

    # Map display rows back to Book objects
    row_to_book = {row: book for row, book in zip(rows, books)}
    selected = [row_to_book[row] for row in chosen]

    # Confirmation prompt
    print(f"{len(selected)} book(s) selected for download:")
    for book in selected:
        print(f"  - {book.title}")

    if not questionary.confirm("Proceed with download?", default=False).ask():
        return []

    # Return in original input order
    selected_set = {id(b) for b in selected}
    return [b for b in books if id(b) in selected_set]
