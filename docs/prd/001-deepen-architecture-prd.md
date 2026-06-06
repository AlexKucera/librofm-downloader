# PRD 001: Deepen Architecture — Module Depth & Domain Alignment

> **Status:** Draft (grilling complete, ready for issue breakdown)
> **Date:** 2026-06-04
> **Parent ADRs:** [ADR 0001](../adr/0001-parallel-downloads.md), [ADR 0006](../adr/0006-select-mode-interactive-book-selection.md)

## Problem Statement

The librofm-downloader codebase has grown through 10+ issue-driven slices (Issues #2–#23). Each slice added correct code in the right place *at the time*, but the accumulated result is **shallow modules with leaky interfaces**:

- **`cli.run()`** (246 lines) does the entire Sync Run pipeline — config resolution, auth, library fetch, history filtering, worker resolution, download orchestration, summary, and exit-code policy. Its interface is small (7 parameters) but its test surface is enormous: ~29 tests patch 6+ internal modules to exercise it.
- **`download_book()`** (9 parameters) exposes implementation details (transport override, cancel_event threading, format strategy branching, config for extras toggles) that every caller must understand.
- **`LibroFmClient`** repeats auth-header assembly, `httpx.Client` construction, authenticated-state checks, and test-only `transport=` parameters across 4 endpoint methods.
- **Book intake** (`_raw_to_book()`) lives in the orchestrator while the `Book` dataclass lives in `downloader.py`, splitting API-shape normalization knowledge across two files.
- **Output path logic** is scattered across 4 functions in `downloader.py` plus the `Book` dataclass, and has already produced 2 real bugs (path doubling, cover placement).
- **Download reporting** leaks task identity to callers; the parallel progress-bar bug (Issue #23 fix) was caused by callers needing to bind `task_id` through a closure.
- **DownloadHistory writing** happens inside `download_book()` at two separate points, making it impossible for callers to control persistence policy without modifying download logic.

These shallow modules force tests to patch internals rather than exercising interfaces. They cause bugs when implementation details change. And they make every new feature touch more files than it should.

## Solution

A coordinated deepening of 6 module boundaries, executed in dependency order. Each candidate introduces a **deep module**: a small interface behind which a lot of behaviour concentrates. The vocabulary comes from the existing domain glossary (`CONTEXT.md`) and respects both ADRs.

### Execution Order

```
#2  Book intake          ← foundation: everything works with Book objects
#3  Output Structure     ← needs Book; consumed by download & session
#6  Libro.fm session     ← independent of #3, can be done in parallel
#4  Download Attempt     ← needs OutputPlan + Session + named results
#5  Download reporting   ← needs Download Attempt shape
#1  Sync Run             ← orchestrates all above
```

## User Stories

1. As a **maintainer**, I want `Book` intake and API-shape normalization to live in one place, so that Libro.fm API changes (new fields, nested structure shifts) require editing exactly one file.
2. As a **maintainer**, I want output path planning to return a coherent plan object, so that adding a new output type (e.g., chapter images, metadata sidecars) doesn't require touching 4+ functions.
3. As a **test author**, I want to assert download outcomes through a `DownloadResult` dataclass, so that I don't need to coordinate mocks for `client`, `history`, `progress`, `cancel_event`, and `config` simultaneously.
4. As a **test author**, I want the Librofm session to accept transport injection at construction time, so that I can create one mock session and pass it to any function that needs Librofm API access — instead of threading `transport=` through 4 method signatures per test.
5. As a **test author**, I want the Sync Run pipeline to be callable as a function with clear parameters, so that I can test auth failure, empty library, mixed download results, and Ctrl+C handling without patching 6 internal imports inside `cli.py`.
6. As a **developer**, I want `download_book()` to take 4 domain-aligned parameters instead of 9, so that adding a new download concern (e.g., checksum verification) adds depth to an existing module rather than widening the interface again.
7. As a **developer**, I want progress reporting to give me a bound callback per book, so that parallel download wiring cannot accidentally update the wrong progress bar.
8. As a **future developer** implementing Select Mode (ADR #6), I want the Sync Run pipeline to have a clear filter stage that I can replace with interactive selection — without restructuring the entire pipeline.

## Implementation Decisions

### Candidate #2: Book Intake Module

- **New file:** `librofm_downloader/book.py`
- **Contains:** `Book` dataclass (moved from `downloader.py`), `from_library_row(raw: dict) -> Book` intake function
- **ISBN normalization:** `from_library_row()` coerces ISBN to `str()` (API sometimes returns `int`)
- **Narrator resolution:** handles nested `audiobook_info.narrators` fallback to top-level `narrators`
- **PDF extras detection:** handles nested `audiobook_info.pdf_extras` with `bool()` coercion
- **Default values:** title defaults to `"Unknown"`, isbn defaults to `"?"` — preserved from current `_raw_to_book()`
- **Path helpers move to separate `path.py`** (not into `book.py`): `sanitize()`, `resolve_path()`, `needs_subdirectory()`, token registry, `_token_value()`

### Candidate #3: Output Structure Planning

- **New file:** `librofm_downloader/path.py`
- **Contains:** path helpers (from `downloader.py`) + new `OutputPlan` frozen dataclass
- **`OutputPlan` carries:**
  - Audio destination path (`.m4b` or MP3 directory)
  - Partial-file path (`.m4b.partial` or `.zip.partial`)
  - Cover art destination path (or `None` if disabled/absent)
  - PDF extra destination path (or `None` if disabled/absent)
  - Format strategy (from Config)
  - Extras flags: `download_covers`, `download_extras` (from Config)
- **Resolution function:** `resolve_output_plan(book: Book, output_base: Path | str, config: Config) -> OutputPlan`
- **Replaces:** `_resolve_output_dir()` + scattered path computation in `download_book()`, `_download_cover()`, `_download_pdf()`
- **Download functions consume plan fields** instead of computing paths internally

### Candidate #6: Libro.fm Session

- **Rename:** `LibroFmClient` → `LibroFmSession`
- **New file:** `librofm_downloader/session.py` (renamed from `client.py`; keep alias for transition)
- **Constructor injection:** `LibroFmSession(base_url, username, password, *, transport=None)`
- **All 4 endpoint methods drop their `transport` parameter**
- **Internal:** single `httpx.Client` constructed once with the injected transport (or real HTTP)
- **Auth headers assembled once** and stored on the instance (not recomputed per call)
- **API semaphore** (`threading.Semaphore(3)`) stays on the instance
- **Backward compatibility:** `librofm_downloader/client.py` re-exports from `session.py` as deprecated aliases

### Candidate #4: Download Attempt

- **Stays in:** `librofm_downloader/downloader.py` (but slimmer — only download logic)
- **New interface:** `download_book(book: Book, session: LibroFmSession, plan: OutputPlan, reporter: DownloadReporter) -> DownloadResult`
- **New result type:** `DownloadResult` frozen dataclass with fields:
  - `status`: `Literal["downloaded", "skipped", "failed"]`
  - `path`: `Path | None` (output path on success, None on skip/fail)
  - `format`: `str | None` (actual format used: `"m4b"` or `"mp3"`)
  - `error`: `str | None` (error message on failure)
- **History writing moves to caller:** `download_book()` no longer takes `history` or calls `_write_history()`. The orchestrator/Sync Run inspects `DownloadResult` and writes history for successful downloads.
- **Format strategy and extras flags come from `OutputPlan`** (not from raw Config)
- **Progress callback comes from reporter** (see #5)
- **Cancel event handled internally or via reporter contract** (TBD during implementation)

### Candidate #5: Download Reporting

- **Stays in:** `librofm_downloader/progress.py`
- **Change:** `start_download(book)` returns a **bound callable** `Callable[[int], None]` (for TTY/ProgressReporter) or `None` (for PlainTextReporter)
- **Task identity is fully internal** to `ProgressReporter`; callers never see `task_id`
- **`complete(book)` and `fail(book, reason)` stay on the reporter** (they look up task id internally via `id(book)`)
- **Orchestrator no longer creates closures** — it just passes the bound callback to `download_fn`
- **Fallback behavior removed:** `update()` without `task_id` raises or is a no-op; the bound callback always targets the right bar

### Candidate #1: Sync Run Pipeline

- **New file:** `librofm_downloader/sync_run.py`
- **New function:** `sync_run(config, secrets_path, history_path, *, verbose, limit, workers, select_mode) -> SyncRunResult`
- **Pipeline stages (sequential, early-return on fatal error):**
  1. Resolve paths (XDG/CWD/history)
  2. Load config
  3. Authenticate → `LibroFmSession`
  4. Fetch library → `list[dict]`
  5. Intake: convert to `list[Book]` via `from_library_row()`
  6. Filter: remove downloaded books (unless select_mode)
  7. Select: if `select_mode`, open TUI (ADR #6); else apply limit
  8. Resolve `OutputPlan` for each book
  9. Download all (via orchestrator or direct call)
  10. Write history for successful downloads
  11. Report summary
  12. Return `SyncRunResult`
- **`cli.py` becomes thin adapter:** parse args → call `sync_run()` → translate exit code → `sys.exit()`
- **Verbose output:** printed by `sync_run()` itself (it owns the pipeline, it owns the output)
- **`SyncRunResult`** absorbs/replaces `OrchestratorResult`:
  - `downloaded_count`, `skipped_count`, `failed_count`
  - `failed_books: list[tuple[Book, str]]`
  - `skipped_books: list[Book]`
  - `interrupted: bool`

### Cross-Cutting: Named Result Types

- **`DownloadResult`** — per-book outcome from `download_book()`
- **`SyncRunResult`** — pipeline outcome (replaces `OrchestratorResult`)
- **`OrchestratorResult`** — deprecated; `download_all_books()` returns `SyncRunResult` directly
- All frozen dataclasses for immutability

### Cross-Cutting: Import Migration

| Old import | New import |
|------------|-----------|
| `from librofm_downloader.downloader import Book` | `from librofm_downloader.book import Book` |
| `from librofm_downloader.downloader import sanitize, resolve_path` | `from librofm_downloader.path import sanitize, resolve_path` |
| `from librofm_downloader.client import LibroFmClient` | `from librofm_downloader.session import LibroFmSession` |
| `from librofm_downloader.client import AuthError, M4BUnavailableError` | `from librofm_downloader.session import AuthError, M4BUnavailableError` |

## Testing Decisions

### Test Philosophy

- **Test through interfaces, not implementation.** After deepening, tests should construct real objects (Book, OutputPlan, fake LibroFmSession) rather than patching internal imports.
- **Each deep module gets its own test file** exercising its interface boundary.
- **Integration tests** verify pipeline stages connect correctly (sync_run tests use faked session + filesystem history).

### Test File Map

| New/Modified Test File | Tests What |
|------------------------|-----------|
| `tests/test_book.py` (NEW) | `Book` dataclass, `from_library_row()` edge cases: missing fields, int ISBN, nested narrators, PDF extras bool coercion, default values |
| `tests/test_path.py` (NEW/MOVED) | `sanitize()`, `resolve_path()` (default + custom pattern), `needs_subdirectory()`, `OutputPlan` resolution, subdirectory rules, cover/PDF path inclusion |
| `tests/test_session.py` (RENAMED) | Constructor injection, auth, all 4 endpoints via one transport, semaphore, error translation. Renamed from `test_client.py` |
| `tests/test_downloader.py` (SHRUNK) | Only download functions: `download_m4b`, `download_zip_part`, `_download_mp3`, `download_accompanying_files`, `download_book` (new 4-arg interface), `DownloadResult` shape |
| `tests/test_progress.py` (UPDATED) | Bound callable from `start_download()`, task identity internal, no more closure wiring tests needed |
| `tests/test_sync_run.py` (NEW) | Pipeline stages: config resolution, auth failure, empty library, filtering, limit, summary, exit codes, Ctrl+C |
| `tests/test_cli.py` (SHRUNK) | Only argparse parsing + exit-code translation. No more pipeline testing in CLI tests. Most current CLI test classes migrate to `test_sync_run.py`. |
| `tests/test_orchestrator.py` (UPDATED) | Takes `list[Book]` not `list[dict]`. Uses `DownloadResult`. History writing verified at caller level. |

### Estimated Test Impact

| File | Current tests | Post-refactor estimate | Change |
|------|--------------|----------------------|--------|
| `test_cli.py` | ~29 classes | ~5 classes (argparse + exit code only) | **-24 classes migrate out** |
| `test_downloader.py` | ~20 classes | ~14 classes (Book/sanitize/path tests move out) | **-6 classes migrate out** |
| `test_client.py` | ~6 classes | ~6 classes (renamed, signature updates) | Same count, rewrites |
| `test_book.py` (NEW) | 0 | ~8 classes | **+8 classes** |
| `test_path.py` (NEW) | 0 | ~12 classes | **+12 classes** |
| `test_sync_run.py` (NEW) | 0 | ~15 classes | **+15 classes** (migrated from cli) |

## Out of Scope

- **Select Mode implementation** (ADR #6) — this PRD defines where select mode plugs into the pipeline (stage 7), but does not implement the TUI itself.
- **Async/multiprocessing migration** — ADR 0001 explicitly rejects this; this PRD respects that decision.
- **Configuration schema changes** — no new config fields or validation rules.
- **Database or persistent queue** — beyond the tool's scope (cron-invoked CLI).
- **Retry logic** — not part of current requirements; would be a future addition to the Download Attempt module.
- **Checksum/integrity verification** — would consume `OutputPlan` but is not in scope.

## Further Notes

### Risks

1. **Import churn is the largest risk.** ~97 files import `Book` from `downloader.py`. The aggressive profile embraces this, but a mechanical find-and-replace + test run cycle is essential. Git's rename detection will help track the move.
2. **`LibroFmClient` rename breaks external references** if any exist (docs, user configs). The backward-compat alias in `client.py` mitigates this for one release cycle.
3. **History-writing relocation** is the most subtle behavioral change. Currently `download_book()` writes history after M4B success AND after MP3 success. Moving this to the caller means there's exactly one write point — but any caller of `download_book()` (not just the orchestrator) must remember to write history. Mitigation: make `download_all_books()` / `sync_run()` the only callers; treat `download_book()` as internal API.
4. **Orchestrator taking `list[Book]`** means orchestrator tests must construct Book objects instead of raw dicts. This is actually simpler (fewer dict keys to remember) but requires updating ~21 test helper functions.

### Success Criteria

- Every new module has ≤5 public symbols in its interface (depth measure)
- No test in `test_cli.py` patches `load_config`, `LibroFmClient`, `DownloadHistory`, `download_book`, OR `DownloadReporter` — those belong in `test_sync_run.py`
- `download_book()` has ≤5 parameters (down from 9)
- `LibroFmSession` endpoint methods have ≤3 parameters each (down from 5-6)
- All 259+ tests pass (including 3 known-hangy Ctrl+C tests)
- `cli.py` ≤80 lines (down from 246)
- Zero knowledge of raw Libro.fm API dict shape exists outside `book.py`

---

*PRD written from architecture review grilling session. Ready for issue breakdown via `/to-issues`.*
