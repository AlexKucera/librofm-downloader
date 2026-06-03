# Quickstart

Get librofm-downloader installed, configured, and running in three steps.

## 1. Install

### From PyPI (recommended)

```bash
pip install librofm-downloader
```

Requires **Python 3.11+**.

### From source

```bash
git clone https://github.com/AlexKucera/librofm-downloader.git
cd librofm-downloader
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

The `[dev]` extra installs pytest for testing — omit it if you only want to run the tool.

## 2. Configure

librofm-downloader uses two YAML files:

| File | Purpose | Committed to git? |
|------|---------|:-----------------:|
| `config.yaml` | Preferences (format, output dir, toggles) | ✅ Yes |
| `secrets.yaml` | Credentials only | ❌ No (gitignored) |

### config.yaml

```yaml
# libro.fm downloader configuration
# This file is safe to commit — no credentials here.
# Credentials go in secrets.yaml (which is gitignored).

librofm:
  # Audio format preference:
  #   m4b_mp3_fallback  — try M4B first, fall back to MP3 ZIP (default)
  #   mp3_only         — download MP3 ZIP only
  #   m4b_only         — download M4B only, skip if unavailable
  format: m4b_mp3_fallback

  # Where downloaded audiobooks are saved
  output_dir: ./audiobooks

  # Whether to download PDF extras when available
  download_extras: true

  # Whether to download cover art when available
  download_covers: true
```

### secrets.yaml

```yaml
librofm:
  username: your-email@example.com
  password: your-password
```

> [!WARNING]
> Never commit `secrets.yaml`. It is listed in `.gitignore` by default.
> If you accidentally put credentials in `config.yaml`, the tool will refuse to start and tell you to move them.

## 3. Run

### Basic sync

```bash
librofm-downloader
```

This:

1. Loads `config.yaml` + `secrets.yaml`
2. Authenticates with Libro.fm via OAuth2 password grant
3. Fetches your full library (all pages)
4. Skips books already in `download_history.json`
5. Downloads each new book (3 parallel workers by default) with a progress bar
6. Records successful downloads to history

### First run output (TTY)

```
3 book(s) to download:

Author One - Book Title One ██████████████████████████ 100.0% 2.1 MB/s 00:01  45.2 MB
  ✓ Book Title One
Author Two - Another Book     ██████████████████████████ 100.0% 1.8 MB/s 00:02 120.5 MB
  ✓ Another Book
Author Three - Third Book      ██████████████████████████ 100.0% 2.3 MB/s 00:00  89.1 MB
  ✓ Third Book

Summary: 3 downloaded, 0 skipped, 0 failed
```

### Subsequent run (nothing new)

```
All caught up! No new books to download.
```

### Cron / non-TTY output

When stdout is not a terminal (e.g., cron, piped), output switches to plain text log lines:

```
Downloading: Author One - Book Title One (unknown size)
Completed: Author One - Book Title One
Downloading: Author Two - Another Book (unknown size)
Completed: Author Two - Another Book

Summary: 2 downloaded, 0 skipped, 0 failed
```

## What gets downloaded?

Files land under your `output_dir` using this structure:

```
audiobooks/
├── Brandon Sanderson/
│   ├── The Way of Kings/
│   │   ├── The Way of Kings.m4b
│   │   ├── cover.jpg
│   │   └── map.pdf
│   └── Words of Radiance.m4b          ← no extras = flat file
└── Suzanne Collins/
    └── The Hunger Games.m4b
```

- Books with **cover art or PDF extras** get a subdirectory (`Author/Title/`)
- Books without extras are flat files (`Author/Title.m4b`)
- See [Path Patterns](path-patterns.md) for customization options

## Next steps

- [Configuration Reference](configuration.md) — every field documented
- [Format Strategies](format-strategies.md) — choose the right mode for your setup
- [CLI Usage](cli-usage.md) — all flags, exit codes, cron examples
- [Troubleshooting](troubleshooting.md) — common problems and solutions
