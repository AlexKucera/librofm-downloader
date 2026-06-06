# PRD-003: Deepen Codebase Architecture

## Problem Statement

The codebase has solid module boundaries and excellent test coverage (~380+ tests), but several architectural friction points have accumulated across 35 issues of rapid feature development:

1. **Dead code**: A deprecated `client.py` shim (Issue #27 migration) and its duplicate test file still ship, adding 620 lines of maintenance surface for zero benefit.
2. **Encapsulation leak**: `downloader.py` reaches through two layers of private attributes (`session._client._transport`) to get the HTTP transport — the tightest cross-module coupling in the codebase.
3. **DRY violations**: The streaming download loop is duplicated between `download_m4b()` and `download_zip_part()` (~40 lines each). The `download_book()` format-strategy branches repeat the same success-path logic 3 times.
4. **Misplaced responsibility**: `_write_history()` lives in `downloader.py` but has nothing to do with downloading — it's an orphan called only from `sync_run.py`'s closure. The progress reporter doubles as a shared-state bag for `cancel_event`.
5. **Composition root brittleness**: `sync_run.py` imports 7 sibling modules and constructs everything inline with zero dependency injection, forcing all 43 tests onto fragile `unittest.mock.patch` of fully-qualified names.
6. **Test organization drift**: Tests for `path.py` functions live in `test_downloader.py`. Integration-style pipeline tests live in `test_progress.py`. A test class is duplicated verbatim.

Each friction point is small individually, but together they create hidden coupling that will make future changes (new formats, new APIs, refactoring) riskier and more tedious than they need to be.

## Solution

A phased architecture deepening that addresses each friction point in priority order:

- **Phase 1** (quick wins): Excise dead code, cap the encapsulation leak
- **Phase 2** (pipeline tightening): Extract duplication, relocate orphan, separate concerns
- **Phase 3** (test cleanup): Reorganize drifted tests, remove duplicates

No new user-facing behaviour. No new CLI flags or config fields. This is pure structural improvement — reducing coupling, increasing locality, and turning hypothetical seams into real ones.

## User Stories

1. As a maintainer, I want all deprecated migration shims removed from production imports, so that I don't wonder which client module is the real one.
2. As a maintainer, I want `LibroFmSession`'s internal structure protected behind a public property, so that refactoring session internals doesn't silently break `downloader.py`.
3. As a maintainer, I want the streaming download loop defined in one place, so that bug fixes or enhancements (retry, throttling) only need one edit.
4. As a maintainer, I want history persistence logic consolidated in the history module, so that `downloader.py` is purely about downloading.
5. As a maintainer, I want the progress reporter to only handle reporting, so that its interface isn't polluted by cancellation mechanism concerns.
6. As a maintainer, I want `sync_run.py`'s key collaborators injectable, so that tests can pass fakes instead of patching fully-qualified import paths.
7. As a maintainer, I want each test file to test exactly one module, so that I can unambiguously find where a function's tests live.
8. As a maintainer, I want no duplicated test classes, so that every test failure maps to exactly one root cause.
9. As a future developer adding a new audio format, I want a single place to add the format strategy branch without touching the streaming loop.
10. As a future developer writing tests for path resolution, I want those tests in `test_path.py`, not scattered across `test_downloader.py`.

## Implementation Decisions

### Phase 1: Dead Code Excision + Encapsulation

#### Decision 1.1: Delete `client.py` and `test_client.py`

- Remove `librofm_downloader/client.py` entirely (32-line deprecation shim)
- Remove `tests/test_client.py` entirely (588 lines, near-duplicate of `test_session.py`)
- Migrate the 3 unique rate-limiter tests (semaphore blocking, CDN bypass, exception release) into `tests/test_session.py`
- Verify zero production code references remain via grep
- Update any documentation references to the old `LibroFmClient` name

#### Decision 1.2: Add public `transport` property to `LibroFmSession`

- Add a `@property` getter `transport` on `LibroFmSession` that returns `self._client._transport`
- Update `downloader.py` to call `session.transport` instead of `session._client._transport`
- This turns a private-attribute-chain access into a stable interface contract — if session internals refactor later, only the property body changes

### Phase 2: Pipeline Tightening

#### Decision 2.1: Extract `_stream_to_file()` helper

- Extract a private `_stream_to_file(url, output_path, transport, progress, cancel_event) -> Path` function from the common loop body shared by `download_m4b()` and `download_zip_part()`
- The helper handles: open `.partial` file → seek to existing size for resume → stream chunks in `CHUNK_SIZE` blocks → check `cancel_event` on each chunk → atomic rename to final path
- Both `download_m4b()` and `download_zip_part()` become thin wrappers: call `_stream_to_file()`, then do their post-processing step (return Path vs extract ZIP)
- This reduces ~80 lines of duplicated loop logic to ~40 lines in one place + 2 small wrappers

#### Decision 2.2: Relocate `_write_history` to `history.py`

- Move `_write_history(history, book, fmt, path)` from `downloader.py` to `history.py` as a module-level function
- Update the single call site in `sync_run.py`'s `_make_download_fn()` closure to import from `history` instead of `downloader`
- Remove `HistoryEntry` import from `downloader.py` (no longer needed there)
- Optionally make it a method on `DownloadHistory` if it fits naturally; otherwise keep as module-level function adjacent to `DownloadHistory`

#### Decision 2.2.3: Factor out common success-path from `download_book()` format branches

- The three format-strategy blocks (`m4b_mp3_fallback`, `mp3_only`, `m4b_only`) in `download_book()` each repeat: rename chapters → download accompanying files → return success `DownloadResult`
- Extract the post-download success steps into a helper that all three branches call
- Each branch becomes: attempt download → if success, call success helper → return result

#### Decision 2.3: Pass `cancel_event` explicitly, not through reporter

- Currently `sync_run.py` sets `reporter.cancel_event = cancel_event`, then `downloader.py` reads `reporter.cancel_event.is_set()`
- Change: thread `cancel_event` through the explicit parameter chain it already partially follows: `sync_run` closure → `download_book()` → `download_m4b()` / `download_zip_part()` already accept `cancel_event`; just wire it through `download_book` too
- Remove `cancel_event` attribute from both reporter classes (`PlainTextReporter`, `ProgressReporter`)
- Remove `reporter.cancel_event = ...` assignment from `sync_run.py`

### Phase 3: Test Organization Cleanup

#### Decision 3.1: Move path-related tests from `test_downloader.py` to `test_path.py`

- Identify tests in `test_downloader.py` that exercise `sanitize()`, `resolve_path()`, `needs_subdirectory()`, `resolve_output_plan()` (imported from `path.py` but tested inside downloader tests)
- Move them to `tests/test_path.py` under appropriately-named test classes
- Verify all moved tests still pass in their new home

#### Decision 3.2: Move integration-style tests from `test_progress.py` to `test_sync_run.py`

- Identify tests in `test_progress.py` that patch `sync_run` internals (`TestFailureIsolationCLI`, `TestFatalVsBookLevel`) — these are full-pipeline integration tests
- Move to `tests/test_sync_run.py` since they exercise the sync_run pipeline

#### Decision 3.3: Delete duplicated `TestParallelProgressCallbackWiring`

- The class appears twice in `test_progress.py` (lines ~1087–1170 and ~1171–1254) with identical methods
- Delete the second occurrence

### Deferred: Make `sync_run.py` injectable (Candidate #5)

- This is the highest-leverage refactor but also the most work
- Defer to a future PRD because it touches the composition root and would interact with any feature development happening there
- Record as a known opportunity for when `sync_run.py` is next opened for other reasons

### Deferred: Consolidate `SyncRunResult` / `OrchestratorResult` (Candidate #7)

- Low-friction duplication; both types serve different layers
- Defer until either type needs modification for other reasons

## Testing Decisions

### Principles

- All existing tests must continue passing after each phase
- New tests target external behaviour (function inputs/outputs), not implementation details
- Use the same patterns established in the codebase: `httpx.MockTransport` for HTTP, duck-typed fakes for reporters, `threading.Event` for cancellation
- Every deletion (dead code removal, test relocation) must be verified by running the full test suite

### Modules to Test

| Change | New Tests Needed | Rationale |
|--------|-----------------|-----------|
| `_stream_to_file()` extraction | 3-5 tests | Resume, cancel-mid-stream, atomic rename, fresh download, error propagation |
| `session.transport` property | 1-2 tests | Returns correct transport, works with MockTransport injection |
| `_write_history` relocation | 0 new tests | Existing coverage moves with the function; verify import path |
| `cancel_event` wiring change | 0 new tests | Behaviour unchanged; verify existing cancel tests pass |
| Dead code deletion | 0 new tests | Verify suite passes without deleted modules |

### Prior Art

- Streaming download tests: existing `test_download_m4b_resume`, `test_download_zip_part_extract` patterns in `test_downloader.py`
- Transport injection: all 14 `test_session.py` tests use `httpx.MockTransport`
- Cancel-event threading: existing cooperative cancellation tests in `test_orchestrator.py` (lines 691–816)
- Property exposure: `book.py` frozen dataclass attribute access pattern

## Out of Scope

- **`sync_run.py` dependency injection** (Candidate #5): deferred to future PRD — high value but high scope, better done when sync_run is next touched for feature work
- **`SyncRunResult` / `OrchestratorResult` consolidation** (Candidate #7): low priority, no current drift
- **`session.py` auth guard deduplication** (minor DRY — 4 methods × 2 lines): noted but not worth a dedicated change
- **`needs_subdirectory()` renaming** (naming clarity in `path.py`): cosmetic, no behavioural impact
- **New features, formats, or CLI flags**: this PRD is purely structural
- **Performance optimization**: no performance regressions expected, but no improvements targeted either
- **Documentation site updates**: unless API-visible names change (e.g., `client.py` removal may warrant a migration note)

## Further Notes

### Execution Order

Phases are independent enough to be done in any order, but the recommended sequence is:

1. **Phase 1 first** — deletes files and adds a one-line property. Zero risk, clears deck.
2. **Phase 2 second** — the meaty refactor. Do each decision as a self-contained commit so any can be reverted independently.
3. **Phase 3 last** — test reorganization is safe to do after Phase 2 stabilizes.

### Risk Assessment

| Change | Risk | Mitigation |
|--------|------|------------|
| Delete `client.py` | Low | Grep confirms zero production imports |
| `session.transport` property | Trivial | One-line addition, one-line caller change |
| `_stream_to_file()` extraction | Medium | Preserve exact chunk-loop semantics; comprehensive test coverage |
| `_write_history` relocation | Trivial | One call site; grep to confirm |
| `cancel_event` wiring | Low | Parameter already flows through most of the stack |
| Test relocation | Low | Move-only, no logic changes; full suite verification |

### Relationship to Past Issues

This PRD addresses technical debt surfaced during Issues #26–#35. Each issue added functionality correctly; this PRD pays down the structural cost that accumulated across that burst of delivery.
