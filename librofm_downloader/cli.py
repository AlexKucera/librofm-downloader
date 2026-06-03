"""CLI entry point — wire config → auth → fetch library → filter → print."""

import sys

from rich.console import Console

from librofm_downloader.config import load_config, ConfigError
from librofm_downloader.client import LibroFmClient, AuthError
from librofm_downloader.history import DownloadHistory

console = Console()


def run(
    config_path: str = "config.yaml",
    secrets_path: str = "secrets.yaml",
    history_path: str = "download_history.json",
) -> int:
    """Main pipeline: load config → auth → fetch library → filter → print.

    Returns:
        Exit code: 0 on success, 1 on failure.
    """
    try:
        config = load_config(config_path, secrets_path)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        return 1

    client = LibroFmClient(
        username=config.username,
        password=config.password,
    )

    try:
        client.authenticate()
    except AuthError as exc:
        console.print(f"[red]Authentication failed:[/red] {exc}")
        return 1

    try:
        books = client.fetch_library()
    except Exception as exc:
        console.print(f"[red]Failed to fetch library:[/red] {exc}")
        return 1

    history = DownloadHistory(history_path)
    new_books = [b for b in books if not history.is_downloaded(b.get("isbn", ""))]

    if not new_books:
        console.print("[green]All caught up! No new books to download.[/green]")
        return 0

    console.print(f"\n[bold]{len(new_books)} book(s) to download:[/bold]\n")
    for book in new_books:
        title = book.get("title", "Unknown")
        isbn = book.get("isbn", "?")
        console.print(f"  • {title}  [dim]({isbn})[/dim]")

    return 0
