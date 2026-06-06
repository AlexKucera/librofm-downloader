# Issue #22: XDG config path resolution with CWD fallback

> **Date:** 2026-06-04
> **Type:** issue
> **Reference:** [GitHub #22](https://github.com/AlexKucera/librofm-downloader/issues/22) · Parent [#21](https://github.com/AlexKucera/librofm-downloader/issues/21)

## Goal

Build a path resolution engine for config files that searches `~/.config/librofm-downloader/` (XDG) first, then falls back to CWD. Wire it into `load_config()` so passing `None` for either path triggers search. Missing `config.yaml` is non-fatal (defaulted Config). Missing `secrets.yaml` is fatal (domain error listing searched paths). All OS exceptions caught internally → domain errors only. CLI should print a notice when running on built-in defaults.

## What Was Done

- Added `_resolve_config_file(filename)` to `config.py` — searches XDG (`~/.config/librofm-downloader/`) then CWD, auto-creates XDG dir, returns `Path | None`
- Modified `load_config()` signature to accept `Path | str | None` for both params; `None` triggers resolver
- Missing `config.yaml` path → `config_yaml = {}` (all fields get built-in defaults from `.get()` calls)
- Missing `secrets.yaml` path → raises `ConfigError` listing both searched locations in order
- All `FileNotFoundError`/`OSError` from file I/O caught and re-raised as `ConfigError`
- Added `_config_path: Path | None = None` field to `Config` dataclass — sentinel for "used defaults"
- CLI `run()` and argparse defaults changed from `"config.yaml"`/`"secrets.yaml"` to `None` so resolver activates
- CLI prints `[yellow]config.yaml not found. Using built-in defaults.[/yellow]` when `_config_path is None`
- 9 new tests across `TestResolveConfigFile` (5) and `TestLoadConfigWithResolution` (4)
- **181 total tests pass** (was 172)

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| `_config_path` private field on `Config` for defaults signal | Non-breaking: existing code ignores it, CLI can check it. Frozen dataclass prevents mutation. Alternatives: return tuple (breaks signature), raise warning (invisible). |
| `ConfigError` for missing secrets (not `FileNotFoundError`) | AC requires no OS exceptions leak to callers. Domain error lists searched paths so user knows where to put the file. |
| Missing config → empty dict, not exception | AC says non-fatal. All `Config` fields have sensible defaults via `.get()`. Credentials come from secrets only. |
| CLI defaults to `None` (not filename strings) | Original defaults of `"config.yaml"` bypassed the resolver entirely — `load_config` only searches when it receives `None`. |
| XDG dir auto-created on every resolution call | AC requires it. `mkdir(parents=True, exist_ok=True)` is idempotent and cheap. Ensures the dir exists for users to drop files into. |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| `ConfigError` not imported in test file | New test class used `ConfigError` but only subclasses were imported | Added `ConfigError` to the import block |
| Test created `config/` instead of `.config/` | Test XDG path used `"config"` without leading dot, but implementation uses `.config` | Fixed test to use `tmp_path / ".config" / "librofm-downloader"` |
| `environ.get("HOME", "~").expanduser()` — `AttributeError` | Called `.expanduser()` on a `str`, not `Path` | Changed to `Path(environ.get("HOME", "~")).expanduser()` |
| `mkdir()` called after `chdir()` in test | Test ordered `monkeypatch.chdir()` before creating the CWD directory | Reordered: `mkdir()` first, then `chdir()` |
| CLI showed `Config error: Cannot read config file 'config.yaml': [Errno 2]` | CLI argparse defaults were `"config.yaml"` strings — `load_config` received a path, not `None`, so resolver never ran | Changed CLI and argparse defaults to `None` |
| Duplicate `InvalidFormatError` class + orphaned docstring | Edit operation merged old code into new location | Removed duplicate, kept single definition |
| Extra `"` in docstring → `SyntaxError` | Corrupted edit left 4 closing quotes instead of 3 | Fixed to `"""Invalid audio format value."""` |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/config.py` | Added `_resolve_config_file()`, modified `load_config()` to accept `None`, added `_config_path` field to `Config`, wrapped I/O in try/except for domain errors |
| `librofm_downloader/cli.py` | Changed `run()` and argparse defaults from `"config.yaml"`/`"secrets.yaml"` to `None`, added "using built-in defaults" notice |
| `tests/test_config.py` | Added `ConfigError` + `_resolve_config_file` imports, 9 new tests in `TestResolveConfigFile` and `TestLoadConfigWithResolution` |

## Open Items & Next Steps

- [ ] Update CLI `--help` text to mention XDG search behavior
- [ ] Consider adding `XDG_CONFIG_HOME` override (currently hardcoded to `~/.config`)
- [ ] Update README/docs to document XDG config location and CWD fallback
- [ ] GitNexus index needs rebuild (`npx gitnexus analyze`) after these changes

---

*Log written by write-log skill*
