# Fix: `-v` / `--verbose` flag not wired through CLI entry point

> **Date:** 2026-06-04
> **Type:** issue
> **Reference:** User-reported bug — `-v` flag does nothing

## Goal

Fix the `-v` / `--verbose` CLI flag which was accepted on the command line but never actually parsed or passed to `run()`, making verbose mode completely non-functional for installed console scripts.

## What Was Done

- Extracted `argparse` block out of `if __name__ == "__main__":` guard in `librofm_downloader/cli.py` into a proper `main()` function
- Updated `pyproject.toml` entry point from `librofm_downloader.cli:run` → `librofm_downloader.cli:main`
- Verified all 247 tests pass (36 CLI tests + 211 others)
- Reinstalled package (`pip install -e .`) and confirmed `librofm-downloader --help` shows `-v, --verbose`

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Keep `run()` unchanged, add `main()` alongside it | `run()` is called directly with keyword args by 36 tests. Renaming it would break all tests for no benefit. A thin `main()` wrapper is the cleanest fix. |
| `main()` calls `sys.exit(run(...))` | Preserves the exact same exit-code behavior as the old `__main__` block. |
| `if __name__ == "__main__": main()` guard kept | Allows `python -m librofm_downloader.cli` to still work for development. |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| `-v` flag does nothing | `pyproject.toml` pointed console script entry at `run()` directly. `run()` expects parsed keyword args, not `sys.argv`. The argparse code was inside `if __name__ == "__main__":` which only executes when running the file directly via Python, never for installed console scripts. | Extracted argparse into `main()` and pointed entry point at `main()`. |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/cli.py` | Extracted argparse from `__main__` guard into `main()` function; added `main()` as proper CLI entry point |
| `pyproject.toml` | Changed `[project.scripts]` entry point from `librofm_downloader.cli:run` to `librofm_downloader.cli:main` |

## Open Items & Next Steps

None

---

*Log written by write-log skill*
