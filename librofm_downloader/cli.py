"""CLI entry point — wire config → auth → fetch library → download → history."""

import sys
from pathlib import Path

from rich.console import Console

from librofm_downloader.config import load_config, ConfigError
from librofm_downloader.client import LibroFmClient, AuthError
from librofm_downloader.history import DownloadHistory
from librofm_downloader.downloader import Book, download_book

console = Console()


def run(
    config_path: str = "config.yaml",
    secrets_path: str = "secrets.yaml",
    history_path: str = "download_history.json",
    verbose: bool = False,
    limit: int = 0,
) -> int:
    """Main pipeline: load config → auth → fetch library → filter → download → summary.

    Args:
        config_path: Path to config.yaml.
        secrets_path: Path to secrets.yaml (gitignored).
        history_path: Path to download_history.json.
        verbose: Print extra detail (URLs, paths, API responses).

    Returns:
        Exit code: 0 on success, 1 on failure.
    """
    if verbose:
        console.print("[dim]── config ──────────────────────────────────────[/dim]")
        console.print(f"  config:  {config_path}")
        console.print(f"  secrets: {secrets_path}")
        console.print(f"  history: {history_path}")

    # 1. Load config
    try:
        config = load_config(config_path, secrets_path)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        return 1

    if verbose:
        console.print(f"  format:   {config.format}")
        console.print(f"  output:   {config.output_dir}")
        console.print(f"  extras:   {config.download_extras}")
        console.print(f"  covers:   {config.download_covers}")
        console.print(f"  user:     {config.username}")

    # 2. Authenticate
    if verbose:
        console.print("[dim]── auth ────────────────────────────────────────[/dim]")

    client = LibroFmClient(
        username=config.username,
        password=config.password,
    )

    try:
        client.authenticate()
    except AuthError as exc:
        console.print(f"[red]Authentication failed:[/red] {exc}")
        return 1

    if verbose:
        console.print("  [green]✓[/green] authenticated")

    # 3. Fetch library
    if verbose:
        console.print("[dim]── library ─────────────────────────────────────[/dim]")

    try:
        books = client.fetch_library()
    except Exception as exc:
        console.print(f"[red]Failed to fetch library:[/red] {exc}")
        return 1

    if verbose:
        console.print(f"  {len(books)} book(s) in library")

    # 4. Filter already-downloaded
    if verbose:
        console.print("[dim]── filtering ───────────────────────────────────[/dim]")

    history = DownloadHistory(history_path)
    new_books = [b for b in books if not history.is_downloaded(b.get("isbn", ""))]
    if limit:
        new_books = new_books[:limit]

    if verbose:
        downloaded_count = len(books) - len(new_books)
        console.print(f"  {downloaded_count} already downloaded, {len(new_books)} new")

    if not new_books:
        console.print("[green]All caught up! No new books to download.[/green]")
        return 0

    # 5. Download loop
    console.print(f"\n[bold]{len(new_books)} book(s) to download:[/bold]\n")

    downloaded = 0
    skipped = 0
    failed = 0

    for raw_book in new_books:
        title = raw_book.get("title", "Unknown")
        isbn = raw_book.get("isbn", "?")
        authors = raw_book.get("authors", [])
        # Narrators are nested inside audiobook_info in the API response
        audiobook_info = raw_book.get("audiobook_info", {}) or {}
        narrators = audiobook_info.get("narrators", []) or raw_book.get("narrators", [])
        console.print(f"  ⬇ {title}  [dim]({isbn})[/dim]")

        if verbose:
            console.print(f"     authors:   {', '.join(authors) or '?'}")
            console.print(f"     narrators: {', '.join(narrators) or '?'}")

        book = Book(
            title=title,
            authors=authors,
            narrators=narrators,
            isbn=isbn,
            series=raw_book.get("series", ""),
            series_num=raw_book.get("series_num"),
            cover_url=raw_book.get("cover_url", ""),
            # pdf_extras is a list inside audiobook_info in the API response
            pdf_extras=bool(audiobook_info.get("pdf_extras")) if audiobook_info else False,
            publication_year=raw_book.get("publication_year"),
            publication_month=raw_book.get("publication_month"),
            publication_day=raw_book.get("publication_day"),
        )

        try:
            result = download_book(
                book=book,
                client=client,
                output_base=config.output_dir,
                history=history,
                format_strategy=config.format,
                config=config,
            )
            if result is None:
                console.print(f"    [yellow]⏭ Skipped[/yellow]")
                skipped += 1
            else:
                console.print(f"    [green]✓ Downloaded → {result}[/green]")
                if verbose:
                    console.print(f"    [dim]  {result.stat().st_size:,} bytes[/dim]")
                downloaded += 1
        except Exception as exc:
            console.print(f"    [red]✗ Failed: {exc}[/red]")
            if verbose:
                import traceback
                traceback.print_exc()
            failed += 1

    # 6. Summary
    console.print(f"\n[bold]Summary:[/bold] {downloaded} downloaded, {skipped} skipped, {failed} failed")

    if verbose:
        console.print("[dim]── done ────────────────────────────────────────[/dim]")

    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download audiobooks from Libro.fm")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--secrets", default="secrets.yaml", help="Path to secrets.yaml")
    parser.add_argument("--history", default="download_history.json", help="Path to download history JSON")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output (URLs, sizes, tracebacks)")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Maximum number of books to download (0 = no limit). Useful for testing.",
    )
    args = parser.parse_args()

    sys.exit(run(
        config_path=args.config,
        secrets_path=args.secrets,
        history_path=args.history,
        verbose=args.verbose,
        limit=args.limit,
    ))
