# Troubleshooting

Common errors, their causes, and how to fix them.

## Authentication failures

### "Authentication failed: Auth failed (401)"

**Cause:** Wrong email or password in `secrets.yaml`.

**Fix:**

1. Verify you can log in to [libro.fm](https://libro.fm) in a browser with the same credentials
2. Check for typos in `secrets.yaml` (YAML is case-sensitive)
3. If you changed your Libro.fm password recently, update `secrets.yaml`

### "Authentication failed: Auth failed (xxx)" (non-401)

**Cause:** Network issue or Libro.fm API temporarily down.

**Fix:**

1. Check your internet connection
2. Try again in a few minutes
3. Check [Libro.fm status](https://status.libro.fm) if available

## Configuration errors

### "Config error: Credentials (...) found in config.yaml"

**Cause:** You put `username` or `password` in `config.yaml` instead of `secrets.yaml`.

**Fix:** Remove those lines from `config.yaml`. They belong only in `secrets.yaml`. See [Secrets](secrets.md).

### "Missing required fields in secrets.yaml: username"

**Cause:** `secrets.yaml` is missing a required field.

**Fix:** Add both `username` and `password` under the `librofm:` key:

```yaml
librofm:
  username: your-email@example.com
  password: your-password
```

### "Invalid format 'xyz'"

**Cause:** The `format` value in `config.yaml` is not one of the three valid strategies.

**Fix:** Use one of:

- `m4b_mp3_fallback`
- `mp3_only`
- `m4b_only`

### "[Errno 2] No such file or directory: 'config.yaml'"

**Cause:** The config file doesn't exist at the specified path (default: current directory).

**Fix:**

```bash
# Run from the directory that contains config.yaml
cd /path/to/your/project

# Or specify the path explicitly
librofm-downloader --config /path/to/config.yaml --secrets /path/to/secrets.yaml
```

## Download issues

### Download stops partway through

**Cause:** Network interruption, timeout, or you pressed Ctrl+C.

**Behavior:**
- Exit code **130** if Ctrl+C
- Partial file saved as `{filename}.m4b.partial` or `{filename}.zip.partial`

**Fix — resume on next run:**
The tool automatically detects `.partial` files and sends an HTTP `Range` header to resume from where it stopped. Just run again:

```bash
librofm-downloader
```

### "Failed: Author - Title [ISBN] (connection error)"

**Cause:** Intermittent network failure during a single book's download.

**Behavior:**
- That book is marked as **failed** in the summary
- All other books continue downloading normally
- Exit code is still **0** (pipeline completed)

**Fix:**
Run again — the failed book will be retried (it wasn't recorded in history since it didn't complete):

```bash
$ librofm-downloader
Summary: 0 downloaded, 0 skipped, 1 failed
  Failed:
    ✗ Brandon Sanderson - The Way of Kings [9780743565400] (connection error)

# Run again — it will retry the failed book
$ librofm-downloader
```

### Book shows as skipped with m4b_only mode

**Cause:** The book has no M4B format available from Libro.fm (API returns 404).

**Behavior:**
- Book appears under `Skipped:` in summary
- Not written to download history

**Fix options:**
- Switch to `m4b_mp3_fallback` to get the MP3 version instead
- Accept that some books aren't available in M4B format

## History file problems

### "Corrupt history file download_history.json: ... Starting with empty history."

**Cause:** The `download_history.json` file exists but contains invalid JSON.

**Behavior:**
- Tool starts with empty history (all books appear as "new")
- Already-downloaded books will be re-downloaded

**Fix:**

```bash
# Option 1: Delete and let it rebuild
rm download_history.json
librofm-downloader

# Option 2: Fix the JSON manually (if you know what's in there)
# Check for trailing commas, missing braces, etc.
```

### Books re-downloading after already being downloaded

**Cause:** The ISBN in the library response doesn't match what's stored in history.

**Check:**

```bash
# See what's recorded
cat download_history.json | python -m json.tool

# Look for the ISBN of the book that's re-downloading
```

**Possible reasons:**
- The book was re-published under a new ISBN
- History file was deleted or moved
- You're running from a different directory with a different history file

## Output / path issues

### Files going to wrong directory

**Cause:** `output_dir` setting or CWD mismatch.

**Check:**

```bash
# Verify your config
grep output_dir config.yaml

# Check where you're running from
pwd

# Use absolute paths to avoid ambiguity
librofm-downloader --config /absolute/path/to/config.yaml
```

### "Permission denied" when writing files

**Cause:** The user running the tool doesn't have write access to `output_dir`.

**Fix:**

```bash
# Check permissions
ls -la ./audiobooks/

# Fix ownership or choose a writable directory
chmod u+w ./audiobooks/
# or set output_dir to somewhere writable in config.yaml
```

## Performance

### Downloads are slow

**Check:**

1. Your internet connection speed
2. Whether a VPN/proxy is adding latency
3. Libro.fm CDN responsiveness (varies by region)

The tool downloads in a **single stream per book** (no parallelism within one book), but processes books sequentially. There is no built-in rate limiting or parallel download feature.

### Large library takes a long time

Audiobooks are large (200 MB – 1 GB each). A library of 50 books at 2 MB/s would take ~7 hours just for transfer time. This is expected behavior.

Use `--limit` to process smaller batches:

```bash
# Download 5 books at a time
librofm-downloader --limit 5
```

## Getting help

If none of the above covers your issue:

1. Run with `-v` (`--verbose`) to get detailed output including URLs and tracebacks
2. Check the [GitHub Issues](https://github.com/AlexKucera/librofm-downloader/issues) for known problems
3. Open a new issue with:
   - The error message (from `-v` output)
   - Your `format` setting
   - Whether it happens on every book or specific ones
   - Your OS and Python version (`python --version`)
