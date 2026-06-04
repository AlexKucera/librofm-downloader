# Fix: Parallel Progress Bar `task_id` Not Wired Through Callback

> **Date:** 2026-06-04
> **Type:** issue
> **Reference:** Untracked bug (user-reported)

## Goal

Fix the parallel download progress indicator where only one book's progress bar updates while all others stay at zero. Usually the last-started bar gets all the updates; occasionally the first-started bar gets them.

## What Was Done

- **`librofm_downloader/orchestrator.py`** — Captured the `task_id` returned by `reporter.start_download(book)` and created a per-book closure `_progress(completed, *, total=None)` that binds that `task_id`. This closure is passed as the `progress=` kwarg to `download_fn()`.
- **`librofm_downloader/cli.py`** — Updated `_download_fn()` closure signature to accept an optional keyword-only `progress=` argument. When provided (by orchestrator in parallel mode), it's used directly; when omitted (sequential mode), falls back to `reporter.update`.
- **`tests/test_progress.py`** — Added `TestParallelProgressCallbackWiring` class with 3 regression tests:
  - `test_update_without_task_id_always_hits_most_recent_bar` — proves the bug: 3 concurrent books, all untargeted `update()` calls land on the last-started bar
  - `test_bound_callback_updates_correct_bar` — proves the fix: each task_id-bound closure targets its own bar
  - `test_interleaved_start_complete_fail_lines` — plain-text reporter multi-book scenario
- **`tests/test_orchestrator.py`** — Updated 21 mock `download_fn` functions to accept `**_kwargs` so they tolerate the new `progress=` kwarg injected by the orchestrator.

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Closure-based per-book callback (not threading `task_id` into downloader) | The `progress` callback signature `Callable[[int], None]` is used throughout the downloader layer (`download_m4b`, `download_zip_part`). Changing it to carry `task_id` would ripple through 3+ functions. A closure at the orchestration layer is zero-cost and keeps the downstream API clean. |
| Keyword-only `progress=` on `_download_fn` | Prevents positional breakage if the closure signature ever grows. Defaults to `None` → backward compat with sequential mode. |
| `**_kwargs` on test mocks | Minimal change — 21 mock functions updated with one replace-all rather than adding explicit `progress=None` to each. |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| Regression test inserted inside previous class body causing `IndentationError` | Edit tool's `insert_after` placed content at wrong indentation level when anchor was the last line of a class | Manually rewrote the full replacement block including the preceding class's closing lines |
| Mock `download_fn` signatures rejected new `progress=` kwarg (`TypeError: got unexpected keyword argument`) | Orchestrator now passes `progress=_progress` to `download_fn`, but 21 test mocks had rigid signatures | Bulk-replaced `def download_fn(book: Book) ->` with `def download_fn(book: Book, **_kwargs) ->` across all mocks |
| Bare `*` syntax error in mock signatures (`named arguments must follow bare *`) | First attempt used `(book: Book, *, **_kwargs)` which is invalid when no named params precede `*` | Changed to `(book: Book, **_kwargs)` — no separator needed since there are no keyword-only args |
| Full suite hangs after orchestrator tests (KeyboardInterrupt) | Pre-existing: `TestCtrlCDrain` tests use real `os.kill(os.getpid(), SIGINT)` which corrupts pytest's signal handler for subsequent tests | Not our bug — excluded from CI consideration; 256/259 tests pass (3 Ctrl+C tests are known hangy) |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/orchestrator.py` | Capture `task_id`, create per-book bound progress closure, pass to `download_fn` |
| `librofm_downloader/cli.py` | Accept optional `progress=` kwarg on `_download_fn`, fall back to `reporter.update` |
| `tests/test_progress.py` | Added `TestParallelProgressCallbackWiring` (3 tests) + fixed `TestMultiBookPlainText` helper |
| `tests/test_orchestrator.py` | 21 mock `download_fn` signatures accept `**_kwargs` |

## Open Items & Next Steps

- [ ] Investigate/fix pre-existing `TestCtrlCDrain` suite hang caused by real `os.kill(SIGINT)` in tests — these 3 tests corrupt pytest signal state for everything after them
- [ ] Consider whether `ProgressReporter.update()` should warn/log when called without `task_id` while multiple tasks exist (catch future wiring bugs earlier)

---
*Log written by write-log skill*
