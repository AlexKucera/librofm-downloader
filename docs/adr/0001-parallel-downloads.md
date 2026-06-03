# ADR 0001: Parallel Downloads via ThreadPoolExecutor

## Status

Accepted (2026-06-03)

## Context

Libro.fm-downloader downloads audiobooks sequentially: one book completes before the next begins. Audiobook files are large (200 MB – 1 GB each), and a fresh sync run with many undownloaded books can take hours. Users want to reduce wall-clock time by downloading multiple books simultaneously.

The codebase is entirely synchronous — `httpx.Client` (not `AsyncClient`), plain functions, no `async`/`await`. The core download function (`download_book()`) is already a pure function with no shared mutable state.

## Decision

Use **`concurrent.futures.ThreadPoolExecutor`** to download multiple books in parallel.

### Concurrency model: threads (not asyncio, not processes)

| Model | Verdict |
|---|---|
| `ThreadPoolExecutor` | **Chosen** — zero refactoring of existing sync code. Threads release the GIL during HTTP I/O (~99% of download time). |
| `asyncio` + `AsyncClient` | Rejected — would require rewriting `client.py`, `downloader.py`, and the entire call chain. |
| `multiprocessing` | Rejected — overkill for I/O-bound work; IPC complexity for `DownloadHistory`. |

### Worker count

Three sources, layered (CLI > config > default):

1. **`--workers N`** CLI flag — per-invocation override
2. **`workers: N`** in `config.yaml` — persistent default
3. **Default: 3** if neither is set

### Progress reporting (TTY)

One Rich progress bar per active download. Rich's `Progress` natively supports multiple simultaneous tasks. As each book completes, its bar collapses to a `✓ Book Title` line. In non-TTY/cron mode, log lines interleave naturally.

### Error policy

**Continue all** — one book's failure does not cancel in-flight downloads. Matches existing sequential behavior of per-book fault isolation. The summary reports mixed results.

### Ctrl+C handling

Graceful drain: print `"Aborting..."` immediately so the user knows the signal was received, then let in-flight downloads finish their current work before exiting with code 130. Partial files (`.m4b.partial`, `.zip.partial`) are safe to resume on next run via HTTP Range headers.

### DownloadHistory thread-safety

Add a `threading.Lock` around `write()` / `_flush()` to prevent concurrent writes from corrupting the JSON history file or losing updates.

### API throttling

A `threading.Semaphore(3)` limits concurrent Libro.fm **API calls** (`fetch_m4b_url`, `fetch_download_manifest`, `fetch_pdf_extra_url`) regardless of worker count. CDN file downloads are **not** limited — they go to CloudFront/AWS, not Libro.fm's API servers.

Rationale: the API is the scarce resource; the CDN handles high concurrency natively. With `--workers 8`, you get 8 parallel CDN transfers but only 3 simultaneous API calls.

### Summary output

Books grouped by status — Downloaded, Failed, Skipped — then sorted in **library order** (the order `fetch_library()` returned them) within each group. Deterministic and readable.

## Consequences

### Positive

- Wall-clock time reduced proportionally to worker count (bandwidth permitting)
- Per-book fault isolation preserved — a hung CDN doesn't block other downloads
- Zero changes to `download_book()` signature or internals
- Graceful degradation: `--workers 1` is identical to current sequential behavior

### Negative

- Slightly higher memory usage (N download buffers instead of 1)
- Terminal height usage: N progress bars + header + footer
- History file write contention under high parallelism (mitigated by lock)
- Cannot evolve to true async without reversing this decision (acceptable — tool runs once per cron invocation)

### Risks

- **Libro.fm rate limiting**: mitigated by API semaphore (default 3 concurrent)
- **Bandwidth saturation**: user-configurable; default of 3 is conservative for home connections
- **Ctrl+C during file write**: same risk as sequential; `.partial` + Range resume handles it

## Alternatives Considered

1. **External downloader (aria2c, wget)**: Delegate downloads to a tool built for parallelism. Rejected — adds a dependency, loses integrated progress reporting and history tracking.
2. **Sequential with prefetching**: Fetch next book's M4B URL while current book downloads. Rejected — partial parallelism, same complexity as full threading.
3. **No parallelism**: Accept sequential downloads. Rejected — defeats the user's stated goal of throughput.
