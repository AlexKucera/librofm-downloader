# Issue #33: Config field, CLI flag for rename_chapters (Slice 2)

> **Date:** 2026-06-05
> **Type:** issue
> **Reference:** [Issue #33](https://github.com/AlexKucera/librofm-downloader/issues/33) — Slice 2 of parent Issue #19

## Goal

Add `rename_chapters` configuration following the exact same pattern as the existing `download_extras` and `download_covers` boolean toggles. Users can control chapter renaming via two layers (CLI > config file), both defaulting to enabled (`True`). The `Config` dataclass gains a new field; YAML config and CLI argparse respect it. This is plumbing only — wiring into the actual download pipeline is Slice 3.

## What Was Done

- **Config dataclass** (`librofm_downloader/config.py`): Added `rename_chapters: bool` field to frozen `Config` dataclass (line 19). No dataclass default — always set by `load_config()`.
- **Config loader**: Added `rename_chapters=librofm.get("rename_chapters", True)` in `load_config()` return (line 143). Defaults to `True`.
- **CLI argparse** (`librofm_downloader/cli.py`): Added `--rename-chapters` flag with `action="store_true"`, `default=False`. Threaded through `run()` signature → `sync_run()` call.
- **sync_run() threading** (`librofm_downloader/sync_run.py`): Added `rename_chapters: bool = False` parameter. Resolution logic: `resolved_rename_chapters = rename_chapters or config.rename_chapters` (CLI True forces enable; absent defers to config). Verbose display line added (`chapters:` alongside extras/covers).
- **YAML fixture** (`tests/fixtures/config_with_overrides.yaml`): Added `rename_chapters: false` line.
- **Existing test fixes** (`tests/test_downloader.py`): Updated 7 direct `Config()` constructor calls to include new required `rename_chapters=True` argument.

### TDD Cycles

| Cycle | Test | Implementation |
|-------|------|----------------|
| 1 | `test_default_rename_chapters_is_true` — minimal YAML → `True` | Add field to Config + `.get("rename_chapters", True)` in load_config |
| 2 | `test_explicit_false_for_rename_chapters` — overrides YAML has `false` | GREEN immediately (dict get already handles it); added `rename_chapters: false` to fixture |
| 3 | `test_rename_chapters_flag_default` + `test_rename_chapters_flag` — argparse passthrough | Added `--rename-chapters` to argparse, threaded through `run()` → `sync_run()` |
| 4 | `test_cli_rename_chapters_overrides_config_false` — sync_run resolution | Resolution logic: `rename_chapters or config.rename_chapters` |

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| No env var support | User chose config + CLI only, matching existing `download_extras`/`download_covers` which are YAML-only. Avoids establishing a new pattern no other field uses yet. |
| One-way `--rename-chapters` (`store_true`) instead of paired `--flag/--no-flag` | User wanted: flag present = force-enable; absent = defer to config. Simpler than BooleanOptionalAction, consistent with existing one-way flags like `--verbose`. |
| Sentinel-like resolution (`or` pattern) vs workers sentinel (`0` meaning "use config") | Bool is simpler: `False` = not set, `True` = force on. The `or` pattern works cleanly: `rename_chapters or config.rename_chapters`. |
| Field threaded as individual param through `sync_run()` (not just closure-captured config) | Follows the `workers` precedent — makes the override explicit and testable. The resolved value is available for slice 3 pipeline wiring. |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| 7 tests in `test_downloader.py` failed with `TypeError: __init__() missing 'rename_chapters'` | Existing tests construct `Config(...)` directly with positional/keyword args — adding a new required field breaks them | Added `rename_chapters=True` to all 7 direct `Config()` calls in `test_downloader.py` |
| `resolved_rename_chapters` computed but NOT consumed in download pipeline | By design — this is slice 2 (plumbing only). The `rename_chapters()` function exists in `downloader.py` but is never called from the pipeline. That's slice 3 (next issue). | N/A — documented as open item |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/config.py` | Added `rename_chapters: bool` to Config dataclass; `load_config()` reads from merged dict with default `True` |
| `librofm_downloader/cli.py` | Added `--rename-chapters` argparse arg (`store_true`); threaded `rename_chapters` param through `run()` → `sync_run()` |
| `librofm_downloader/sync_run.py` | Added `rename_chapters: bool = False` param; resolution logic; verbose display line |
| `tests/test_config.py` | 2 new tests: default True, explicit False from YAML |
| `tests/test_cli.py` | 2 new tests: flag default=False, flag=True passthrough |
| `tests/test_sync_run.py` | 1 new test: CLI override of config=False |
| `tests/fixtures/config_with_overrides.yaml` | Added `rename_chapters: false` |
| `tests/test_downloader.py` | 7 existing `Config()` calls updated with `rename_chapters=True` |

## Acceptance Criteria Status

| # | Criterion | Status |
|---|-----------|--------|
| 1 | `Config.rename_chapters` defaults to `True` | ✅ PASS |
| 2 | `rename_chapters: false` in config.yaml produces `Config(rename_chapters=False)` | ✅ PASS |
| 3 | `RENAME_CHAPTERS=false` env var overrides config value | ⏭️ Skipped (user chose config+CLI only) |
| 4 | `--rename-chapters` CLI flag overrides both config and env var | ✅ PASS |
| 5 | `--rename-chapters` CLI flag explicitly enables it | ✅ PASS |
| 6 | Field threaded through `sync_run()` → `_download_fn` closure → ready for pipeline use | ✅ PASS |
| 7 | ~4 tests for config defaults, YAML reading, and CLI override | ✅ PASS (**5 new tests**) |

**Test count: 223 total, all passing** (up from 218 before this issue).

## Open Items & Next Steps

- [ ] **Slice 3 (next issue):** Wire `resolved_rename_chapters` into the download pipeline so `rename_chapters()` in `downloader.py` is actually called after MP3 extraction. Currently the function exists but is never invoked.
- [ ] Consider adding verbose log line when renaming occurs: `"renaming mp3 chapter files… (<example>)"` — user requested visibility into whether renaming happened.
- [ ] When slice 3 is done, add integration test that downloads an MP3-format book with `rename_chapters=True` and verifies output filenames contain chapter titles.

---

*Log written by write-log skill*
