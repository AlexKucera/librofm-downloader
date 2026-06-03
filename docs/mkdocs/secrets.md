# Secrets

Why `secrets.yaml` exists, how it works, and common mistakes to avoid.

## Purpose

Libro.fm authentication requires your email and password. These are stored in a **separate file** from your regular configuration so you can safely commit `config.yaml` to version control without leaking credentials.

## File format

```yaml
librofm:
  username: your-email@example.com
  password: your-password
```

Two fields, both required, both strings. That's it.

## Why it's gitignored

The `.gitignore` entry:

```
secrets.yaml
```

This is set up by default in the project template. If you clone the repo and create `secrets.yaml`, Git will never track it.

## Common mistakes

### 1. Putting credentials in config.yaml

If you accidentally add `username` or `password` to `config.yaml`:

```yaml
# ❌ Wrong — config.yaml
librofm:
  username: me@example.com    # <-- this will be rejected
  password: secret            # <-- this will be rejected
  format: m4b_mp3_fallback
```

The tool refuses to start:

```
Config error: Credentials (username, password) found in config.yaml.
Move them to secrets.yaml (which is gitignored).
```

**Fix:** Remove those lines from `config.yaml` and put them in `secrets.yaml`.

### 2. Committing before gitignore

If you `git add secrets.yaml` **before** the `.gitignore` rule was added, Git may already be tracking it:

```bash
# Check if Git is tracking it
git ls-files | grep secrets.yaml

# If it shows up, remove it from tracking (keeps local file)
git rm --cached secrets.yaml
git commit -m "Stop tracking secrets.yaml"
```

### 3. Missing fields

If `secrets.yaml` exists but is missing `username` or `password`:

```
Missing required fields in secrets.yaml: username, password.
Add them to your secrets.yaml file.
```

Both fields are **required** — there are no defaults for credentials.

### 4. Wrong indentation

YAML is whitespace-sensitive. The `librofm:` key must be at column 0, and `username`/`password` must be indented with exactly 2 spaces:

```yaml
# ✅ Correct
librofm:
  username: me@example.com
  password: secret

# ❌ Wrong — no indentation
librofm:
username: me@example.com
password: secret

# ❌ Wrong — wrong key name (not under librofm:)
username: me@example.com
password: secret
```

## Security notes

- The password is stored in **plaintext** on disk — this is a CLI tool for personal use, not a multi-user service
- The password is sent to Libro.fm's OAuth2 token endpoint over HTTPS; it is never logged or transmitted elsewhere
- If your Libro.fm account has 2FA enabled, you may need an [app-specific password](https://libro.fm/settings) depending on how Libro.fm handles OAuth2 password grants
- Never share your `secrets.yaml` file — if you do, **rotate your Libro.fm password immediately**
