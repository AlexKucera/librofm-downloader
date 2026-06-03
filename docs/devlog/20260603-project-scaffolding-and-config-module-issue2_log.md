# Project Scaffolding & Config Module (Issue #2)

> **Date:** 2026-06-03
> **Type:** issue
> **Reference:** [Issue #2](https://github.com/AlexKucera/librofm-downloader/issues/2)

## Goal

Set up the Python project foundation: `pyproject.toml`, package structure, virtual environment, and a **config module** that loads `config.yaml` + `secrets.yaml`, deep-merges them, validates required fields, rejects credentials in config, applies defaults, and returns a typed immutable `Config` dataclass.

## What Was Done

- **`pyproject.toml`** — build system (setuptools), runtime deps (httpx≥0.27, pyyaml≥6.0, rich≥13.0), dev deps (pytest≥8.0, pytest-mock≥3.12), Python ≥3.11
- **Virtual environment** — `.venv/` with Python 3.13, all deps installed cleanly via `pip install -e ".[dev]"`
- **Package structure** — `librofm_downloader/__init__.py`, `librofm_downloader/config.py`
- **Config module** (`librofm_downloader/config.py`, 112 lines):
  - `@dataclass(frozen=True) Config` — immutable typed config with 7 fields (username, password, format, output_dir, download_extras, download_covers)
  - `load_config(config_path, secrets_path)` — public API: load YAML → check no creds in config → merge secrets over config → validate required fields → validate format → return Config
  - Exception hierarchy: `ConfigError` → `CredentialsInConfigError`, `MissingFieldError`, `InvalidFormatError`
  - `_deep_merge()` — recursive dict merge (override wins on conflict)
  - `_check_no_credentials_in_config()` — reject username/password in config.yaml
  - `_check_required_fields()` — require username+password after merge
  - `_validate_format()` — allow only `m4b_mp3_fallback`, `mp3_only`, `m4b_only`
- **Test suite** (`tests/test_config.py`, 232 lines, **25 tests** across 6 classes):
  - `TestLoadValidConfig` (5 tests) — tracer bullet: returns frozen dataclass with all fields populated
  - `TestSecretsMerge` (3 tests) — secret values override config values; non-overlapping keys preserved
  - `TestCredentialsRejection` (3 tests) — raises `CredentialsInConfigError`; message mentions "secrets"
  - `TestMissingRequiredFields` (3 tests) — raises `MissingFieldError`; lists all missing fields
  - `TestDefaults` (4 tests) — format→m4b_mp3_fallback, output_dir→./audiobooks, download_extras→True, download_covers→True
  - `TestInvalidFormat` (2 tests) — raises `InvalidFormatError`; error lists valid formats
  - `TestEdgeCases` (5 tests) — frozen immutability, extra keys tolerated, explicit False bools, all 3 valid formats accepted
- **11 YAML fixture files** in `tests/fixtures/`
- **`CHANGELOG.md`** — Keep a Changelog format with initial Unreleased section

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| `@dataclass(frozen=True)` for Config | Immutable, hashable, self-documenting; prevents accidental mutation at runtime |
| Fail-fast validation order | Check creds-in-config first (security), then missing fields, then format value — each check is independent and gives clearest error |
| Deep-merge before validation | Secrets must be merged first so that credentials from secrets satisfy the "required fields" check; cred-check runs on raw config.yaml only |
| Custom exception hierarchy | Three distinct error types let callers handle security (creds-in-config), user-error (missing fields), and configuration (bad format) differently |
| `frozenset` for VALID_FORMATS | Immutable constant; O(1) lookup; clearly signals "these are the only valid values" |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| `BackendUnavailable: Cannot import 'setuptools.backends._legacy'` | Used wrong build-backend string in initial pyproject.toml | Changed to `setuptools.build_meta` |
| `NameError: name 'merged' is not defined` (8 test failures) | When inserting `_check_no_credentials_in_config()` call into `load_config()`, the edit accidentally dropped the `merged = _deep_merge(...)` line below it | Re-added the merged assignment line |
| Repeated anchor-hash mismatches during edits | Including anchors from **config.py** inside an edit operation targeting **test_config.py** — the tool validates all anchors against the target file path | Split edits into separate calls per file; always re-read before editing |

## Files Changed

| File | Change Summary |
|------|---------------|
| `pyproject.toml` | New — project metadata, dependencies, pytest config |
| `CHANGELOG.md` | New — Keep a Changelog format |
| `librofm_downloader/__init__.py` | New — package root docstring |
| `librofm_downloader/config.py` | New — Config dataclass, load_config(), validation, exceptions (112 lines) |
| `tests/__init__.py` | New — empty package init |
| `tests/test_config.py` | New — 25 tests across 7 test classes (232 lines) |
| `tests/fixtures/valid_config.yaml` | New — full config without creds |
| `tests/fixtures/valid_secrets.yaml` | New — username + password only |
| `tests/fixtures/config_with_overrides.yaml` | New — config with format/output_dir/extras/covers set |
| `tests/fixtures/secrets_with_overrides.yaml` | New — secrets overriding format + output_dir |
| `tests/fixtures/config_with_creds.yaml` | New — config containing username+password (should be rejected) |
| `tests/fixtures/secrets_minimal.yaml` | New — minimal secrets with just format |
| `tests/fixtures/config_no_creds.yaml` | New — config with only format, no creds section |
| `tests/fixtures/secrets_missing_username.yaml` | New — secrets with password but no username |
| `tests/fixtures/config_minimal.yaml` | New — empty librofm: {} block (tests defaults) |
| `tests/fixtures/secrets_only_creds.yaml` | New — secrets with only username+password |
| `tests/fixtures/config_invalid_format.yaml` | New — config with format: wav (should be rejected) |

## Open Items & Next Steps

- None for this slice — all 11 acceptance criteria met, 25/25 tests passing
- Next issue would likely cover: auth module (OAuth2 password grant against Libro.fm), library fetching, or download logic per the project roadmap

---

*Log written by write-log skill*
