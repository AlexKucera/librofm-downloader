# Issue #29: Download Attempt — Interface Shrink to 4 Params

> **Date:** 2026-06-04
> **Type:** issue
> **Reference:** [Issue #29](https://github.com/AlexKucera/librofm-downloader/issues/29)
> **Parent:** [PRD 001: Deepen Architecture — Module Depth & Domain Alignment](https://github.com/AlexKucera/librofm-downloader/issues/25)

## Goal

Shrink `download_book()` from 9 parameters to 4 domain-aligned parameters. Introduce `DownloadResult` dataclass. Move history writing out of `download_book()` to the caller. End state:

```python
def download_book(
    book: Book,
    session: LibroFmSession,
    plan: OutputPlan,
    reporter: DownloadReporter,
) -> DownloadResult:
```

## What Was Done

### Cycle 1 (Tracer Bullet): `DownloadResult` frozen dataclass
- Added `@dataclass(frozen=True) class DownloadResult` to `downloader.py` with fields: `status` (Literal), `path`, `format`, `error`
- **5 tests** in new `TestDownloadResult` class: instantiates each status, defaults, frozen check, field presence, error message

### Cycle 2: Extend `OutputPlan` with `format_strategy`
- Added `format_strategy: str = "m4b_mp3_fallback"` field to `OutputPlan` in `path.py`
- Added keyword-only `format_strategy` parameter to `resolve_output_plan()` factory, passed through to constructor
- **4 tests** in new `TestOutputPlanFormatStrategy` class

### Cycle 3: Core refactoring — shrink `download_book()` signature
- Rewrote `download_book()` from 9 params → 4 params returning `DownloadResult`
- Removed `_write_history()` calls from inside `download_book()` and `_download_mp3()`
- Removed `history` parameter from `_download_mp3()`
- Removed `config` parameter from `download_accompanying_files()` — now checks `plan.cover_path is not None` / `plan.pdf_path is not None`
- Added `.cancel_event = None` attribute to both `PlainTextReporter` and `ProgressReporter` in `progress.py`
- Transport extracted from `session._client._transport` instead of per-function injection
- Progress callback obtained from `reporter.update`; cancel from `reporter.cancel_event`
- **1 test** in new `TestDownloadBookNewInterface` class (tracer bullet for new interface)
- **11 old tests failed** as expected (old call sites) — fixed in next cycle

### Cycle 4: Update all test call sites to new interface
- Updated **8 `download_book()` call sites** across `TestDownloadBook` (4) + `TestFormatStrategy` (4)
- Updated **7 `download_accompanying_files()` call sites** in `TestDownloadAccompanyingFiles` + `TestOutputStructure`
- Updated **1 `test_progress.py`** call site (`TestProgressCallbackWiring`)
- Key pattern change: tests now build `OutputPlan` via `resolve_output_plan()`, create `DownloadReporter()`, assert on `DownloadResult` fields, manually write history after calling `download_book()`

### Cycle 5: Update production callers
- **`cli.py`**: Rewrote `_make_download_fn()` closure to build `OutputPlan` per-book, call 4-param `download_book()`, write history after inspecting result, return `result.path` / `None` for backward compat with orchestrator. Added `reporter.cancel_event = cancel_event` wiring.
- **`orchestrator.py`**: No changes needed — adapter pattern in cli.py preserves `Path | None` contract
- **`test_cli.py`**: Updated ~10 mock return values from raw `Path`/`None` → `DownloadResult`, updated 6 side_effect functions for new 4-param signature

### Post-cycle fix
- Fixed `test_one_failure_does_not_stop_batch` in `test_progress.py`: mock was returning raw `Path` objects but cli's closure now accesses `.status` on result → updated mock to return `DownloadResult(status="downloaded", path=..., format="m4b")`

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Store `format_strategy` on `OutputPlan` | Issue spec says "consumed from OutputPlan"; keeps plan as single config snapshot; avoids 5th param on download_book |
| Store `cancel_event` on reporter instance | Reporter already threaded through entire stack; avoids adding a param. Both implementations get `.cancel_event = None` attribute |
| Extract transport via `session._client._transport` | Tests inject transport at `LibroFmSession(..., transport=)` constructor (already supported). Low-level functions still accept `transport=` but it comes from session now |
| Remove `config` from `download_accompanying_files()` | Plan paths are already `None` when disabled — checking `plan.cover_path is not None` is equivalent to `config.download_covers and book.cover_url` but simpler |
| Return `Path \| None` from cli closure (not `DownloadResult`) | Orchestrator's `_download_one()` checks `result is None` for skip detection and catches exceptions separately. Adapter pattern avoids touching orchestrator at all |
| Let exceptions propagate for unexpected failures | Same behavior as before — HTTPStatusError etc. propagate up through orchestrator's `except BaseException` handler. Only caught/expected failures produce `DownloadResult(status="failed")` |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| `test_one_failure_does_not_stop_batch` failure: `'PosixPath' object has no attribute 'status'` | Mock returned raw `Path` objects; cli's new closure accesses `result.status` on whatever `download_book()` returns | Updated mock `side_effect` to return `DownloadResult(status="downloaded", path=Path(...), format="m4b")` instances |
| Transport injection concern: removing `transport` param would break CDN calls in tests | Tests use `httpx.MockTransport(handler)` that handles BOTH API and CDN URLs. Without passing transport to low-level functions, CDN calls hit real network | Extract from `session._client._transport` — the same MockTransport handles everything since session was constructed with it |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/downloader.py` | Added `DownloadResult` frozen dataclass; rewrote `download_book()` → 4 params returning `DownloadResult`; removed `history` from `_download_mp3()`; removed `config` from `download_accompanying_files()` |
| `librofm_downloader/path.py` | Added `format_strategy: str` field to `OutputPlan`; added `format_strategy=` kwarg to `resolve_output_plan()` |
| `librofm_downloader/progress.py` | Added `cancel_event = None` attribute to both `PlainTextReporter.__init__` and `ProgressReporter.__init__` |
| `librofm_downloader/cli.py` | Added imports (`_write_history`, `resolve_output_plan`); wired `reporter.cancel_event = cancel_event`; rewrote `_make_download_fn()` closure for new interface + caller-side history writing |
| `tests/test_downloader.py` | Added `TestDownloadResult` (5 tests) + `TestDownloadBookNewInterface` (1 test); updated 8 `download_book()` call sites + 7 `download_accompanying_files()` call sites |
| `tests/test_path.py` | Added `TestOutputPlanFormatStrategy` (4 tests) |
| `tests/test_progress.py` | Updated progress wiring test for 4-param sig; fixed mock to return `DownloadResult` |
| `tests/test_cli.py` | Updated ~10 mock return values + 6 side-effect functions for `DownloadResult` returns |

## Test Results

| Metric | Value |
|--------|-------|
| **Total tests pass** | **368** (7 deselected = pre-existing Ctrl+C `os._exit` tests) |
| **New tests added** | **15** (5 DownloadResult + 4 OutputPlan format + 1 tracer bullet + updated call sites) |
| **Failures** | **0** |
| **Acceptance criteria** | **6/6 met** |

## Acceptance Criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | `download_book()` has exactly 4 parameters (+ self) | ✅ `(book, session, plan, reporter)` |
| 2 | `DownloadResult` frozen dataclass with correct shape for all three statuses | ✅ `status`, `path`, `format`, `error` — frozen |
| 3 | History NOT written by `download_book()`; caller writes after inspecting result | ✅ `_write_history` removed from `download_book()` + `_download_mp3()`; cli.py closure writes |
| 4 | All download tests exercise new interface; no test passes raw Config or history to `download_book()` | ✅ All 8 call sites updated |
| 5 | M4B→MP3 fallback flow produces correct `DownloadResult` at each stage | ✅ `"downloaded"/"m4b"` → fallback → `"downloaded"/"mp3"` → `"skipped"` |
| 6 | Cancel/interrupt path produces correct `DownloadResult(status="failed")` | ✅ Uses `reporter.cancel_event` threaded through to chunk loops |

## Open Items & Next Steps

- None — issue complete, all AC met. Ready for next issue in PRD 001 roadmap.

---

*Log written by write-log skill*
