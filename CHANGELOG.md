# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] - 2026-06-06

### Added

- **selector:** Add interactive book selection module `selector.py` with
  `select_books()` (questionary checkbox prompt, confirmation summary) and
  `_format_row()` helper. Uses `unsafe_ask()` for Ctrl+C propagation.
  Row format: `N. Title — Author [Series #N]`.
  9 tests. Closes #47.
- **sync_run:** Wire `--select` into download pipeline. TTY guard
  (non-interactive terminals get error exit 1), dict→Book conversion
  via `from_library_row()`, selected Books pass to orchestrator
  without double-conversion, `--limit` bypassed with notice.
  6 integration tests. Closes #48.

### Fixed

- **sync_run:** Show --limit-superseded notice unconditionally when
  `--select` is active. Previously the message was gated behind
  `--verbose`, so non-verbose users had no indication their flag
  was silently ignored.
- **sync_run:** Check stdin (not stdout) for TTY guard, fixing the
  interactive selection check in non-interactive environments.

## [1.3.0] - 2026-06-06

### Added

- **downloader:** Add `rename_chapters()` function to rename extracted MP3
  files with chapter titles from the download manifest. Natural sort by
  numeric prefix, auto zero-padding, null/blank title fallback, sanitization
  via existing `sanitize()`. 11 tests. Closes #32.
- **config:** Add `rename_chapters` boolean field to Config dataclass with default
  `True`. Read from YAML config, threaded through CLI (`--rename-chapters` flag)
  and `sync_run()` resolution (CLI True → config value). 5 new tests, 223 total.
  Closes #33.
- **downloader:** Wire `rename_chapters()` into download pipeline.
  `_download_mp3()` returns `(output_dir, tracks)` tuple; `download_book()`
  accepts `rename_chapters` kwarg; new `_rename_and_log()` helper calls rename
  and reports via `reporter.chapter_renamed()`. Both reporters show visible
  feedback: "Renamed N chapter(s) for 'Book' → 'example.mp3'".
  `sync_run.py` closure threads resolved flag through to `download_book()`.
  6 new integration tests, ~229 total. Closes #34.
- **downloader:** Integration tests for rename_chapters pipeline wiring.
  Edge cases: special chars, single-track, 105-chapter 3-digit padding.
  Closes #35.

### Fixed

- **downloader:** Fix progress bar exceeding 100% on resumed downloads.
  `Content-Length` from a Range response covers only remaining bytes;
  now adds `resume_from` for the true total.
- **downloader:** Fix missing `Callable` import in module scope.
- **session:** Stop reaching into `httpx.Client._transport` (private API).
  Transport reference is now stored at construction time.

### Refactored

- **cancel:** Thread `cancel_event` explicitly through parameter chain
  (`sync_run` → `download_book()` → streaming calls) instead of stashing
  it on reporter objects as shared state. Remove `cancel_event` attribute from
  both `PlainTextReporter` and `ProgressReporter`. 429 tests (+5 net).
  Closes #39.
- **session:** Expose public `transport` property on `LibroFmSession` returning
  the underlying httpx transport. Update sole call site in `downloader.py` from
  `session._client._transport` to `session.transport`. 2 new tests, 425 total.
  Closes #38.
- **downloader:** Extract `_stream_to_file()` private helper from the
  duplicated ~30-line chunked-download loop in `download_m4b()`,
  `download_zip_part()`, `_download_cover()`, and `_download_pdf()`. All
  four callers are now thin wrappers that delegate streaming to the
  shared helper. 5 new TDD tests (fresh download, resume, cancel
  mid-stream, progress callback, error propagation). 224 total tests.
  Net -22 lines in downloader.py. Closes #41.
- **downloader:** Extract `_finalize_download()` from format-specific branches
  to consolidate post-download logic into a single helper.
- **session:** Rename LibroFmClient → LibroFmSession, relocate to
  session.py, inject transport at construction time. Old client.py is now
  a deprecated re-export shim. Endpoint signatures slimmed from 4-5 params
  to ≤3 (transport removed). 227 tests pass (+17 new). Closes #27.
- **path:** Introduce OutputPlan frozen dataclass and resolve_output_plan()
  function to centralize all path computation for a book. Download functions
  now consume pre-resolved plan fields instead of computing paths inline,
  eliminating duplicated audio-filename logic. 237 tests pass (+10 new).
  Closes #28.
- **downloader:** Shrink download_book() from 9 parameters to 4
  domain-aligned params (book, session, plan, reporter) returning a frozen
  DownloadResult dataclass. Move history writing to caller (cli closure).
  Add format_strategy to OutputPlan, wire cancel_event through reporter,
  extract transport from session. Remove config from accompanying_files.
  368 tests pass (+15 new). Closes #29.
- **progress:** Return bound callable from start_download() instead of raw
  task_id. Task identity is fully internal to progress.py. Orchestrator
  no longer creates per-book closures — passes the bound callback
  directly. download_book() accepts optional progress= kwarg. Public
  update() drops task_id param. 382 tests pass (+11 new). Closes #30.
