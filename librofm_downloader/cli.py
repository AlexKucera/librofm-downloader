"""CLI entry point — wire config → auth → fetch library → download → history."""

import sys
from pathlib import Path

from rich.console import Console

from librofm_downloader.config import load_config, ConfigError
from librofm_downloader.client import LibroFmClient, AuthError
from librofm_downloader.history import DownloadHistory
from librofm_downloader.downloader import Book, download_book
from librofm_downloader.orchestrator import download_all_books
from librofm_downloader.progress import DownloadReporter

console = Console()


def run(
    config_path: str = "config.yaml",
    secrets_path: str = "secrets.yaml",
    history_path: str = "download_history.json",
    verbose: bool = False,
    limit: int = 0,
    workers: int = 0,
) -> int:
    """Main pipeline: load config → auth → fetch library → filter → download → summary.

    Args:
        config_path: Path to config.yaml.
        secrets_path: Path to secrets.yaml (gitignored).
        history_path: Path to download_history.json.
        verbose: Print extra detail (URLs, paths, API responses).
        limit: Maximum number of books to download (0 = no limit).
        workers: Parallel download worker count (0 = use config value).

    Returns:
        Exit code: 0 on success, 1 on fatal error, 130 on Ctrl+C interrupt.
        """

    try:
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

        # Resolve workers: CLI flag (>0?) → config.workers → default 3
        resolved_workers = workers if workers > 0 else config.workers
        if resolved_workers < 1:
            resolved_workers = 3
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

        # 5. Download loop with TTY-aware reporting
        reporter = DownloadReporter()
        console.print(f"\n[bold]{len(new_books)} book(s) to download:[/bold]\n")

        # --- Download loop (parallel via orchestrator — Issue #16) ---

        def _make_download_fn():
            """Closure capturing client, config, history, reporter for each book."""
            def _download_fn(book: Book):
                if verbose:
                    console.print(f"  ⬇ {book.title}  [dim]({book.isbn})[/dim]")
                    console.print(f"     authors:   {', '.join(book.authors) or '?'}")
                    console.print(f"     narrators: {', '.join(book.narrators) or '?'}")
                return download_book(
                    book=book,
                    client=client,
                    output_base=config.output_dir,
                    history=history,
                    format_strategy=config.format,
                    config=config,
                    progress=reporter.update,
                )
            return _download_fn

        result = download_all_books(
            new_books,
            workers=resolved_workers,
            download_fn=_make_download_fn(),
            reporter=reporter,
        )

        downloaded = result.downloaded_count
        skipped = result.skipped_count
        failed = result.failed_count
        failed_books = result.failed_books
        skipped_books = result.skipped_books

        reporter.summary(
            downloaded=downloaded,
            skipped=skipped,
            failed=failed,
            failed_books=failed_books,
            skipped_books=skipped_books,
        )

        if verbose:
            console.print("[dim]── done ────────────────────────────────────────[/dim]")

        return 0

    except KeyboardInterrupt:
        console.print("\n[yellow]Download interrupted by user (Ctrl+C).[/yellow]")
        return 130


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
    parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=0,
        metavar="N",
        help="Parallel download workers (0 = use config value). Default: 3.",
    )
    args = parser.parse_args()

    sys.exit(run(
        config_path=args.config,
        secrets_path=args.secrets,
        history_path=args.history,
        verbose=args.verbose,
        limit=args.limit,
        workers=args.workers,
    ))
