# Issue #12: Slice 1 — Config `workers` field + CLI `--workers` flag

**Date:** 2026-06-03
**Type:** issue
**Status:** Complete

## Summary

Added parallel download worker-count configuration through all three config layers (YAML → Config dataclass → CLI → resolution). Follows the existing pattern established by `format`/`InvalidFormatError` and `--limit`.

## What Was Done

### config.py changes
- Added `workers: int = 3` field to frozen `Config` dataclass (default 3, backward-compatible)
- Added `InvalidWorkersError(ConfigError)` subclass for validation failures
- Added `_validate_workers()` function — rejects non-int and values < 1
- Wired validation into `load_config()` — only validates when `workers` key is explicitly present in YAML
- Parses `librofm.workers` from merged YAML dict with fallback to `3`

### cli.py changes
- Added `-w`/`--workers` argument to argparse (`type=int`, `metavar="N"`, `default=0`)
- Added `workers: int = 0` parameter to `run()` function
- Implemented 3-layer resolution in `run()`: CLI flag (>0?) → `config.workers` → hardcoded `3`
- Stored as `resolved_workers` variable (for slice 6 to wire to orchestrator)
- Updated docstring with new parameter

### Test changes (6 new tests, 179 total)
- **test_config.py** — 3 new tests:
  - `TestWorkersDefault::test_default_workers_is_3` — absent from YAML → defaults to 3
  - `TestWorkersFromYaml::test_workers_5_from_yaml` — `workers: 5` in YAML parsed correctly
  - `TestWorkersValidation::test_workers_zero_raises_error` — `workers: 0` raises `InvalidWorkersError`
  - `TestWorkersValidation::test_workers_negative_raises_error` — `workers: -1` raises `InvalidWorkersError`
- **test_cli.py** — 3 new tests:
  - `TestCLIWorkersFlag::test_cli_workers_overrides_config` — `--workers 8` overrides config.workers=3
  - `TestCLIWorkersFlag::test_no_flag_uses_config_value` — no flag uses config value (5)
  - `TestCLIWorkersFlag::test_workers_1_accepted` — `--workers 1` accepted (sequential)

### Fixture files added
- `tests/fixtures/config_workers_zero.yaml` — workers: 0 (invalid)
- `tests/fixtures/config_workers_negative.yaml` — workers: -1 (invalid)
- Updated `config_with_overrides.yaml` — added `workers: 5`

### Existing test fixes
- Updated ~15 existing tests across `test_cli.py`, `test_progress.py` that mock `load_config` to include `mock_config.return_value.workers = 3`
- No logic changes needed — `Config.workers = 3` default made all direct `Config(...)` constructions backward-compatible

## Decisions & Rationale

1. **Default on dataclass, not just in loader**: Gave `workers` a default of `3` in the `Config` dataclass itself so existing tests that construct `Config(...)` directly don't break. This is more defensive than requiring every caller to pass it.

2. **Validate only when explicit**: Only call `_validate_workers()` when the `workers` key is present in YAML. This means omitting it silently gets the default (3), which is the desired behavior per the AC.

3. **CLI default=0 as sentinel**: Used `0` as the "not specified" sentinel for the CLI flag (matching the `--limit` pattern). The resolution logic checks `> 0` before using the CLI value.

4. **Store resolved value now**: Even though slice 6 wires it to the orchestrator, storing `resolved_workers` in `run()` makes it visible for debugging and avoids another refactor pass.

## Gotchas & Fixes

- **MagicMock comparison error**: Adding a new field to `Config` broke ~15 existing tests that mock `load_config()` because `MagicMock` can't be compared with `<` operator. Fixed by adding `workers=3` to all mock configs.
- **Duplicate docstring**: The initial edit to add `workers` to the docstring created a duplicate. Fixed by removing the old docstring fragment.
- **Edit anchor format**: Multi-line anchors don't work with `set_line`. Had to use single-line anchors.

## Next Steps

- **Slice 6** will wire `resolved_workers` to the parallel download orchestrator
- Consider adding `workers` to verbose output display

## Acceptance Criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | `Config.workers` defaults to `3` | ✅ |
| 2 | `workers: 5` in config.yaml produces `Config(workers=5)` | ✅ |
| 3 | `workers: 0` or `workers: -1` in YAML raises `InvalidWorkersError` | ✅ |
| 4 | `--workers 8` on CLI resolves to 8 regardless of config.yaml value | ✅ |
| 5 | No `--workers` flag uses config.yaml value; missing from both yields default 3 | ✅ |
| 6 | `--workers 1` is accepted (sequential fallback) | ✅ |
| 7 | 3–4 new tests in `test_config.py` covering default, YAML parse, validation rejection, CLI resolution | ✅ (6 new) |

**All 7/7 AC met • 179 tests pass**
