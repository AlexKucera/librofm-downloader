"""Config loading, validation, and defaults for librofm-downloader."""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Config:
    """Typed, immutable configuration for the downloader."""

    username: str
    password: str
    format: str
    output_dir: str
    download_extras: bool
    download_covers: bool
    _config_path: Path | None = None  # None = defaulted (file missing)
    workers: int = 3


class ConfigError(Exception):
    """Base exception for config-related errors."""


class CredentialsInConfigError(ConfigError):
    """Credentials found in config.yaml (should be in secrets.yaml)."""


class MissingFieldError(ConfigError):
    """Required field(s) missing from configuration."""


class InvalidFormatError(ConfigError):
    """Invalid audio format value."""


class InvalidWorkersError(ConfigError):
    """Invalid parallel download worker count."""


def _resolve_config_file(filename: str) -> Path | None:
    """Resolve a config file by searching XDG then CWD.

    Searches ``~/.config/librofm-downloader/`` first, then falls back to
    the current working directory.  Auto-creates the XDG parent directory
    on demand.

    Returns:
        Resolved :class:`Path` if found, ``None`` if absent from both locations.
    """
    from os import environ  # noqa: S405 – we only read HOME

    home = Path(environ.get("HOME", "~")).expanduser()
    xdg_path = home / ".config" / "librofm-downloader" / filename
    xdg_path.parent.mkdir(parents=True, exist_ok=True)

    if xdg_path.is_file():
        return xdg_path.resolve()

    cwd_path = Path(filename).resolve()
    if cwd_path.is_file():
        return cwd_path

    return None



def load_config(
    config_path: Path | str | None,
    secrets_path: Path | str | None,
) -> Config:
    """Load config.yaml + secrets.yaml, merge, validate, and return Config.

    When either path is ``None``, searches XDG then CWD via
    :func:`_resolve_config_file`.  Missing config.yaml is non-fatal
    (returns fully-defaulted :class:`Config`).  Missing secrets.yaml is
    fatal (raises :class:`ConfigError`).
    """
    # Resolve None paths → search XDG then CWD
    if config_path is None:
        config_path = _resolve_config_file("config.yaml")
    if secrets_path is None:
        secrets_path = _resolve_config_file("secrets.yaml")

    # Load config.yaml (non-fatal if missing)
    config_yaml: dict = {}
    if config_path is not None:
        try:
            with Path(config_path).open() as f:
                config_yaml = yaml.safe_load(f) or {}
        except (FileNotFoundError, OSError) as exc:
            raise ConfigError(
                f"Cannot read config file '{config_path}': {exc}"
            ) from exc

    # Reject credentials in config.yaml
    _check_no_credentials_in_config(config_yaml)

    # Load secrets.yaml (fatal if missing)
    if secrets_path is None:
        searched = [
            "~/.config/librofm-downloader/secrets.yaml",
            "./secrets.yaml",
        ]
        raise ConfigError(
            f"Missing secrets.yaml. Searched: {' → '.join(searched)}. "
            f"Create one with your Libro.fm username and password."
        )

    try:
        with Path(secrets_path).open() as f:
            secrets_yaml = yaml.safe_load(f) or {}
    except (FileNotFoundError, OSError) as exc:
        raise ConfigError(
            f"Cannot read secrets file '{secrets_path}': {exc}"
        ) from exc

    # Deep-merge secrets over config
    merged = _deep_merge(config_yaml, secrets_yaml)

    librofm = merged.get("librofm", {})

    # Validate required fields
    _check_required_fields(librofm)

    # Validate format
    _validate_format(librofm.get("format", "m4b_mp3_fallback"))

    # Validate workers (if explicitly set)
    if "workers" in librofm:
        _validate_workers(librofm["workers"])

    return Config(
        username=librofm["username"],
        password=librofm["password"],
        format=librofm.get("format", "m4b_mp3_fallback"),
        output_dir=librofm.get("output_dir", "./audiobooks"),
        download_extras=librofm.get("download_extras", True),
        download_covers=librofm.get("download_covers", True),
        _config_path=config_path,
        workers=librofm.get("workers", 3),
    )

def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Override wins on conflict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _check_no_credentials_in_config(config_yaml: dict) -> None:
    """Raise CredentialsInConfigError if username/password found in config.yaml."""
    librofm = config_yaml.get("librofm", {})
    cred_fields = [f for f in ("username", "password") if f in librofm]
    if cred_fields:
        raise CredentialsInConfigError(
            f"Credentials ({', '.join(cred_fields)}) found in config.yaml. "
            f"Move them to secrets.yaml (which is gitignored)."
        )


def _check_required_fields(librofm: dict) -> None:
    """Raise MissingFieldError if required fields are missing."""
    required = {"username", "password"}
    missing = [f for f in required if f not in librofm or librofm[f] is None]
    if missing:
        raise MissingFieldError(
            f"Missing required fields in secrets.yaml: {', '.join(missing)}. "
            f"Add them to your secrets.yaml file."
        )


VALID_FORMATS = frozenset({"m4b_mp3_fallback", "mp3_only", "m4b_only"})


def _validate_format(fmt: str) -> None:
    """Raise InvalidFormatError if format is not a valid value."""
    if fmt not in VALID_FORMATS:
        raise InvalidFormatError(
            f"Invalid format '{fmt}'. Valid formats: {', '.join(sorted(VALID_FORMATS))}."
        )


def _validate_workers(workers: int) -> None:
    """Raise InvalidWorkersError if workers is less than 1."""
    if not isinstance(workers, int) or workers < 1:
        raise InvalidWorkersError(
            f"Invalid workers value '{workers}'. Must be an integer >= 1."
        )