# CLI Usage

Command-line interface reference for `librofm-downloader`.

## Synopsis

```bash
librofm-downloader [OPTIONS]
```

## Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--config` | | `config.yaml` | Path to `config.yaml` |
| `--secrets` | | `secrets.yaml` | Path to `secrets.yaml` |
| `--history` | | `download_history.json` | Path to download history JSON file |
| `-v, --verbose` | | off | Print extra detail (URLs, paths, API responses) |
| `--limit` N | | `0` (no limit) | Maximum number of books to download |
| `-w, --workers` N | | `3` | Number of parallel download workers (1 = sequential) |

### --verbose

Shows internal pipeline state at each stage:

```
── config ──────────────────────────────────────
  config:  config.yaml
  secrets: secrets.yaml
  history: download_history.json
  format:   m4b_mp3_fallback
  output:   ./audiobooks
  extras:   True
  covers:   True
  user:     me@example.com
── auth ────────────────────────────────────────
  ✓ authenticated
── library ─────────────────────────────────────
  47 book(s) in library
── filtering ───────────────────────────────────
  42 already downloaded, 5 new
  ⬇ Book Title  [dim](9780743565400)[/dim]
     authors:   Brandon Sanderson
     narrators: Kate Reading, Michael Kramer
    ...
  123,456,789 bytes
```

### --limit

Cap how many books are downloaded in a single run. Useful for testing:

```bash
# Download only 1 book (the first new one)
librofm-downloader --limit 1

# Download up to 3 books
librofm-downloader --limit 3 -v
```

Books are processed in the order returned by the Libro.fm API. Already-downloaded books are filtered out **before** the limit is applied.

### --workers

Controls how many books download simultaneously:

```bash
# Default: 3 parallel downloads
librofm-downloader

# High-bandwidth connection: 5 workers
librofm-downloader -w 5

# Force sequential (useful for debugging)
librofm-downloader --workers 1
```

Resolution order (CLI > config > default):

1. **`--workers N`** / **`-w N`** on the command line
2. **`workers:`** field in `config.yaml`
3. **Default: 3**

> [!NOTE]
> The worker count controls **CDN download parallelism**. Libro.fm API calls are separately capped at 3 concurrent requests via an internal semaphore, regardless of worker count. This protects the API server while letting CDN transfers scale up.

Set to `1` for behavior identical to the pre-parallelism sequential mode.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success — all done (including "nothing new to download") |
| `1` | Fatal error — config problem, auth failure, or library fetch failure |
| `130` | Interrupted — user pressed Ctrl+C during downloads |

### Exit code 0 scenarios

- All new books downloaded successfully
- No new books to download (`All caught up!`)
- Some books failed but the pipeline completed (failures are reported in the summary)

> [!NOTE]
> Exit code 0 does **not** mean "zero failures" — it means the process ran to completion.
> Check the summary line for `failed` count.

### Exit code 1 scenarios

```bash
# Config error
$ librofm-downloader --config missing.yaml
Config error: [Errno 2] No such file or directory: 'missing.yaml'

# Auth failure
$ librofm-downloader
Authentication failed: Auth failed (401)

# Library fetch failure
$ librofm-downloader
Failed to fetch library: 502 Bad Gateway
```

### Exit code 130

```bash
$ librofm-downloader
^CDownload interrupted by user (Ctrl+C).
echo $?
130
```

Partial downloads are preserved as `.partial` files and will be **resumed** on the next run.

## Cron setup

### Basic daily sync

```cron
# m h  dom mon dow   command
0  4  *  *  *       cd /path/to/librofm-downloader && .venv/bin/librofm-downloader >> /var/log/librofm.log 2>&1
```

Runs every day at 4:00 AM, appends output to a log file.

### With email on failure

```cron
0  4  *  *  *       cd /path/to/librofm-downloader && .venv/bin/librofm-downloader || echo "librofm-downloader failed" | mail -s "DL failure" you@example.com
```

### Weekly with limit

```cron
0  3  *  *  1       cd /path/to/librofm-downloader && .venv/bin/librofm-downloader --limit 10 >> /var/log/librofm-weekly.log 2>&1
```

Runs Mondays at 3:00 AM, caps at 10 books.

### systemd timer (alternative to cron)

```ini
# /etc/systemd/system/librofm-downloader.service
[Unit]
Description=Libro.fm Audiobook Downloader
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/path/to/librofm-downloader
ExecStart=/path/to/librofm-downloader/.venv/bin/librofm-downloader

# /etc/systemd/system/librofm-downloader.timer
[Unit]
Description=Run librofm-downloader daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl enable --now librofm-downloader.timer
journalctl -u librofm-downloader -f
```

## TTY vs non-TTY output

The tool auto-detects whether stdout is a terminal:

### TTY (interactive terminal)

- **Rich progress bars** with percentage, transfer speed, ETA, and size
- Color-coded results (✓ green, ✗ red, ⏭ yellow)
- Progress bars update in-place (no scrolling flood)

```
Brandon Sanderson - The Way of Kings ████████████████████  67.3% 2.1 MB/s 00:03  45.2 MB
```

### Non-TTY (cron, pipe, redirect)

- **Plain text log lines** — one per event
- No color, no progress bar updates
- Same information, machine-friendly format

```
Downloading: Brandon Sanderson - The Way of Kings (unknown size)
Completed: Brandon Sanderson - The Way of Kings
Summary: 1 downloaded, 0 skipped, 0 failed
```

This means you get nice progress in your terminal and clean logs in cron — **no flags needed**.
