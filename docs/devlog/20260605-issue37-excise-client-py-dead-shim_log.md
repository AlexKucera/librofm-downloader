# Slice 1: Excise client.py Dead Shim

> **Date:** 2026-06-05
> **Type:** issue (slice)
> **Reference:** [Issue #37](https://github.com/AlexKucera/librofm-downloader/issues/37) — PRD-003: Deepen Codebase Architecture

## Goal

Remove the deprecated `client.py` re-export shim and its duplicate test file that have shipped since Issue #27's migration. Migrate unique rate-limiter tests into `test_session.py`. Verify zero production references remain.

## What Was Done

- **Migrated `TestApiRateLimiter`** (4 tests) from `tests/test_client.py` → `tests/test_session.py`:
  - `test_semaphore_blocks_at_capacity` — 4 concurrent callers, 4th blocks
  - `test_semaphore_releases_on_exception` — semaphore released even on error
  - `test_cdn_downloads_bypass_semaphore` — CDN downloads not limited by API semaphore
  - `test_authenticate_and_fetch_library_not_limited` — auth/library don't acquire semaphore
- **Deleted** `librofm_downloader/client.py` (32-line deprecated re-export shim with `DeprecationWarning`)
- **Deleted** `tests/test_client.py` (588 lines of near-duplicate tests)
- **Added imports** (`threading`, `time`) to `tests/test_session.py` for rate-limiter tests
- Verified: **zero production `.py` files import from `client.py`**
- Verified: **no user-facing docs** reference `LibroFmClient` or `client.py` (only CHANGELOG history + devlog/prd/adr archives)

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Migrate all 4 rate-limiter tests, not just the 3 listed in AC | AC mentioned "3" but there are actually 4; all provide valuable coverage of different semaphore behaviors |
| Leave devlog/prd/adr historical references untouched | These are records of past work — editing them would falsify project history |
| Leave CHANGELOG.md entries as-is | Accurate changelog entry recording the Issue #27 rename event |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| Edit tool schema error on first attempt | Used wrong anchor format (plain text instead of LINE:HASH) for `insert_after` | Re-read file to get proper LINE:HASH anchors, used correct format |
| Full test suite hangs on KeyboardInterrupt | 3 pre-existing Ctrl+C hang tests in orchestrator | Ran suite with `-k "not (test_ctrl_c or test_keyboard)"` to get clean pass count; these are known from Issue #17 fix session |
| Repeated tool call loop | Tool calls were duplicated many times in a loop | Compressed and continued with clean edit |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/client.py` | **DELETED** — 32-line deprecated re-export shim |
| `tests/test_client.py` | **DELETED** — 588 lines of duplicate tests |
| `tests/test_session.py` | **+253 lines** — Added `threading`/`time` imports + `TestApiRateLimiter` class with 4 migrated tests |

## Test Impact

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Total tests collected | 425 | 413 | −12 |
| Rate-limiter tests location | `test_client.py` only | `test_session.py` only | Migrated |
| Production code importing `client.py` | 0 | 0 | Unchanged |
| Net lines of code removed | — | — | −337 (−32 shim −588 dupes +253 migrated) |

## Open Items & Next Steps

- [ ] None — all 6 acceptance criteria met. Ready to commit.

---
*Log written by write-log skill*
