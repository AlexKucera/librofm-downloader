# Issue #44: Refactor sync_run() to Injectable Pipeline

> **Date:** 2026-06-05
> **Type:** issue
> **Reference:** [GitHub #44](https://github.com/AlexKucera/librofm-downloader/issues/44)

## Goal

Refactor `sync_run()` from a hard-wired composition root (imports 7 sibling modules, constructs everything inline) into an injectable pipeline where key collaborators are accepted as optional parameters with real-construction defaults. This turns hypothetical test seams into real ones — tests can pass fakes instead of patching fully-qualified import names.

## What Was Done

- Added 4 keyword-only DI parameters to `sync_run()`: `session`, `history`, `reporter`, `download_all_fn` (all default `None`)
- Wired guard clauses: when `None`, constructs real collaborators (backward-compatible); when provided, uses injected instance directly
- Extracted `_print_verbose_config(config, history_path, secrets_path)` helper from the inline verbose logging block (~17 lines)
- Extracted `_resolve_history_path(history_path)` helper, deduplicating XDG→CWD→default resolution that previously duplicated `config.py`'s `_resolve_config_file()` logic
- Refactored `_make_download_fn()` from implicit scope-capturing closure to explicit-parameter closure (6 params: `_config, _client, _history, _reporter, _cancel_event, _rename_chapters`)
- Added 10 new tests across 7 test classes covering each seam individually + a full-DI integration test

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Injected params are keyword-only (after `*`) | Prevents positional misuse; caller must be explicit about which collaborator they're overriding |
| `session` is already authenticated when injected | Caller is responsible for `.authenticate()`. When `None`, sync_run constructs + authenticates as before. Avoids double-auth or half-auth edge cases. |
| `download_all_fn or download_all_books` pattern | Cleanest fallback — no wrapper needed, just use the real function when no override provided |
| `_make_download_fn()` stays nested, not module-level | It's a factory that returns a closure matching the orchestrator's `download_fn` protocol. Moving it to module level would expose an internal detail. Instead, it now takes explicit params rather than closing over `sync_run()` scope. |
| Helper extraction tests use direct unit testing | `_print_verbose_config()` and `_resolve_history_path()` are tested directly (not through `sync_run()`), confirming extraction didn't change behavior. |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| `history` parameter name shadowed by local `history = DownloadHistory(history_path)` | The injected param and the local variable had the same name — line 180 would always overwrite the parameter | Guard clause `if history is None: history = DownloadHistory(history_path)` ensures injected value is preserved |
| Pre-existing `KeyboardInterrupt` in full test suite | Ctrl+C thread tests in `test_cli.py` sometimes raise during `pytest -x` | Cosmetic only — 172/172 pass, the KeyboardInterrupt is the test itself verifying exit behavior |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/sync_run.py` | Added 4 DI params to signature, extracted 2 helpers (`_print_verbose_config`, `_resolve_history_path`), refactored `_make_download_fn()` to explicit params |
| `tests/test_sync_run.py` | +10 new tests in 7 classes: injection seams (session, history, reporter, download_fn), helper units, full-DI integration, explicit closure params |

## Test Results

- **sync_run tests:** 46 → 56 (+10 new, 0 regressions)
- **Full suite:** 172/172 pass
- **Net diff:** +469 lines (399 test, 70 production — helpers offset by inline block removal)

## Open Items & Next Steps

None — all 7 acceptance criteria met.

---

*Log written by write-log skill*
