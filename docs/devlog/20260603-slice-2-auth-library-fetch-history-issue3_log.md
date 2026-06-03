# Slice 2: Auth + Library Fetch + History (Issue #3)

> **Date:** 2026-06-03
> **Type:** slice
> **Reference:** [Issue #3](https://github.com/AlexKucera/librofm-downloader/issues/3)

## Goal

Build the data layer that feeds into downloads later: **OAuth2 authentication**, **paginated library fetching**, **download history tracking**, and a **CLI skeleton** that wires everything end-to-end — all test-driven with vertical slices.

## What Was Done

### 1. Client Module (`librofm_downloader/client.py`, 99 lines)
- **`AuthError`** exception — clear error type for auth failures
- **`LibroFmClient`** class:
  - `DEFAULT_HEADERS` — `X-LibroFm-AppVer: 7.34.8`, `User-Agent: okhttp/5.3.2`
  - `__init__(base_url, username, password, timeout)` — configurable base URL and timeout
  - `authenticate(transport=None)` — OAuth2 password grant → `POST /oauth/token` → returns `access_token`. Accepts `httpx.BaseTransport` override for testing
  - `fetch_library(transport=None)` — `GET /api/v10/library` with Bearer token, auto-paginates via `next_page` key until exhausted. Returns `list[dict]` of all books

### 2. History Module (`librofm_downloader/history.py`, 64 lines)
- **`HistoryEntry`** — `@dataclass(frozen=True)` with fields: `isbn`, `title`, `format`, `path`, `downloaded_at`
- **`DownloadHistory`** class:
  - `__init__(path)` — loads existing JSON from disk; missing/corrupt → empty with warning logged
  - `find(isbn)` → `HistoryEntry | None` — look up by ISBN
  - `is_downloaded(isbn)` → `bool` — fast membership check
  - `write(entry)` — persist entry to disk (creates parent dirs)
  - `_flush()` — write in-memory state to disk as indented JSON

### 3. CLI Skeleton (`librofm_downloader/cli.py`, 60 lines)
- **`run(config_path, secrets_path, history_path) -> int`** — main pipeline:
  1. Load config (`load_config`)
  2. Create client + authenticate
  3. Fetch all library pages
  4. Load download history, filter out already-downloaded ISBNs
  5. Print new books via `rich.Console` (or "All caught up!" message)
  6. Return exit code 0 (success) or 1 (failure)

### Test Suite (16 new tests across 3 files)

| File | Class | Tests | What's Verified |
|------|-------|-------|-----------------|
| `tests/test_client.py` | `TestAuthenticate` | 3 | Token returned on valid creds, AuthError on 401, required headers present |
| `tests/test_client.py` | `TestFetchLibrary` | 3 | Single-page fetch, multi-page pagination, pre-auth check |
| `tests/test_history.py` | `TestWriteAndRead` | 1 | Write + read back by ISBN |
| `tests/test_history.py` | `TestIsDownloaded` | 2 | True for downloaded, False for unknown |
| `tests/test_history.py` | `TestFileCreation` | 1 | File created after write (with subdirs) |
| `tests/test_history.py` | `TestCorruptRecovery` | 3 | Corrupt JSON→empty+warning, missing file→empty, empty file→empty |
| `tests/test_cli.py` | `TestCLIHappyPath` | 1 | Exit 0, prints book titles |
| `tests/test_cli.py` | `TestCLIAuthFailure` | 1 | Exit 1, prints "Authentication failed" |
| `tests/test_cli.py` | `TestCLIHistoryFiltering` | 1 | Downloaded books filtered from output |

**Total: 41 tests** (25 config + 6 client + 7 history + 3 CLI) — all passing

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| `httpx.MockTransport` for testability | Each handler is a simple `request → Response` function; no real HTTP, no monkey-patching, no external fixtures |
| New `httpx.Client()` per method call | Script runs once per invocation; avoids stale connections/state leak between auth and fetch calls |
| Pagination via `next_page` key (not Link header) | Matches Libro.fm API's documented pagination pattern; simpler than parsing Link headers |
| `@dataclass(frozen=True)` for HistoryEntry | Immutable records prevent accidental mutation; same pattern as Config |
| Corrupt JSON → empty + warning (not crash) | Defensive: user can delete/fix the file and re-run; script never loses data from a corrupt history |
| `rich.Console` for CLI output | Already a dependency; gives colorized output without manual ANSI codes |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| SyntaxError: unexpected character after line continuation | `write()` tool embedded literal `\n` escape sequences instead of actual newlines in multi-line strings | Used `write()` with proper heredoc content instead of `edit()` with escaped newlines |
| Stale anchor-hash mismatches during edits | Edit tool caches anchors from previous reads; re-reading invalidates them | Always `read()` before `edit()` when working on a file that was just written |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/client.py` | **New** — LibroFmClient, AuthError, OAuth2 auth, paginated library fetch (99 lines) |
| `librofm_downloader/history.py` | **New** — DownloadHistory, HistoryEntry, JSON read/write with corrupt recovery (64 lines) |
| `librofm_downloader/cli.py` | **New** — run() pipeline: config→auth→fetch→filter→print (60 lines) |
| `tests/test_client.py` | **New** — 6 tests: auth success/failure/headers, single+multi page fetch, pre-auth guard |
| `tests/test_history.py` | **New** — 7 tests: write/read, is_downloaded, file creation, corrupt/missing/empty recovery |
| `tests/test_cli.py` | **New** — 3 tests: happy path exit 0, auth failure exit 1, history filtering |

## Acceptance Criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | OAuth2 password grant returns access_token on valid credentials | ✅ `test_returns_access_token_on_valid_credentials` |
| 2 | Auth fails clearly on invalid credentials (exit code 1, descriptive message) | ✅ `test_raises_auth_error_on_invalid_credentials` + `test_exits_one_on_auth_failure` |
| 3 | Library fetch returns all books across multiple pages | ✅ `test_paginates_through_all_pages` |
| 4 | Single-page library handled correctly (no infinite loop) | ✅ `test_returns_books_on_single_page` |
| 5 | Required headers sent with every request | ✅ `test_sends_required_headers_with_auth_request` |
| 6 | History file created if it does not exist | ✅ `test_file_created_after_write` |
| 7 | Previously downloaded ISBNs correctly identified | ✅ `test_returns_true_for_downloaded_isbn` + `test_returns_false_for_unknown_isbn` |
| 8 | Corrupt/missing history JSON treated as empty (with warning) | ✅ 3 tests in `TestCorruptRecovery` |
| 9 | CLI prints list of new (undownloaded) books | ✅ `test_exits_zero_and_prints_books` |
| 10 | CLI exits 0 when auth succeeds and library is fetched | ✅ `test_exits_zero_and_prints_books` |
| 11 | ~30 tests | ✅ **41 tests** (exceeds target) |
| 12 | All tests pass | ✅ **41/41 passed** |

**11/11 AC met** ✅

## Open Items & Next Steps

- This slice builds the data layer only — no actual downloading yet
- Next issue would cover: download logic (M4B/MP3), progress tracking, path resolution, or the full sync run per the project roadmap
- The `run()` function is ready to be wired to `__main__.py` or a CLI entry point (e.g., `python -m librofm_downloader`)

---
*Log written by write-log skill*