- **cli/sync-run:** Extract entire download pipeline from cli.run() into
  standalone sync_run() function in new sync_run.py module. Introduce
  SyncRunResult frozen dataclass (replaces OrchestratorResult as public
  return type). Slim cli.py from 252→65 lines to a thin argparse→exit
  adapter that only patches sync_run(). Migrate 35 pipeline tests from
  test_cli.py to test_sync_run.py (43 total + 10 CLI-only tests).
  Add select_mode stub (ADR #6 branch point) and fatal_error field for
  exit-code translation. 374 tests pass. Closes #31.
- **sync-run:** Refactored `sync_run()` to injectable pipeline. 4 DI seams
  (session/history/reporter/download_fn), extracted 2 helpers
  (`_print_verbose_config`, `_resolve_history_path`), simplified closure.
  +10 tests. Closes #44.
- **sync-run:** Consolidated `SyncRunResult`/`OrchestratorResult` via
  composition. `SyncRunResult` wraps `OrchestratorResult` + 6 delegating
  properties. Bridge copy code eliminated. +2 tests. Closes #45.
- **history:** Relocate `_write_history()` from `downloader.py` → `history.py`.
  Updated all import sites. +1 net test. Closes #40.
- **tests:** Reorganize test files to match production modules. Deleted 13
  duplicate path classes, moved 2 integration classes, removed duplicate
  `TestParallelProgressCallbackWiring`, rescued orphaned method. −470 net
  test lines, 374 tests. Closes #43.
- **book:** Extract Book dataclass + `from_library_row()` and path logic
  (`sanitize`, `resolve_path`, `needs_subdirectory`) from monolithic
  `downloader.py` into `book.py` and `path.py`. 79 new tests. Closes #26.

## [1.2.0] - 2026-06-04

### Added

- **config:** Parallel download worker count: `workers` field on Config dataclass
  (default 3), `InvalidWorkersError` validation for values < 1, YAML parsing
  from `librofm.workers`, and `-w`/`--workers` CLI flag with three-layer
  resolution (CLI > config > default). 6 new tests (179 total). Closes #12.
- **progress:** Per-book identity mapping for concurrent progress bars:
  replace singleton `_current_task`/`_current_book` with bidirectional
  `_tasks`/`_book_ids` dicts keyed by `id(book)`. `start_download()` now
  returns `task_id`, `update()` accepts optional `task_id` kwarg with
  backward-compat fallback to most-recent task. `complete()`/`fail()`
  clean up both mappings. PlainTextReporter unchanged (already stateless).
  10 new tests (194 total). Closes #14.
- **api:** Rate limit concurrent Libro.fm API calls with `threading.Semaphore(3)`.
  CDN downloads bypass the limiter. 4 new tests (198 total). Closes #15.
- **orchestrator:** ThreadPoolExecutor-based parallel download engine:
  `download_all_books()` replaces sequential for-loop in cli.py, submitting all
  books as futures with per-future failure isolation. Returns `OrchestratorResult`
  dataclass with stable-sorted counts, failed_books as (Book, reason) tuples,
  and skipped_books as Book objects. `_raw_to_book()` conversion extracted from
  cli.py. 20 new tests (218 total). Closes #16.
- **orchestrator:** Graceful Ctrl+C drain during parallel downloads:
  first interrupt prints "Aborting...", drains in-flight downloads via
  `executor.shutdown(wait=True)`, then re-raises for exit code 130; second
  interrupt during drain force-quits immediately with
  `shutdown(cancel_futures=True)`. 13 new integration tests covering
  workers=1 regression parity, concurrent execution proof, summary ordering,
  failure isolation, verbose overlap safety, double-Ctrl+C fast exit, and
  partial file resume-safety after interrupt (231 total). Closes #17.
- **docs:** Update all documentation for parallel downloads. Closes #18.

### Fixed

- **history:** Make `DownloadHistory.write()` thread-safe with
  `threading.Lock` so concurrent worker threads don't corrupt or lose
  history entries during parallel downloads. Lock guards both in-memory
  mutation and disk flush. 5 new tests (184 total). Closes #13.
- **progress:** Wire task_id through parallel progress callback.
  All concurrent download updates went to the same (most recently started) bar
  because `task_id` was never threaded from `start_download()` to `update()`.
  Create per-book closure in orchestrator that binds `task_id`, pass through
  `cli._download_fn` as optional kwarg. 3 new regression tests. 259 total.
- **orchestrator:** Fix Ctrl+C hangs and threading shutdown traceback.
  Python threads cannot be killed when blocked in HTTP I/O; previous approach
  of `shutdown(wait=True)` caused infinite hangs. Now uses `os._exit(130)`
  hard exit after printing summary, marks unfinished books as cancelled, and
  bypasses Python's thread-pool cleanup entirely. Wires `cancel_event`
  through full download stack (cli → orchestrator → download_book → download_m4b).
  Fixes `books_with_index[idx][0]` bug that returned int index instead of Book
  object in post-interrupt collection. 256 tests pass.
- **cli:** Remove redundant per-book verbose print in parallel download loop.
  Progress bars already show author+title; the extra `⬇ title`/authors/narrators
  block caused a triple-display (bars → details → live progress). 247 tests pass.
- **cli:** Extract `main()` so argparse runs for installed console script.
  `-v`/`--verbose` was dead because the entry point called `run()`
  directly, bypassing the `if __name__ == "__main__"` argparse block.

## [1.1.0] - 2026-06-04

### Added

- **config:** XDG config path resolution with CWD fallback.
  `_resolve_config_file()` searches `~/.config/librofm-downloader/` then CWD.
  `load_config(None, None)` triggers search; missing config.yaml is non-fatal
  (prints notice, uses built-in defaults); missing secrets.yaml raises
  domain error listing searched paths. All OS exceptions wrapped as
  `ConfigError`. XDG directory auto-created on demand. Closes #22.
- **cli:** Wire XDG path resolution into CLI layer.
  History path defaults to `None` (resolves XDG → CWD, falls back to XDG
  location). Missing config message now lists searched paths. `--verbose`
  shows resolved file paths for config, secrets, and history. Explicit
  `--config`/`--secrets`/`--history` flags bypass search. Clean exit 1
  with no traceback when secrets missing from all locations. Closes #23.

### Documentation

- Update all documentation for XDG path resolution.
  configuration.md: new "Default file locations" section with search order,
  auto-creation, missing-config vs missing-secrets behavior, CLI flag
  overrides, validation error table with "not found" messages, and
  history default location. quickstart.md, cli-usage.md, troubleshooting.md,
  and README.md updated to reference XDG-first search. Closes #24.

## [1.0.0] - 2026-06-03

### Added

- Project scaffolding: pyproject.toml, package structure, test suite,
  config module with YAML loading, secrets deep-merge, validation, and
  defaults. Closes #2.
- OAuth2 client with password grant auth and paginated library fetch.
  Download history tracking with corrupt JSON recovery. Closes #3.
- Path resolution with default conditional patterns and custom token
  substitution. Filesystem-safe component sanitization (illegal chars,
  control chars, colons). Immutable Book dataclass for typed book metadata.
  Subdirectory decision logic based on PDF extras or cover art presence.
  Closes #4.
- M4B download pipeline: streaming chunked download with .partial files,
  atomic rename to .m4b, resume support via HTTP Range header.
  Closes #5.
- MP3 format fallback: download manifest fetch, ZIP part download+extraction
  with .partial tracking and resume, format strategy selector
  (m4b_mp3_fallback, mp3_only, m4b_only), and `--limit` CLI flag for
  capped downloads. Closes #6.
- PDF extras and cover art download: `fetch_pdf_extra_url()` client
  endpoint, `download_accompanying_files()` with config toggles
  (`download_extras`, `download_covers`), streaming .partial → atomic
  rename pattern, non-critical failure handling (warnings only), and
  output structure verification (subdirectory vs flat layout).
  12 new tests. Closes #7.
- TTY-aware download reporting: rich progress bars with live %/ETA/speed/
  file size for interactive terminals, plain log lines for pipes/cron,
  Content-Length-driven total so percentage works from first chunk,
  per-book failure isolation (one failed book doesn't stop batch),
  and fatal error immediate-exit before download loop starts.
  18 new tests. Closes #8.
- Enhanced summary: failed books listed with ISBN/title/reason, skipped
  books listed with ISBN/title; both plain-text and rich/TTY reporters.
  Graceful Ctrl+C handling: clean shutdown message instead of traceback,
  exit code 130 (standard Unix SIGINT convention). 3 integration tests.
  Closes #9.
- MkDocs documentation site with 8 pages — Quickstart, Configuration
  Reference, Secrets, Path Patterns, Format Strategies, CLI Usage, and
  Troubleshooting. Material theme, flat URLs, all code snippets verified
  against implementation. Polished README with badges, features table,
  format comparison, and project comparison note. Closes #10.

### Fixed

- **downloader:** Path doubling: `resolve_path()` returns Author/Title but code
  appended title again, producing nested folders like Title/Title/Title.m4b.
  Also fix cover download: add Libro.fm headers to httpx client, normalize
  protocol-relative URLs (//cdn → https://cdn).
- Library endpoint key mismatch: API returns "audiobooks" not "books".
- M4B endpoint key mismatch: API returns "m4b_url" not "url".
- Narrators nested under `audiobook_info.narrators` in API response.
- ISBN type mismatch in history lookup: JSON keys are strings but API
  returns ISBN as integer — added str() coercion in find/is_downloaded.
- Missing download loop in CLI run() function (listed books but never downloaded).
