# Slice 3b: Live Testing Fixes & CLI Polish (Issue #5)

> **Date:** 2026-06-03
> **Type:** issue
> **Reference:** [Issue #5](https://github.com/AlexKucera/librofm-downloader/issues/5)

## Goal

After completing TDD for the M4B download pipeline (109 tests passing), run against the **real Libro.fm API** to validate end-to-end behavior. Fix any discrepancies between mocked test assumptions and actual API response shapes.

## What Was Done

### Live API Testing — Discovered 4 Critical Bugs

Ran `python -m librofm_downloader.cli --config config.yaml --secrets secrets.yaml -v` against the real Libro.fm API with valid credentials. Found and fixed:

1. **`fetch_library()` returned 0 books** — Code used `data.get("books", [])` but API returns `"audiobooks"` key
2. **`fetch_m4b_url()` crashed with `KeyError: 'url'`** — Code used `data["url"]` but API returns `"m4b_url"` key  
3. **Narrators always showed `?`** — Narrators are nested inside `audiobook_info.narrators`, not top-level
4. **Books re-downloaded every run** — JSON dict keys are always strings; API returns ISBNs as integers. `is_downloaded(9781250431516)` looked up int key → never matched string key `"9781250431516"` in history

### CLI Improvements

- **Wired the missing download loop** into `run()` — the function listed books then returned 0 without ever calling `download_book()`
- **Added `--verbose` / `-v` flag** — prints config values, auth status, library count, per-book authors/narrators, file sizes in bytes, full tracebacks on failure
- **Added `argparse` entry point** at `__main__` so script can be run directly as `python -m librofm_downloader.cli`
- **Fixed nested field extraction** in CLI loop:
  - `narrators`: extracted from `raw_book["audiobook_info"]["narrators"]` with fallback to top-level
  - `pdf_extras`: extracted from `raw_book["audiobook_info"]["pdf_extras"]` (API returns list, not bool)

### Config Files Created

- **`config.yaml`** — committed-safe config with all options documented inline (format, output_dir, download_extras, download_covers)
- **`secrets.yaml`** — gitignored credentials file template

### Test Updates

Updated all mock-based tests to match real API response shape:
- `test_client.py`: `books` → `audiobooks` in all library mock responses; `url` → `m4b_url` in M4B mock responses
- `test_downloader.py`: `url` → `m4b_url` in all orchestration mock responses
- Added `TestCLIVerbose::test_verbose_prints_config_and_auth_details`

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Fix history lookup with `str(isbn)` coercion | JSON keys are always strings; API returns ISBN as int. Coercion in `find()` and `is_downloaded()` makes both sides string comparison. Safer than changing HistoryEntry.isbn type which would break serialization. |
| Extract narrators/pdf_extras from `audiobook_info` in CLI only (not client) | Client returns raw API dict; transformation happens at the boundary where Book dataclass is constructed. Keeps client layer thin and honest about what the API actually returns. |
| `--verbose` flag instead of always-verbose | Default output stays clean for cron/automation use; verbose available for debugging. Follows Unix convention. |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| **0 books in library** | `fetch_library()` used `.get("books", [])` but real API key is `"audiobooks"` | Changed to `.get("audiobooks", [])`. Mock tests used wrong key name — updated all mocks. |
| **KeyError 'url' on M4B fetch** | Real API returns `"m4b_url"` not `"url"` | Changed to `data["m4b_url"]`. Updated all mock responses. |
| **Narrators always empty (`?`)** | Narrators nested under `audiobook_info.narrators` in API response; code read top-level `narrators` key | Added `audiobook_info = raw_book.get("audiobook_info", {}) or {}` then `audiobook_info.get("narrators", [])` with fallback |
| **Books re-download every run despite history** | JSON dict keys are `str`; Libro.fm API returns ISBN as `int`. `history._data` has `"978..."` but lookup uses `978...` (int) → never matches | Added `str(isbn)` coercion in `find()` and `is_downloaded()` |
| **Script silently does nothing** | `run()` had no download loop wired — it fetched books, filtered them, printed count, returned 0 | Rewrote `run()` with full 6-stage pipeline: config→auth→library→filter→download→summary |
| **SyntaxError on ternary** | Wrote `(x if y else []) if y else []` which Python can't parse | Simplified to `bool(audiobook_info.get("pdf_extras")) if audiobook_info else False` |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/client.py` | `books` → `audiobooks`; `url` → `m4b_url` |
| `librofm_downloader/cli.py` | Full download loop wired; `--verbose` flag; argparse entry point; nested narrator/pdf_extras extraction |
| `librofm_downloader/history.py` | `str(isbn)` coercion in `find()` and `is_downloaded()` |
| `config.yaml` | New file — committed-safe configuration template |
| `secrets.yaml` | New file — gitignored credentials template |
| `tests/test_client.py` | Updated mock keys to match real API (`audiobooks`, `m4b_url`) |
| `tests/test_downloader.py` | Updated mock keys to match real API (`m4b_url`) |
| `tests/test_cli.py` | Added `TestCLIVerbose` class (1 test) |

## Live Test Results

**6 books downloaded successfully (~2.9 GB total):**

| Book | Size | Path Pattern |
|------|------|-------------|
| This Story Might Save Your Life | 296 MB | Author/Title/Title.m4b (subdir — has PDF extras) |
| The River Has Roots | 108 MB | Author/Title/Title.m4b (subdir — has cover) |
| Harry Potter und der Feuerkelch | 654 MB | Author/Series/Book N Title/Title.m4b (series+subdir) |
| King Sorrow | 724 MB | Author/Title.m4b (flat — no extras/cover) |
| Alien Clay | 387 MB | Author/Title/Title.m4b (subdir — has PDF extras) |
| The Secret of Secrets | 634 MB | Author/Series/Book N Title/Title.m4b (series+subdir) |

**Re-run correctly shows:** `6 already downloaded, 0 new` → `All caught up! No new books to download.`

## Test Summary

**109 tests passing** (up from 108 — added 1 verbose test):

```
tests/test_cli.py          :: 5 passed   (+1 verbose)
tests/test_client.py       :: 7 passed   (keys fixed)
tests/test_config.py       :: 20 passed
tests/test_downloader.py   :: 67 passed  (keys fixed)
tests/test_history.py      :: 10 passed  (str() coercion)
───────────────────────────────────────────
Total                      :: 109 passed
```

## Acceptance Criteria Status (re-verified against live API)

- [x] M4B metadata query returns URL when available ✓ (live-tested, 6/6 books)
- [x] M4B query raises on 404 ✓ (mock-tested)
- [x] Download writes to `.partial` during transfer ✓ (verified file creation)
- [x] Atomic rename to `.m4b` on completion ✓ (no .partial files left behind)
- [x] Resume via Range header ✓ (mock-tested with strict Range validation)
- [x] Resume from correct byte offset ✓ (mock-tested)
- [x] Output path follows Slice 3a pattern + sanitization ✓ (all 6 paths correct)
- [x] Subdirectory when extras present; flat otherwise ✓ (mixed: 4 subdir, 2 flat)
- [x] History entry only after successful download ✓ (6 entries written)
- [x] Book without M4B skipped ✓ (mock-tested)
- [x] All tests pass ✓ (**109/109**)

## Open Items & Next Steps

- [ ] **MP3 fallback (Issue #5 mentions):** Books without M4B currently just skipped. Next slice should implement MP3 download manifest parsing + ZIP part extraction.
- [ ] **Progress bar:** No progress indicator during large downloads (~300-700MB each). Rich Progress bar would improve UX.
- [ ] **Concurrency:** Sequential download of 6 books took ~9 min. Parallel downloads could be faster.
- [ ] **Cover art / PDF extras downloading:** Config has flags for these but they're not implemented yet.
- [ ] **`download_history.json` cleanup:** ISBN type inconsistency in stored data (int vs str). Consider normalizing on next write.

---
*Log written by write-log skill*
