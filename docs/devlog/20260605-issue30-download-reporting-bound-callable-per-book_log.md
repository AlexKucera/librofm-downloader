# Issue #30 — Download Reporting: Bound Callable Per Book

> **Date:** 2026-06-05
> **Type:** issue
> **Reference:** #30

## Goal

Refactor `start_download(book)` to return a bound callable that already targets the correct progress bar, making task identity fully internal to `progress.py`. Eliminate the per-book closure pattern from the orchestrator.

## What Was Done

- **`librofm_downloader/progress.py`** — `start_download()` now returns `Callable[[int], None]` (bound closure) instead of `int task_id`. Public `update()` no longer accepts `task_id` param. The bound callable captures `task_id` internally and calls `_progress.update(task_id, ...)` directly.
- **`librofm_downloader/orchestrator.py`** — Removed closure pattern from `_download_one`. Now calls `progress_cb = reporter.start_download(book)` and passes `progress_cb` as `progress=` kwarg to `download_fn`.
- **`librofm_downloader/downloader.py`** — `download_book()` accepts optional `progress=` kwarg; uses it when provided, falls back to `reporter.update` for backward compatibility.
- **`librofm_downloader/cli.py`** — `_download_fn` now passes `progress=progress` through to `download_book()`.
- **`tests/test_progress.py`** — 9 existing tests refactored for new return type (int → callable) + 5 new tests in `TestBoundCallableFromStartDownload`.
- **`tests/test_orchestrator.py`** — 1 new test: `TestOrchestratorUsesBoundCallback`.
- **`tests/test_downloader.py`** — 1 new test: `test_uses_provided_progress_callback_over_reporter_update`.

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Bound closure over callback-with-book-arg | Simpler API; prevents cross-bar contamination by construction — caller can't possibly target wrong task |
| Kept public `update()` without `task_id` param | Fallback for direct callers not going through orchestrator; targets most-recent task |
| Bound callable calls `_progress.update()` directly (not public `update()`) | Keeps fast path clean; avoids any guard logic in the hot loop |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| Downloader progress-wiring test showed "skipped" status | Mock URLs didn't match `/packaged_m4b` path or CDN host patterns used by real download path selection | Used proper mock URLs matching real route conditions |
| `MagicMock(spec=DownloadReporter)` raised error | `DownloadReporter` is a factory function, not a class — `spec=` expects a class | Switched to bare `MagicMock()` |
| 9 existing tests broke after return-type change | `start_download()` changed from returning `int` → `Callable`; tests asserted on `isinstance(result, int)` or passed result to `update(task_id=)` | Refactored all 9 to call returned callable directly |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/progress.py` | `start_download()` returns bound `Callable[[int], None]`; public `update()` drops `task_id` param |
| `librofm_downloader/orchestrator.py` | Removed per-book closure; uses bound callable from `start_download()` |
| `librofm_downloader/downloader.py` | `download_book()` accepts optional `progress=` kwarg with fallback to reporter |
| `librofm_downloader/cli.py` | Wires `progress=` kwarg through `_download_fn` → `download_book()` |
| `tests/test_progress.py` | 9 refactored + 5 new tests for bound callable behavior |
| `tests/test_orchestrator.py` | 1 new test: orchestrator uses bound callback correctly |
| `tests/test_downloader.py` | 1 new test: provided progress callback takes priority over reporter |

## Open Items & Next Steps

- None — issue fully complete, 6/6 AC met

---

*Log written by write-log skill*
