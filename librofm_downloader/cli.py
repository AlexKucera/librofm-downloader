"""CLI entry point — parse args → call sync_run() → translate exit code."""

import os
import sys

from rich.console import Console

from librofm_downloader.sync_run import sync_run

console = Console()


def run(
    config_path: str | None = None,
    secrets_path: str | None = None,
    history_path: str | None = None,
    verbose: bool = False,
    limit: int = 0,
    workers: int = 0,
    select_mode: bool = False,
) -> int:
    """Thin adapter: call sync_run() and translate SyncRunResult → exit code (0/1/130)."""
    result = sync_run(
        config_path=config_path,
        secrets_path=secrets_path,
        history_path=history_path,
        verbose=verbose,
        limit=limit,
        workers=workers,
        select_mode=select_mode,
    )
    if result.interrupted:
        return 130
    if result.fatal_error:
        return 1
    return 0


def main() -> None:
    """CLI entry point — parse args and run the download pipeline."""
    import argparse
    parser = argparse.ArgumentParser(description="Download audiobooks from Libro.fm")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--secrets", default=None, help="Path to secrets.yaml")
    parser.add_argument("--history", default=None, help="Path to download history JSON")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--limit", type=int, default=0, metavar="N", help="Max books to download (0=no limit)")
    parser.add_argument("-w", "--workers", type=int, default=0, metavar="N", help="Parallel workers (0=config)")
    parser.add_argument("--select", action="store_true", default=False, help="Interactive selection [not implemented]")
    args = parser.parse_args()
    exit_code = run(
        config_path=args.config, secrets_path=args.secrets, history_path=args.history,
        verbose=args.verbose, limit=args.limit, workers=args.workers, select_mode=args.select,
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
