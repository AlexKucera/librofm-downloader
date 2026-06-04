"""CLI entry point — wire config → auth → fetch library → download → history."""

import os
import sys
import threading
from pathlib import Path

from rich.console import Console

from librofm_downloader.config import load_config, ConfigError, _resolve_config_file
from librofm_downloader.client import LibroFmClient, AuthError
from librofm_downloader.history import DownloadHistory
from librofm_downloader.book import Book
from librofm_downloader.downloader import download_book
from librofm_downloader.orchestrator import download_all_books
from librofm_downloader.progress import DownloadReporter

console = Console()


def run(
    config_path: str | None = None,
    secrets_path: str | None = None,
    history_path: str | None = None,
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
        # 0. Resolve history path (XDG → CWD, default to XDG location)
        if history_path is None:
            resolved = _resolve_config_file("download_history.json")
            if resolved is not None:
                history_path = str(resolved)
            else:
                from os import environ
                home = Path(environ.get("HOME", "~")).expanduser()
                xdg_dir = home / ".config" / "librofm-downloader"
                xdg_dir.mkdir(parents=True, exist_ok=True)
                history_path = str(xdg_dir / "download_history.json")

        # 1. Load config
        try:
            config = load_config(config_path, secrets_path)
            if config._config_path is None:
                searched = [
                    "~/.config/librofm-downloader/config.yaml",
                    "./config.yaml",
                ]
                console.print(
                    f"[yellow]config.yaml not found in {' → '.join(searched)}. "
                    f"Using built-in defaults.[/yellow]"
                )
        except ConfigError as exc:
            console.print(f"[red]Config error:[/red] {exc}")
            return 1

        if verbose:
            console.print("[dim]── config ──────────────────────────────────────[/dim]")
            cfg_display = config._config_path if config._config_path else "(built-in defaults)"
            # Determine resolved secrets path
            secrets_display = secrets_path
            if secrets_path is None:
                resolved_secrets = _resolve_config_file("secrets.yaml")
                secrets_display = resolved_secrets or "(not found)"
            console.print(f"  config:   {cfg_display}")
            console.print(f"  secrets:  {secrets_display}")
            console.print(f"  history:  {history_path}")
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
        cancel_event = threading.Event()
        console.print(f"\n[bold]{len(new_books)} book(s) to download:[/bold]\n")

        # --- Download loop (parallel via orchestrator — Issue #16) ---

        def _make_download_fn():
            """Closure capturing client, config, history, reporter for each book."""
            def _download_fn(book: Book, *, progress: "Callable[[int], None] | None" = None):
                # Allow orchestrator to inject a per-book bound progress callback.
                # Falls back to the shared reporter.update when not in parallel mode.
                if progress is None:
                    progress = reporter.update
                return download_book(
                    book=book,
                    client=client,
                    output_base=config.output_dir,
                    history=history,
                    format_strategy=config.format,
                    config=config,
                    progress=progress,
                    cancel_event=cancel_event,
                )
            return _download_fn

        result = download_all_books(
            new_books,
            workers=resolved_workers,
            download_fn=_make_download_fn(),
            reporter=reporter,
            cancel_event=cancel_event,
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

        if result.interrupted:
            return 130

        if verbose:
            console.print("[dim]── done ────────────────────────────────────────[/dim]")

        return 0

    except KeyboardInterrupt:
        console.print("\n[yellow]Download interrupted by user (Ctrl+C).[/yellow]")
        return 130


def main() -> None:
    """CLI entry point — parse args and run the download pipeline."""
    import argparse

    parser = argparse.ArgumentParser(description="Download audiobooks from Libro.fm")
    parser.add_argument("--config", default=None, help="Path to config.yaml (default: search XDG then CWD)")
    parser.add_argument("--secrets", default=None, help="Path to secrets.yaml (default: search XDG then CWD)")
    parser.add_argument("--history", default=None, help="Path to download history JSON (default: search XDG then CWD)")
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

    exit_code = run(
        config_path=args.config,
        secrets_path=args.secrets,
        history_path=args.history,
        verbose=args.verbose,
        limit=args.limit,
        workers=args.workers,
    )
    if exit_code == 130:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        finally:
            os._exit(130)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()