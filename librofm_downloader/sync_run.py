"""Sync run pipeline — extracted from cli.run().

12 sequential stages: resolve paths → load config → authenticate → fetch library
→ intake (Book) → filter/limit/select → resolve plans → download all → write
history → summary → return result.

This is the domain pipeline.  cli.py becomes a thin argparse→exit adapter that
calls sync_run() and translates SyncRunResult → exit code.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

from librofm_downloader.book import Book
from librofm_downloader.config import ConfigError, _resolve_config_file, load_config
from librofm_downloader.downloader import download_book
from librofm_downloader.history import DownloadHistory, _write_history
from librofm_downloader.orchestrator import OrchestratorResult, download_all_books
from librofm_downloader.path import resolve_output_plan
from librofm_downloader.progress import DownloadReporter
from librofm_downloader.session import AuthError, LibroFmSession

console = Console()


def _print_verbose_config(config, history_path: str, secrets_path: str | None) -> None:
    """Print resolved config details when verbose mode is on."""
    console.print("[dim]\u2500\u2500 config \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500[/dim]")
    cfg_display = config._config_path if config._config_path else "(built-in defaults)"
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
    console.print(f"  chapters: {config.rename_chapters}")
    console.print(f"  user:     {config.username}")


def _resolve_history_path(history_path: str | None) -> str:
    """Resolve history file path: explicit \u2192 XDG search \u2192 XDG default."""
    if history_path is not None:
        return history_path
    resolved = _resolve_config_file("download_history.json")
    if resolved is not None:
        return str(resolved)
    from os import environ
    home = Path(environ.get("HOME", "~")).expanduser()
    xdg_dir = home / ".config" / "librofm-downloader"
    xdg_dir.mkdir(parents=True, exist_ok=True)
    return str(xdg_dir / "download_history.json")

@dataclass(frozen=True)
class SyncRunResult:
    """Structured result from a full sync run.

    Attributes:
        downloaded_count: Books successfully downloaded.
        skipped_count: Books skipped (download_fn returned None).
        failed_count: Books that raised an exception.
        failed_books: List of (book, reason_string) tuples in original order.
        skipped_books: List of Book objects that were skipped, in original order.
        interrupted: True if the run was cancelled by Ctrl+C.
        fatal_error: Non-None if the run stopped before downloads (auth, config, fetch).
    """

    downloaded_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    failed_books: list[tuple[Book, str]] = field(default_factory=list)
    skipped_books: list[Book] = field(default_factory=list)
    interrupted: bool = False
    fatal_error: str | None = None


def sync_run(
    config_path: str | None = None,
    secrets_path: str | None = None,
    history_path: str | None = None,
    verbose: bool = False,
    limit: int = 0,
    workers: int = 0,
    rename_chapters: bool = False,
    *,
    select_mode: bool = False,
    session: LibroFmSession | None = None,
    history: DownloadHistory | None = None,
    reporter: DownloadReporter | None = None,
    download_all_fn: Callable | None = None,
) -> SyncRunResult:
    """Main pipeline: load config → auth → fetch library → filter → download → summary.

    Args:
        config_path: Path to config.yaml.
        secrets_path: Path to secrets.yaml (gitignored).
        history_path: Path to download_history.json.
        verbose: Print extra detail (URLs, paths, API responses).
        limit: Maximum number of books to download (0 = no limit).
        workers: Parallel download worker count (0 = use config value).
        select_mode: Interactive book selection (ADR #6, not yet implemented).

    Returns:
        SyncRunResult with counts and per-book details.
    """

    try:
        # 0. Resolve history path (XDG → CWD, default to XDG location)
        history_path = _resolve_history_path(history_path)

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
            return SyncRunResult(fatal_error=f"Config error: {exc}")

        if verbose:
            _print_verbose_config(config, history_path, secrets_path)

        # Resolve workers: CLI flag (>0?) → config.workers → default 3
        resolved_workers = workers if workers > 0 else config.workers
        if resolved_workers < 1:
            resolved_workers = 3

        # Resolve rename_chapters: CLI flag (True?) → config.rename_chapters
        resolved_rename_chapters = rename_chapters or config.rename_chapters

        # 2. Authenticate (or use injected session)
        if session is not None:
            client = session
        else:
            if verbose:
                console.print("[dim]── auth ────────────────────────────────────────[/dim]")

            client = LibroFmSession(
                username=config.username,
                password=config.password,
            )

            try:
                client.authenticate()
            except AuthError as exc:
                console.print(f"[red]Authentication failed:[/red] {exc}")
                return SyncRunResult(fatal_error=f"Authentication failed: {exc}")

            if verbose:
                console.print("  [green]✓[/green] authenticated")

        # 3. Fetch library
        if verbose:
            console.print("[dim]── library ─────────────────────────────────────[/dim]")

        try:
            books = client.fetch_library()
        except Exception as exc:
            console.print(f"[red]Failed to fetch library:[/red] {exc}")
            return SyncRunResult(fatal_error=f"Failed to fetch library: {exc}")

        if verbose:
            console.print(f"  {len(books)} book(s) in library")

        # 4. Filter already-downloaded
        if verbose:
            console.print("[dim]── filtering ───────────────────────────────────[/dim]")

        if history is None:
            history = DownloadHistory(history_path)
        new_books = [b for b in books if not history.is_downloaded(b.get("isbn", ""))]
        if limit:
            new_books = new_books[:limit]

        if verbose:
            downloaded_count = len(books) - len(new_books)
            console.print(f"  {downloaded_count} already downloaded, {len(new_books)} new")

        if not new_books:
            console.print("[green]All caught up! No new books to download.[/green]")
            return SyncRunResult()

        # 5. Select mode branch point (ADR #6 — stub)
        if select_mode:
            console.print("[red]--select is not yet implemented.[/red]")
            return SyncRunResult()

        # 6. Download loop with TTY-aware reporting
        if reporter is None:
            reporter = DownloadReporter()
        cancel_event = threading.Event()
        # cancel_event passed explicitly via closure to download_book() (Issue #39)
        console.print(f"\n[bold]{len(new_books)} book(s) to download:[/bold]\n")

        # --- Download loop (parallel via orchestrator — Issue #16) ---

        def _make_download_fn(
            _config, _client, _history, _reporter, _cancel_event, _rename_chapters,
        ):
            def _download_fn(
                book: Book, *, progress: Callable[[int], None] | None = None
            ):
                # Build output plan for this book (paths + format strategy)
                plan = resolve_output_plan(
                    book,
                    _config.output_dir,
                    config=_config,
                    format_strategy=_config.format,
                )
                result = download_book(book, _client, plan, _reporter, progress=progress, rename_chapters=_rename_chapters, cancel_event=_cancel_event)

                # Write history as caller (no longer inside download_book)
                if result.status == "downloaded":
                    _write_history(
                        _history, book, result.format or "m4b", str(result.path)
                    )

                # Return Path | None for backward compat with orchestrator
                if result.status == "downloaded":
                    return result.path
                return None  # skipped or failed

            return _download_fn

        _download_all = download_all_fn or download_all_books
        result = _download_all(
            new_books,
            workers=resolved_workers,
            download_fn=_make_download_fn(config, client, history, reporter, cancel_event, resolved_rename_chapters),
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
            return SyncRunResult(
                downloaded_count=downloaded,
                skipped_count=skipped,
                failed_count=failed,
                failed_books=failed_books,
                skipped_books=skipped_books,
                interrupted=True,
            )

        if verbose:
            console.print("[dim]── done ────────────────────────────────────────[/dim]")

        return SyncRunResult(
            downloaded_count=downloaded,
            skipped_count=skipped,
            failed_count=failed,
            failed_books=failed_books,
            skipped_books=skipped_books,
            interrupted=False,
        )

    except KeyboardInterrupt:
        console.print("\n[yellow]Download interrupted by user (Ctrl+C).[/yellow]")
        return SyncRunResult(interrupted=True)
