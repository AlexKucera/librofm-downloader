# CLI Parallel Integration & Ctrl+C Graceful Drain — Issue #17

> **Date:** 2026-06-03
> **Type:** issue
> **Reference:** [Issue #17](https://github.com/AlexKucera/librofm-downloader/issues/17)

## Goal

Wire the parallel orchestrator into `cli.py:run()` as the end-to-end integration slice. Implement graceful Ctrl+C drain handling (first Ctrl+C drains in-flight downloads, second Ctrl+C force-quits). Write 10-12 integration tests covering parallel-specific behaviors.

## What Was Done

### Implementation (`orchestrator.py`)

- **Graceful Ctrl+C drain** in `download_all_books()`:
  - Wrapped `as_completed()` loop in `try/except KeyboardInterrupt`
  - On first Ctrl+C: prints `[yellow]Aborting...[/yellow] (draining in-flight downloads)`, calls `executor.shutdown(wait=True)` to drain, then re-raises for cli.py exit code 130
  - On second Ctrl+C during drain: prints `[red]Force quit — partial downloads may be incomplete.[/red]`, calls `executor.shutdown(wait=False, cancel_futures=True)`, re-raises immediately
  - Moved `Console` import to module level (refactored from inline imports)
  - Removed dead `_draining` tracking variable

### Tests (`test_cli.py`) — 11 new integration tests

| Class | Tests | What's verified |
|-------|-------|-----------------|
| `TestParallelWorkers1Parity` | 2 | workers=1 calls all books in order; exit code 0 on success |
| `TestParallelCtrlCDrain` | 2 | Ctrl+C → exit code 130; "Aborting..." message shown |
| `TestParallelSummaryOrdering` | 2 | 5-book mixed result ordering (succeed/fail/skip); summary kwargs have correct counts |
| `TestParallelConcurrency` | 2 | workers=3 faster than sequential (wall clock); failure isolation |
| `TestParallelVerboseMode` | 2 | verbose + workers=3 prints per-book details; verbose with failure doesn't crash |
| `TestParallelPartialFileSafety` | 1 | Ctrl+C leaves partial files for resume |

### Tests (`test_orchestrator.py`) — 2 new unit tests

| Class | Tests | What's verified |
|-------|-------|-----------------|
| `TestCtrlCDrain` | 2 | Drain completes in-flight books on interrupt; double-Ctrl+C exits immediately (< 0.3s not 10s) |

**Total: 13 new tests, 231 total (was 218)**

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Catch+drain+re-raise pattern (not return partial result) | Keeps orchestrator decoupled from exit codes. cli.py's outer handler already handles exit code 130. Re-raising lets both layers do their job. |
| `executor.shutdown(wait=True)` for drain | Python's ThreadPoolExecutor.shutdown(wait=True) waits for running futures to complete and cancels pending ones. Exactly the "drain" semantics we need. |
| Double-Ctrl+C uses nested try/except | Inner except handles second interrupt during shutdown(wait=True). Clean separation of single vs double interrupt behavior. |
| `Console()` at module level, not reporter.console | Reporter may not always have a console attribute (FakeReporter doesn't). Direct Console() import is simpler and more reliable. |
| SIGINT from thread for double-Ctrl+C test | `os.kill(os.getpid(), signal.SIGINT)` from a daemon thread is the only reliable way to test double-Ctrl+C in pytest. The 0.2s delay gives time for first-interrupt handler to enter drain phase. |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| Single Ctrl+C fell through silently (exit code 0, not 130) | After `shutdown(wait=True)` in inner try/except, no `raise` for the non-double-interrupt path | Added `raise` after inner try/except block to re-raise single KeyboardInterrupt |
| `FakeReporter` has no `.console` attribute | Orchestrator tried `reporter.console.print()` but FakeReporter is a minimal stub | Changed to direct `Console().print()` with module-level import |
| Barrier-based test deadlocked on Ctrl+C | Barrier required all 3 threads to participate; interrupted thread raised before reaching it; other threads blocked forever | Replaced barrier with `time.sleep(0.05)` for completable work + `time.sleep(10)` for slow work that gets interrupted |
| `signal` NameError in double-Ctrl+C test | `import signal` was added after code that referenced it | Moved `import signal` to top of function with other imports |
| Edit tool `replace` not persisting | Stale LINE:HASH anchors between read and edit operations | Used `set_line` or re-read file for fresh anchors |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/orchestrator.py` | Added graceful Ctrl+C drain: try/except around as_completed loop, double-Ctrl+C fast exit, Console import at module level (+10 -5 lines net) |
| `tests/test_cli.py` | Added 11 integration tests across 6 test classes: workers=1 parity, Ctrl+C drain, summary ordering, concurrency proof, verbose mode, partial file safety (~340 lines) |
| `tests/test_orchestrator.py` | Added 2 orchestrator-level Ctrl+C drain tests: partial completion during drain, double-Ctrl+C fast exit (~90 lines) |

## Open Items & Next Steps

- None — issue complete, all acceptance criteria met

---
*Log written by write-log skill*
