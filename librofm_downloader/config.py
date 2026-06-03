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


class ConfigError(Exception):
    """Base exception for config-related errors."""


class CredentialsInConfigError(ConfigError):
    """Credentials found in config.yaml (should be in secrets.yaml)."""


class MissingFieldError(ConfigError):
    """Required field(s) missing from configuration."""


class InvalidFormatError(ConfigError):
    """Invalid audio format value."""


def load_config(config_path: Path | str, secrets_path: Path | str) -> Config:
    """Load config.yaml + secrets.yaml, merge, validate, and return Config."""
    config_path = Path(config_path)
    secrets_path = Path(secrets_path)

    with config_path.open() as f:
        config_yaml = yaml.safe_load(f) or {}

    # Reject credentials in config.yaml
    _check_no_credentials_in_config(config_yaml)

    with secrets_path.open() as f:
        secrets_yaml = yaml.safe_load(f) or {}

    # Deep-merge secrets over config
    merged = _deep_merge(config_yaml, secrets_yaml)

    librofm = merged.get("librofm", {})

    # Validate required fields
    _check_required_fields(librofm)

    # Validate format
    _validate_format(librofm.get("format", "m4b_mp3_fallback"))

    return Config(
        username=librofm["username"],
        password=librofm["password"],
        format=librofm.get("format", "m4b_mp3_fallback"),
        output_dir=librofm.get("output_dir", "./audiobooks"),
        download_extras=librofm.get("download_extras", True),
        download_covers=librofm.get("download_covers", True),
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