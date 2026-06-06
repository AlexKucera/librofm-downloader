# Format Strategies

librofm-downloader supports three audio format strategies, controlled by the `format` field in `config.yaml`.

## Overview

| Strategy | Behavior | Best for |
|----------|----------|----------|
| `m4b_mp3_fallback` | Try M4B first; fall back to MP3 if unavailable | **Default** — maximum compatibility |
| `mp3_only` | Download MP3 ZIP only (skip M4B entirely) | Players that don't support M4B |
| `m4b_only` | Download M4B only; skip book if unavailable | Audiobook apps that prefer M4B |

## m4b_mp3_fallback (default)

The recommended strategy for most users.

```yaml
librofm:
  format: m4b_mp3_fallback
```

**Flow:**

1. Request the M4B download URL from Libro.fm API
2. If available → download as a single `.m4b` file
3. If the API returns **404** → fall back to fetching the MP3 manifest
4. Download all MP3 ZIP parts and extract them

**What you get:**

- Most books: one `.m4b` file (AAC/ALAC audio, bookmarkable, chapter markers)
- Older or region-locked books: extracted MP3 files (one or more per book)
- **No books are skipped** — every downloadable title is fetched in some format

**Output examples:**

```
# M4B succeeded
audiobooks/Brandon Sanderson/The Way of Kings.m4b        # single file, ~450 MB

# Fell back to MP3
audiobooks/Some Author/Old Book/                          # directory with MP3s
├── part1.mp3
├── part2.mp3
└── part3.mp3
```

## mp3_only

Skip M4B entirely and always use the MP3 ZIP pipeline.

```yaml
librofm:
  format: mp3_only
```

**Flow:**

1. Fetch the MP3 download manifest from Libro.fm API
2. Download each ZIP part listed in the manifest
3. Extract all files into the output directory

**When to use this:**

- Your media player doesn't support M4B/M4A containers
- You want raw MP3 files for editing or conversion
- You're feeding files into a system that only accepts MP3

**Output:** Always a directory with extracted MP3 files:

```
audiobooks/Brandon Sanderson/The Way of Kings/
├── part1.mp3
├── part2.mp3
└── ...
```

## m4b_only

Only attempt M4B download. Skip books where M4B is not available.

```yaml
librofm:
  format: m4b_only
```

**Flow:**

1. Request the M4B download URL from Libro.fm API
2. If available → download as a single `.m4b` file
3. If the API returns **404** → log a skip message, move to next book

**When to use this:**

- You only want single-file audiobooks (cleaner library management)
- Your audiobook app (Apple Books, etc.) handles M4B natively
- You'd rather miss a book than get split MP3 files

**Output example:**

```
# Success
audiobooks/Brandon Sanderson/The Way of Kings.m4b

# Skipped (shows in summary)
Summary: 5 downloaded, 2 skipped, 0 failed
  Skipped:
    ⏭ Some Author - Old Book [9781234567890]
```

## How to choose

```
┌─────────────────────────┬──────────────────────────────┐│
│ Want every book?         │ → m4b_mp3_fallback (default) │
│ Only need MP3?           │ → mp3_only                  │
│ Single-file or nothing?  │ → m4b_only                  │
└─────────────────────────┴──────────────────────────────┘
```

## Technical details

### M4B downloads

- Single HTTP stream with **8 MB chunk** buffering
- Written to `{title}.m4b.partial` during transfer
- **Atomic rename** to final `.m4b` on completion
- Supports **resume**: if a `.partial` file exists, sends `Range` header to continue
- Progress reporting via `Content-Length` header (% complete, speed, ETA)

### MP3 downloads

- Fetches a **manifest** (`/api/v10/download-manifest?isbn=...`) listing ZIP part URLs
- Each part is downloaded as a `.zip.partial` file, then renamed to `.zip`
- ZIP contents are **extracted** into the output directory
- The ZIP file is deleted after extraction
- Each part supports resume via `Range` headers
- Parts are downloaded sequentially within each book

### Chapter renaming (MP3 only)

When `rename_chapters` is enabled (default), extracted MP3 files are renamed with chapter titles from the download manifest:

```
# Before (raw extraction)
01.mp3  02.mp3  03.mp3

# After (renamed)
001 - Opening.mp3  002 - The Arrival.mp3  003 - Departure.mp3
```

- Files are sorted naturally by numeric prefix before renaming
- Zero-padding matches the widest track number
- Blank or missing titles fall back to the original filename
- Titles are sanitized (illegal characters stripped) via the same function used for path components
- Disable in `config.yaml` with `rename_chapters: false`, or override per-run with `--rename-chapters` on the CLI
