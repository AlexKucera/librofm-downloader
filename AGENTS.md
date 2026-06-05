# Agent Instructions

## Session Logs

Session logs are written to `docs/devlog/` after each completed task, issue fix, or milestone.
They capture what was done, decisions & rationale, gotchas & fixes, and next steps. Before starting a new session, read the previous session logs.

<!-- write-log: session-log-index -->
| Date | Type | File | Summary |
|------|------|------|---------|
| 2026-06-05 | issue | [20260605-issue44-sync-run-injectable-pipeline_log.md](docs/devlog/20260605-issue44-sync-run-injectable-pipeline_log.md) | **Issue #44 Complete:** Refactored `sync_run()` to injectable pipeline. 4 DI seams (session/history/reporter/download_fn), extracted 2 helpers (`_print_verbose_config`, `_resolve_history_path`), simplified closure. **+10 tests, 172 total** · **All pass** · **7/7 AC** |
| 2026-06-05 | issue | [20260605-issue43-test-reorganization-cleanup-pass_log.md](docs/devlog/20260605-issue43-test-reorganization-cleanup-pass_log.md) | **Issue #43 Complete:** Test reorganization cleanup. Deleted 13 dup path classes from downloader, moved 2 integration classes progress→sync_run, removed duplicate `TestParallelProgressCallbackWiring`, rescued orphaned method. **−470 net test lines, 374 tests** · **168/168 pass on modified files** · **5/5 AC** |
| 2026-06-05 | issue | [20260605-issue41-extract-stream-to-file-helper_log.md](docs/devlog/20260605-issue41-extract-stream-to-file-helper_log.md) | **Issue #41 Complete:** Extracted `_stream_to_file()` helper. 4 callers → thin wrappers (`download_m4b`, `download_zip_part`, `_download_cover`, `_download_pdf`). **5 new TDD tests, 224 total** · **All pass** · **6/8 AC** (line reduction −22, shy of 30–40 target) |
| 2026-06-05 | issue | [20260605-issue40-relocate-write-history-to-history_log.md](docs/devlog/20260605-issue40-relocate-write-history-to-history_log.md) | **Issue #40 Complete:** Relocated `_write_history()` from `downloader.py` → `history.py`. Updated all import sites. **+1 net test, ~430 total** · **All pass** · **5/5 AC** |
| 2026-06-05 | issue | [20260605-issue39-remove-cancel-event-from-reporters_log.md](docs/devlog/20260605-issue39-remove-cancel-event-from-reporters_log.md) | **Issue #39 Complete:** Removed `cancel_event` from both reporter classes. Explicit param on `download_book()`, closure capture in `sync_run.py`. **+5 net tests, ~429 total** · **All pass** · **6/6 AC** |
| 2026-06-05 | issue | [20260605-issue37-excise-client-py-dead-shim_log.md](docs/devlog/20260605-issue37-excise-client-py-dead-shim_log.md) | **Issue #37 Complete (Slice 1):** Excised `client.py` dead shim + `test_client.py`. Migrated 4 rate-limiter tests → `test_session.py`. **−337 lines dead code, 425→413 tests** · **All pass** · **6/6 AC** |
|------|------|------|---------|
| 2026-06-05 | issue | [20260605-issue35-integration-tests-rename-chapters-pipeline-wiring_log.md](docs/devlog/20260605-issue35-integration-tests-rename-chapters-pipeline-wiring_log.md) | **Issue #35 Complete (Slice 4):** Integration tests for rename_chapters pipeline wiring. AC#3 missing test + 4 edge cases (special chars, single-track, 105-chapter 3-digit padding). **4 new tests, ~233 total** · **All pass** · **6/6 AC** |
| 2026-06-05 | issue | [20260605-issue34-wire-rename-chapters-into-download-pipeline_log.md](docs/devlog/20260605-issue34-wire-rename-chapters-into-download-pipeline_log.md) | **Issue #34 Complete (Slice 3):** Wired `rename_chapters()` into download pipeline. `_download_mp3()` returns tuple with tracks, `download_book()` accepts `rename_chapters` kwarg, `_rename_and_log()` helper + user-visible reporter feedback. **6 new tests, ~229 total** · **All pass** · **8/8 AC** |
| 2026-06-05 | issue | [20260605-issue33-rename-chapters-config-field-and-cli-flag_log.md](docs/devlog/20260605-issue33-rename-chapters-config-field-and-cli-flag_log.md) | **Issue #33 Complete (Slice 2):** `rename_chapters` config field + `--rename-chapters` CLI flag. 2-layer resolution (CLI > config), defaults True. **5 new tests, 223 total** · **All pass** · **6/7 AC** (env var skipped per user choice) |
| 2026-06-05 | issue | [20260605-issue32-rename-chapters-function-and-unit-tests_log.md](docs/devlog/20260605-issue32-rename-chapters-function-and-unit-tests_log.md) | **Issue #32 Complete:** `rename_chapters()` function in `downloader.py`. Natural sort, zero-padding, null-title fallback, sanitization via existing `sanitize()`. **11 new tests, 106 in downloader** · **All pass** · **12/12 AC** |
| 2026-06-05 | issue | [20260605-issue31-sync-run-pipeline-and-cli-slimming_log.md](docs/devlog/20260605-issue31-sync-run-pipeline-and-cli-slimming_log.md) | **Issue #31 Complete:** Extracted `sync_run()` pipeline from `cli.run()` into standalone module. `SyncRunResult` frozen dataclass. `cli.py` slimmed 252→65 lines. **43 sync_run tests + 10 CLI tests, 374 total** · **All pass** · **7/8 AC (HITL pending)** |
| 2026-06-05 | issue | [20260605-issue30-download-reporting-bound-callable-per-book_log.md](docs/devlog/20260605-issue30-download-reporting-bound-callable-per-book_log.md) | **Issue #30 Complete:** Bound callable per book from `start_download()`. Task identity internal to `progress.py`. Orchestrator closure eliminated. **11 new tests, 382 total** · **All pass** · **6/6 AC** |
| 2026-06-04 | issue | [20260604-issue29-download-attempt-interface-shrink-to-4-params_log.md](docs/devlog/20260604-issue29-download-attempt-interface-shrink-to-4-params_log.md) | **Issue #29 Complete:** `download_book()` 9→4 domain-aligned params. `DownloadResult` frozen dataclass. History moved to caller. `OutputPlan.format_strategy` added. Cancel via reporter. **15 new TDD tests, 368 total** · **All pass** · **6/6 AC** |
| 2026-06-04 | issue | [20260604-issue28-output-plan-dataclass_log.md](docs/devlog/20260604-issue28-output-plan-dataclass_log.md) | **Issue #28 Complete:** `OutputPlan` frozen dataclass + `resolve_output_plan()`. Centralized all path computation; download functions consume plan fields. Eliminated duplicated audio-path code. **10 new TDD tests, 237 total** · **All pass** · **5/5 AC** |
| 2026-06-04 | issue | [20260604-issue27-librofm-session-constructor-injection-and-rename_log.md](docs/devlog/20260604-issue27-librofm-session-constructor-injection-and-rename_log.md) | **Issue #27 Complete:** `LibroFmClient` → `LibroFmSession`, relocated to `session.py`. Constructor transport injection, shared `httpx.Client`, auth headers assembled once. **17 new TDD tests, 244 total** · **227 pass (3 pre-existing hang)** · **6/6 AC** |
| 2026-06-04 | issue | [20260604-issue26-book-intake-module-bookpy-pathpy-extraction_log.md](docs/devlog/20260604-issue26-book-intake-module-bookpy-pathpy-extraction_log.md) | **Issue #26 Complete:** Book intake (`book.py`) + path logic (`path.py`) extraction from monolithic `downloader.py`. `Book` dataclass + `from_library_row()`, sanitize/resolve_path/needs_subdirectory. **79 new tests, 338 total** · All pass |
| 2026-06-04 | issue | [20260604-fix-parallel-progress-bar-task_id-not-wired-through-callback_log.md](docs/devlog/20260604-fix-parallel-progress-bar-task_id-not-wired-through-callback_log.md) | **Fix:** Parallel progress bars only updated one book — `task_id` never threaded from `start_download()` through to `update()` callback. Per-book closure binding in orchestrator. **3 new tests, 259 total** · **256/259 pass** (3 pre-existing Ctrl+C hang) |
| 2026-06-04 | issue | [20260604-fix-verbose-flag-not-wired-through-cli-entry-point_log.md](docs/devlog/20260604-fix-verbose-flag-not-wired-through-cli-entry-point_log.md) | **Fix:** `-v`/`--verbose` flag dead — argparse was in `__main__` guard, never reached by installed console script. Extracted `main()`, updated entry point. **247/247 tests pass** |
| 2026-06-04 | issue | [20260604-fix-ctrl-c-hangs-and-threading-traceback_log.md](docs/devlog/20260604-fix-ctrl-c-hangs-and-threading-traceback_log.md) | **Fix:** Ctrl+C hangs + threading traceback. `os._exit(130)` hard exit, no-wait cancellation, wired `cancel_event` through full download stack, fixed `books_with_index[idx][1]` bug. **256/256 tests pass** |
| 2026-06-04 | issue | [20260604-fix-keyboardinterrupt-handling-and-test-alignment_log.md](docs/devlog/20260604-fix-keyboardinterrupt-handling-and-test-alignment_log.md) | **Fix:** `except BaseException` in `_download_one`, cooperative cancellation framework, reporter lifecycle. **256/256 tests pass** |
| 2026-06-04 | issue | [20260604-issue22-xdg-config-path-resolution-with-cwd-fallback_log.md](docs/devlog/20260604-issue22-xdg-config-path-resolution-with-cwd-fallback_log.md) | **Issue #22 Complete:** XDG→CWD path resolution, `load_config(None, None)` search, missing-config notice, OS→domain error wrapping. **9 new tests, 181 total** · **8/8 AC** |
| 2026-06-03 | issue | [20260603-cli-parallel-integration-and-ctrl-c-drain-issue17_log.md](docs/devlog/20260603-cli-parallel-integration-and-ctrl-c-drain-issue17_log.md) | **Issue #17 Complete:** CLI parallel integration + graceful Ctrl+C drain. Orchestrator catches KeyboardInterrupt, drains in-flight downloads (shutdown(wait=True)), double-Ctrl+C fast exit. **13 new tests, 231 total** · **10/10 AC** |
| 2026-06-03 | issue | [20260603-parallel-download-orchestrator-issue16_log.md](docs/devlog/20260603-parallel-download-orchestrator-issue16_log.md) | **Issue #16 Complete:** `orchestrator.py` — `ThreadPoolExecutor` parallel download engine. Replaces sequential for-loop in cli.py. `OrchestratorResult` dataclass, stable-sort ordering, failure isolation. **20 new tests, 218 total** · **11/11 AC** |
| 2026-06-03 | issue | [20260603-api-rate-limiter-issue15_log.md](docs/devlog/20260603-api-rate-limiter-issue15_log.md) | **Issue #15 Complete:** `threading.Semaphore(3)` API rate limiter on `LibroFmClient`. Caps concurrent API calls; CDN downloads bypass. **4 new tests, 198 total** · **6/6 AC** |
| 2026-06-03 | issue | [20260603-multi-bar-progress-per-book-identity-mapping-issue14_log.md](docs/devlog/20260603-multi-bar-progress-per-book-identity-mapping-issue14_log.md) | **Issue #14 Complete:** Per-book identity mapping for concurrent progress bars. `_tasks`/`_book_ids` dicts, `start_download()` returns `task_id`, `update(task_id=)` targeting. **10 new tests, 194 total** · **7/7 AC** |
| 2026-06-03 | issue | [20260603-thread-safe-downloadhistory-write-issue13_log.md](docs/devlog/20260603-thread-safe-downloadhistory-write-issue13_log.md) | **Issue #13 Complete:** Thread-safe `DownloadHistory.write()` with `threading.Lock`. **5 new tests, 184 total** · **4/4 AC** |
| 2026-06-03 | issue | [20260603-slice-1-workers-config-and-cli-flag-issue12_log.md](docs/devlog/20260603-slice-1-workers-config-and-cli-flag-issue12_log.md) | **Issue #12 Complete:** `workers` config field + `-w`/`--workers` CLI flag with 3-layer resolution (CLI > config > 3). `InvalidWorkersError` validation. **6 new tests, 179 total** · **7/7 AC** |
| 2026-06-03 | issue | [20260603-issue10-documentation-site-and-readme_log.md](docs/devlog/20260603-issue10-documentation-site-and-readme_log.md) | **Issue #10 Complete:** MkDocs site (8 pages) + polished README. Material theme, flat URLs. **11/11 AC** · **172 tests pass** |
| 2026-06-03 | slice | [20260603-slice-6b-summary-exit-codes-and-integration-tests-issue9_log.md](docs/devlog/20260603-slice-6b-summary-exit-codes-and-integration-tests-issue9_log.md) | **Issue #9 Complete:** Enhanced summary (failed/skipped book details) + graceful Ctrl+C (exit 130) + 3 integration tests. **12 new tests, 168 total** · **15/15 AC** |
| 2026-06-03 | issue | [20260603-output-polish-progress-bars-and-failure-isolation-issue8_log.md](docs/devlog/20260603-output-polish-progress-bars-and-failure-isolation-issue8_log.md) | **Issue #8 Complete:** TTY-aware download reporting — rich progress bars (interactive) + plain log lines (cron). Per-book failure isolation. Content-Length → live %/ETA/speed. **18 new tests, 156 total** · **8/8 AC** |
| 2026-06-03 | slice | [20260603-slice-5-accompanying-files-and-output-structure-issue7_log.md](docs/devlog/20260603-slice-5-accompanying-files-and-output-structure-issue7_log.md) | **Issue #7 Complete:** PDF extras + cover art download with config toggles, .partial→atomic rename, non-critical failure handling, output structure verification. **12 new tests, 134 total** · **11/11 AC** |
| 2026-06-03 | slice | [20260603-slice-6-mp3-fallback-issue6_log.md](docs/devlog/20260603-slice-6-mp3-fallback-issue6_log.md) | **Issue #6 Complete:** MP3 fallback pipeline — manifest fetch, ZIP download+extract+resume, format strategy selector (m4b_mp3_fallback/mp3_only/m4b_only), `--limit` CLI flag. **12 new tests, 122 total** · **11/11 AC** |
| 2026-06-03 | issue | [20260603-slice-3b-live-testing-fixes-issue5_log.md](docs/devlog/20260603-slice-3b-live-testing-fixes-issue5_log.md) | **Issue #5 Live Fixes:** 4 critical API-shape bugs found & fixed (audiobooks key, m4b_url key, nested narrators, ISBN int/str). Download loop wired. `--verbose` flag. **109 tests**, 6 books downloaded (~2.9 GB) · **11/11 AC** |
| 2026-06-03 | slice | [20260603-slice-3b-m4b-download-pipeline-issue5_log.md](docs/devlog/20260603-slice-3b-m4b-download-pipeline-issue5_log.md) | **Issue #5 TDD:** M4B download pipeline — client endpoint, streaming downloader with resume, path integration, history post-download, CLI orchestration. 11 new tests, **108 total** · **11/11 AC** |
| 2026-06-03 | slice | [20260603-slice-3a-path-resolution-and-sanitization-issue4_log.md](docs/devlog/20260603-slice-3a-path-resolution-and-sanitization-issue4_log.md) | **Issue #4 Complete:** Path resolution + sanitization + Book model + custom patterns. 56 new tests, **97 total** · **16/16 AC** |
| 2026-06-03 | issue | [20260603-fix-path-doubling-and-cover-download-issue_log.md](docs/devlog/20260603-fix-path-doubling-and-cover-download-issue_log.md) | **Path doubling fix:** `needs_subdirectory()` no longer triggered by always-present `cover_url`, title no longer double-appended in `_resolve_output_dir()`, cover download fixed (headers + protocol-relative URLs). **172/172 tests** |
| 2026-06-03 | issue | [20260603-project-scaffolding-and-config-module-issue2_log.md](docs/devlog/20260603-project-scaffolding-and-config-module-issue2_log.md) | **Issue #2 Complete:** pyproject.toml + venv + config module (load/merge/validate) + 25 tests. 11/11 AC met |

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **librofm-downloader** (2023 symbols, 3834 relationships, 13 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/librofm-downloader/context` | Codebase overview, check index freshness |
| `gitnexus://repo/librofm-downloader/clusters` | All functional areas |
| `gitnexus://repo/librofm-downloader/processes` | All execution flows |
| `gitnexus://repo/librofm-downloader/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
