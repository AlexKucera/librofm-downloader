# Issue #31: Sync Run Pipeline + CLI Slimming (HITL)

> **Date:** 2026-06-05
> **Type:** issue
> **Reference:** [Issue #31](https://github.com/AlexKucera/librofm-downloader/issues/31)
> **Parent:** #25 — PRD 001: Deepen Architecture — Module Depth & Domain Alignment

## Goal

Extract the entire Sync Run pipeline from `cli.run()` into a standalone `sync_run()` function in a new module. Slim `cli.py` to a thin argparse→exit adapter (~80 lines). Introduce `SyncRunResult`. This is the capstone issue that wires all previous deep modules together.

## What Was Done

### Phase 1 — TDD Vertical Slices (8 tests, 7 slices)

| Slice | Test(s) | Behavior Verified |
|-------|---------|-------------------|
| 1. Tracer bullet | `test_returns_sync_result_on_happy_path` | `SyncRunResult` dataclass exists; `sync_run()` callable with correct return shape |
| 2. Auth failure | `test_returns_fatal_error_on_auth_failure` | Auth error → `SyncRunResult(fatal_error="Authentication failed: ...")` |
| 3. Config error | `test_returns_fatal_error_on_config_error` | ConfigError → `SyncRunResult(fatal_error="Config error: ...")` |
| 4. Fetch failure | `test_returns_fatal_error_on_fetch_failure` | Library fetch exception → `SyncRunResult(fatal_error="Failed to fetch library: ...")` |
| 5. Happy path w/ downloads | `test_propagates_download_counts_from_orchestrator` | Download counts flow from orchestrator → `SyncRunResult` correctly |
| 6. Filtering & limit | `test_filters_already_downloaded_books`, `test_limit_caps_book_list` | History filter removes downloaded books; limit caps the list |
| 7. Select mode + interrupted | `test_select_mode_returns_not_implemented_result`, `test_interrupted_download_returns_interrupted_result` | ADR #6 stub branch point; Ctrl+C propagation |

### Phase 2 — CLI Slimming + Test Migration (35 migrated + 5 new CLI tests)

- **`librofm_downloader/sync_run.py`** created — full pipeline copied from `cli.run()`, return type changed from `int` to `SyncRunResult`, added `fatal_error` field and `select_mode` keyword-only parameter
- **`librofm_downloader/cli.py`** rewritten from 252→**65 lines** — thin adapter: `main()` parses args → calls `sync_run()` → translates result to exit code → `sys.exit()`
- **`tests/test_sync_run.py`** created — **43 tests** (8 new + 35 migrated from old test_cli.py), all patching at `librofm_downloader.sync_run.*` level
- **`tests/test_cli.py`** rewritten — **10 tests** only (5 exit-code translation + 5 argparse), patches only `cli.sync_run` / `cli.run`

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| `SyncRunResult` mirrors `OrchestratorResult` fields exactly + adds `fatal_error` | Keeps migration low-risk; orchestrator still returns its own type internally; `fatal_error` distinguishes "all caught up" (exit 0) from "auth failed" (exit 1) for cli.py's exit-code translation |
| `select_mode` as keyword-only parameter on `sync_run()` | ADR #6 integration point — clearly visible as optional extension, not part of core pipeline signature |
| Early-return paths return `SyncRunResult(fatal_error=...)` instead of raising | Domain function returns structured results; CLI layer decides exit codes. Makes `sync_run()` testable without catching exceptions |
| Keep `OrchestratorResult` undeprecated for now | `download_all_books()` still returns it internally; deprecation is cosmetic at this stage and can be done separately |
| All verbose output stays inside `sync_run()` | Verbose is domain-relevant (config values, auth status, library size); CLI layer doesn't need to know about it |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| SyntaxError on line 112 after edit | `replace` edit mangled a Unicode box-drawing string literal — `"── config"` got split mid-character by the old_text boundary match | Replaced the broken line with the correct完整 string literal using another `replace` edit |
| `fatal_error` field needed after initial tracer bullet | Initial slice used empty `SyncRunResult()` for all early returns, but cli.py couldn't distinguish "all caught up" (exit 0) from "auth failed" (exit 1) | Added `fatal_error: str \| None = None` field to `SyncRunResult`; updated all 4 early-return paths (config error, auth error, fetch failure, select mode stub) |
| 22 test classes to migrate with different patch targets | Every test in old `test_cli.py` patched `librofm_downloader.cli.*` collaborators (load_config, LibroFmSession, DownloadHistory, download_book, etc.) | Rewrote all tests patching at `librofm_downloader.sync_run.*` instead; test logic preserved verbatim |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/sync_run.py` | **New** — `SyncRunResult` frozen dataclass + `sync_run()` function (~271 lines). Full 12-stage pipeline: resolve paths → load config → authenticate → fetch library → filter/limit/select → download all → write history → summary → return result |
| `librofm_downloader/cli.py` | **Rewritten** — 252→65 lines. Thin argparse→exit adapter. `run()` calls `sync_run()`, maps `SyncRunResult.fatal_error` → exit 1, `.interrupted` → exit 130, else exit 0. `--select` flag added to argparse. |
| `tests/test_sync_run.py` | **New** — 43 tests across ~20 classes covering: happy path, auth failure, config error, fetch failure, empty library, mixed results, Ctrl+C, history filtering, limit capping, format wiring, verbose output, workers flag, parallel workers=1 parity, parallel Ctrl+C drain, summary ordering, concurrency, verbose+parallel, partial file safety, history resolution (XDG/CWD), config resolution messages, missing files errors, select mode stub |
| `tests/test_cli.py` | **Rewritten** — 22 classes → 2 classes (10 tests). `TestCLIExitCodeTranslation` (5 tests) + `TestCLIArgparse` (5 tests). Zero internal collaborator patching. |

## Acceptance Criteria Report

| # | Criterion | Status |
|---|-----------|--------|
| 1 | `sync_run()` returns correct `SyncRunResult` for: happy path, auth failure, empty library, mixed results, Ctrl+C | ✅ 43 tests cover all paths |
| 2 | `cli.py` ≤80 lines; contains only argparse + exit code translation | ✅ **65 lines** |
| 3 | No test in `test_cli.py` patches load_config/LibroFmSession/DownloadHistory/download_book/DownloadReporter | ✅ Only patches `sync_run` / `run` |
| 4 | All migrated tests pass in `test_sync_run.py` | ✅ **43/43 pass** |
| 5 | Filtering (already-downloaded + limit) produces correct book list | ✅ 2 dedicated tests |
| 6 | History written exactly once per successful download (in sync_run, not in download_book) | ✅ `_write_history()` in download closure at sync_run.py:210–213 |
| 7 | Select mode stage 7 is a clear if/branch point (implementation deferred) | ✅ Lines 180–183: `if select_mode:` guard with fatal_error return |
| 8 | HITL review required before merge | ⏳ Pending user review |

## Open Items & Next Steps

- [ ] **HITL review** — run `librofm` end-to-end with real credentials to verify thin adapter works correctly
- [ ] **Deprecate `OrchestratorResult`** — consider having `download_all_books()` return `SyncRunResult` directly, or add a deprecation notice
- [ ] **ADR #6 implementation** — wire `--select` flag through to `selector.select_books()` when that module is built
- [ ] **3 pre-existing hanging tests** in `test_orchestrator.py` (Ctrl+C drain tests) remain unresolved — unrelated to this issue

---

*Log written by write-log skill*
