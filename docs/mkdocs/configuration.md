# Configuration Reference

Complete reference for `config.yaml`, `secrets.yaml`, and download history.

## Default file locations

When no `--config`, `--secrets`, or `--history` flags are provided, the tool searches for each file in this order:

1. **XDG directory** — `~/.config/librofm-downloader/`
2. **Current working directory** (CWD)

The XDG directory is **created automatically** on first run if it doesn't exist. This means you can drop your files into `~/.config/librofm-downloader/` and run `librofm-downloader` from any directory.

```
~/.config/librofm-downloader/
├── config.yaml          # optional — built-in defaults used if missing
├── secrets.yaml         # required — tool exits with an error if missing
└── download_history.json # created automatically on first download
```

### Missing files: config vs secrets

The two config files have different missing-file behavior:

| File | If missing | Behavior |
|------|-----------|----------|
| `config.yaml` | Non-fatal | Tool runs with built-in defaults (m4b_mp3_fallback, `./audiobooks`, etc.). A notice is printed listing searched paths. |
| `secrets.yaml` | Fatal | Tool exits with code **1** and an error listing both searched locations so you know where to create it. |

### Overriding with CLI flags

Use `--config`, `--secrets`, and `--history` to bypass the XDG→CWD search entirely and point at specific files:

```bash
# Use files in a custom location
librofm-downloader --config /path/to/config.yaml --secrets /path/to/secrets.yaml

# Custom history file
librofm-downloader --history /path/to/download_history.json
```

When a flag is provided, that path is used directly — no search is performed.

Both config files share the same top-level key: `librofm`.

## secrets.yaml

Credentials only. This file must **not** be committed to version control.

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| `username` | `string` | ✅ | Your Libro.fm account email |
| `password` | `string` | ✅ | Your Libro.fm password |

```yaml
librofm:
  username: your-email@example.com
  password: your-password
```

> [!IMPORTANT]
> Only `username` and `password` belong in this file. All other settings go in `config.yaml`.
> If either field is missing, the tool exits with code **1** and an error message.

## config.yaml

All non-credential settings. Safe to commit. **Optional** — if missing, built-in defaults are used.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `format` | `string` | `"m4b_mp3_fallback"` | Audio download strategy. See [Format Strategies](format-strategies.md). |
| `output_dir` | `string` | `"./audiobooks"` | Base directory for downloaded files. Relative paths resolve from CWD. |
| `download_extras` | `boolean` | `true` | Download PDF extras (e.g., maps) when available. |
| `download_covers` | `boolean` | `true` | Download cover art (JPEG/PNG) when available. |

### Full example

```yaml
librofm:
  format: m4b_mp3_fallback
  output_dir: ./audiobooks
  download_extras: true
  download_covers: true
```

### Minimal example

Only `format` is meaningful here — everything else has a default:

```yaml
librofm:
  format: mp3_only
```

## How merging works

`config.yaml` and `secrets.yaml` are **deep-merged** at startup:

1. `config.yaml` is loaded as the base
2. `secrets.yaml` is layered on top (overrides on conflict)
3. The merged result is validated

This means you could theoretically put any field in either file — but **credentials in `config.yaml` are explicitly rejected** at load time with a clear error:

```
Config error: Credentials (username, password) found in config.yaml.
Move them to secrets.yaml (which is gitignored).
```

## Validation errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Config error: Credentials (...) found in config.yaml` | Username or password in config file | Move to `secrets.yaml` |
| `Missing required fields in secrets.yaml: username` | Missing credential field | Add it to `secrets.yaml` |
| `Invalid format 'foo'` | Unknown format value | Use one of: `m4b_mp3_fallback`, `mp3_only`, `m4b_only` |
| `config.yaml not found in ~/.config/.../config.yaml → ./config.yaml. Using built-in defaults.` | No config file in either location | Non-fatal — defaults used. Create `config.yaml` to customize. |
| `Missing secrets.yaml. Searched: ~/.config/.../secrets.yaml → ./secrets.yaml.` | No secrets file in either location | Create `secrets.yaml` with your credentials in one of the searched locations. |

## Download history

A third file, `download_history.json`, tracks what's been downloaded. It follows the same XDG→CWD search order as the config files, and defaults to the XDG directory when not found anywhere:

```
~/.config/librofm-downloader/download_history.json
```

The file is created automatically on first download. Override with `--history` to use a custom location.

```json
{
  "9780743565400": {
    "isbn": "9780743565400",
    "title": "The Way of Kings",
    "format": "m4b",
    "path": "./audiobooks/Brandon Sanderson/The Way of Kings/The Way of Kings.m4b",
    "downloaded_at": "2026-06-03T10:30:00+00:00"
  }
}
```

- Keyed by **ISBN** — each book is recorded once
- Used to skip already-downloaded books on subsequent runs
- If the file is corrupt or missing, the tool starts with an empty history (and logs a warning)
