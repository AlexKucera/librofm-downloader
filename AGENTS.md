# Agent Instructions

## Session Logs

Session logs are written to `docs/devlog/` after each completed task, issue fix, or milestone.
They capture what was done, decisions & rationale, gotchas & fixes, and next steps. Before starting a new session, read the previous session logs.

<!-- write-log: session-log-index -->
| Date | Type | File | Summary |
|------|------|------|---------|
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

This project is indexed by GitNexus as **librofm-downloader** (997 symbols, 1770 relationships, 10 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

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
