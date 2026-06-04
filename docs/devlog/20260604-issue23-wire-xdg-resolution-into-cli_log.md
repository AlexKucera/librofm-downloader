# Issue #23: Wire XDG Path Resolution into CLI Layer

> **Date:** 2026-06-04
> **Type:** issue
> **Reference:** [GitHub #23](https://github.com/AlexKucera/librofm-downloader/issues/23) · Parent [#21](https://github.com/AlexKucera/librofm-downloader/issues/21)

## Goal

Wire the path resolver from Issue #22 into the CLI layer so that running `librofm-downloader` with no flags finds config/secrets/history via XDG→CWD search. History path defaults to XDG location. Missing config prints searched paths. Verbose mode shows resolved file locations. Explicit CLI flags bypass search entirely.

## What Was Done

- Changed `run()` parameter `history_path` default from `"download_history.json"` to `None` so the resolver activates
- Added history path resolution block in `run()`: calls `_resolve_config_file("download_history.json")` (XDG→CWD search); falls back to `~/.config/librofm-downloader/download_history.json` if not found anywhere
- Imported `_resolve_config_file` from `config.py` into `cli.py`
- Enhanced missing-config message to list searched paths: `"config.yaml not found in ~/.config/librofm-downloader/config.yaml → ./config.yaml. Using built-in defaults."`
- Added verbose resolved-paths display after config load showing `config`, `secrets`, `history` with actual resolved filesystem paths (not input args)
- Changed argparse `--history` default from `"download_history.json"` to `None` with updated help text
- 7 new tests across 3 test classes: `TestCLIHistoryResolution` (3), `TestCLIConfigResolutionMessages` (2), `TestCLIMissingFilesErrors` (2)
- **188 tests pass** (was 181 → +7 new)
- **All 10 acceptance criteria met**

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| History resolves before config load | History path is needed by `DownloadHistory.__init__()`, which happens before downloads; resolving early avoids expanding `load_config`'s responsibility |
| History defaults to XDG location (not CWD) when not found | Consistent with XDG-first resolution strategy; CWD is only a read fallback, not a default-write location |
| Verbose block moved to after config load | The actual resolved paths aren't known until after `load_config` runs and `_resolve_config_file` has been called; showing paths before resolution would display `None` |
| `_resolve_config_file` reused for history | Same XDG→CWD search logic; no need for a separate history resolver |
| Verbose re-calls `_resolve_config_file` for secrets display | At that point `secrets_path` is already consumed by `load_config`; re-resolving is cheap (two `is_file()` checks) and avoids threading the resolved path through |

## Gotchas & Fixes

*None* — all 7 vertical slices passed cleanly on first implementation attempt. No test failures requiring iteration.

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/cli.py` | `history_path` default → `None`; XDG resolution for history path; verbose resolved-paths display; argparse `--history` default → `None`; enhanced missing-config message with searched paths; imported `_resolve_config_file` |
| `tests/test_cli.py` | 7 new tests: `TestCLIHistoryResolution` (3), `TestCLIConfigResolutionMessages` (2), `TestCLIMissingFilesErrors` (2) |

## Open Items & Next Steps

- [ ] Update CLI `--help` text to mention XDG search behavior for `--history`
- [ ] Update README/docs to document XDG config location and history defaults
- [ ] GitNexus index needs rebuild (`npx gitnexus analyze`) after these changes

---

*Log written by write-log skill*
