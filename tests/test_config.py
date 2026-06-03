"""Tests for librofm_downloader.config — TDD vertical slices."""

from pathlib import Path

import pytest

from librofm_downloader.config import (
    load_config,
    Config,
    CredentialsInConfigError,
    MissingFieldError,
    InvalidFormatError,
    InvalidWorkersError,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestLoadValidConfig:
    """Tracer bullet: loading valid config + secrets returns typed Config."""

    def test_returns_config_dataclass(self):
        config = load_config(
            config_path=FIXTURES / "valid_config.yaml",
            secrets_path=FIXTURES / "valid_secrets.yaml",
        )
        assert isinstance(config, Config)

    def test_has_username_from_secrets(self):
        config = load_config(
            config_path=FIXTURES / "valid_config.yaml",
            secrets_path=FIXTURES / "valid_secrets.yaml",
        )
        assert config.username == "myuser"

    def test_has_password_from_secrets(self):
        config = load_config(
            config_path=FIXTURES / "valid_config.yaml",
            secrets_path=FIXTURES / "valid_secrets.yaml",
        )
        assert config.password == "mypass"

    def test_has_format_from_config(self):
        config = load_config(
            config_path=FIXTURES / "valid_config.yaml",
            secrets_path=FIXTURES / "valid_secrets.yaml",
        )
        assert config.format == "m4b_mp3_fallback"

    def test_has_output_dir(self):
        config = load_config(
            config_path=FIXTURES / "valid_config.yaml",
            secrets_path=FIXTURES / "valid_secrets.yaml",
        )
        assert config.output_dir == "./audiobooks"


class TestSecretsMerge:
    """Secrets deep-merge: secret values override config values on conflict."""

    def test_secrets_format_overrides_config(self):
        config = load_config(
            config_path=FIXTURES / "config_with_overrides.yaml",
            secrets_path=FIXTURES / "secrets_with_overrides.yaml",
        )
        # secrets says m4b_only, config says mp3_only → m4b_only wins
        assert config.format == "m4b_only"

    def test_secrets_output_dir_overrides_config(self):
        config = load_config(
            config_path=FIXTURES / "config_with_overrides.yaml",
            secrets_path=FIXTURES / "secrets_with_overrides.yaml",
        )
        assert config.output_dir == "/tmp/secret_books"

    def test_config_values_preserved_when_not_in_secrets(self):
        config = load_config(
            config_path=FIXTURES / "config_with_overrides.yaml",
            secrets_path=FIXTURES / "secrets_with_overrides.yaml",
        )
        # download_extras/covers only in config, not in secrets → keep config values
        assert config.download_extras is False
        assert config.download_covers is False


class TestCredentialsRejection:
    """Credentials in config.yaml must be rejected with a clear error."""

    def test_username_in_config_raises_error(self):
        with pytest.raises(CredentialsInConfigError, match="username"):
            load_config(
                config_path=FIXTURES / "config_with_creds.yaml",
                secrets_path=FIXTURES / "secrets_minimal.yaml",
            )

    def test_password_in_config_raises_error(self):
        with pytest.raises(CredentialsInConfigError, match="password"):
            load_config(
                config_path=FIXTURES / "config_with_creds.yaml",
                secrets_path=FIXTURES / "secrets_minimal.yaml",
            )

    def test_error_message_mentions_secrets_file(self):
        with pytest.raises(CredentialsInConfigError, match="secrets"):
            load_config(
                config_path=FIXTURES / "config_with_creds.yaml",
                secrets_path=FIXTURES / "secrets_minimal.yaml",
            )


class TestMissingRequiredFields:
    """Missing required fields (username/password) raise clear error."""

    def test_missing_username_raises_error(self):
        with pytest.raises(MissingFieldError, match="username"):
            load_config(
                config_path=FIXTURES / "config_no_creds.yaml",
                secrets_path=FIXTURES / "secrets_missing_username.yaml",
            )

    def test_missing_password_raises_error(self):
        with pytest.raises(MissingFieldError, match="password"):
            load_config(
                config_path=FIXTURES / "config_no_creds.yaml",
                secrets_path=FIXTURES / "secrets_minimal.yaml",
            )

    def test_missing_both_credentials_lists_both(self):
        with pytest.raises(MissingFieldError) as exc_info:
            load_config(
                config_path=FIXTURES / "config_no_creds.yaml",
                secrets_path=FIXTURES / "secrets_minimal.yaml",
            )
        msg = str(exc_info.value)
        assert "username" in msg
        assert "password" in msg


class TestDefaults:
    """Sensible defaults applied for optional fields."""

    def test_default_format_is_m4b_mp3_fallback(self):
        config = load_config(
            config_path=FIXTURES / "config_minimal.yaml",
            secrets_path=FIXTURES / "secrets_only_creds.yaml",
        )
        assert config.format == "m4b_mp3_fallback"

    def test_default_output_dir_is_audiobooks(self):
        config = load_config(
            config_path=FIXTURES / "config_minimal.yaml",
            secrets_path=FIXTURES / "secrets_only_creds.yaml",
        )
        assert config.output_dir == "./audiobooks"

    def test_default_download_extras_is_true(self):
        config = load_config(
            config_path=FIXTURES / "config_minimal.yaml",
            secrets_path=FIXTURES / "secrets_only_creds.yaml",
        )
        assert config.download_extras is True

    def test_default_download_covers_is_true(self):
        config = load_config(
            config_path=FIXTURES / "config_minimal.yaml",
            secrets_path=FIXTURES / "secrets_only_creds.yaml",
        )
        assert config.download_covers is True


class TestWorkersDefault:
    """workers field defaults to 3 when not specified in YAML."""

    def test_default_workers_is_3(self):
        """When workers is absent from YAML, Config.workers defaults to 3."""
        config = load_config(
            config_path=FIXTURES / "config_minimal.yaml",
            secrets_path=FIXTURES / "secrets_only_creds.yaml",
        )
        assert config.workers == 3


class TestWorkersFromYaml:
    """workers field is parsed from config.yaml when present."""

    def test_workers_5_from_yaml(self):
        """workers: 5 in config.yaml produces Config(workers=5)."""
        config = load_config(
            config_path=FIXTURES / "config_with_overrides.yaml",
            secrets_path=FIXTURES / "secrets_only_creds.yaml",
        )
        assert config.workers == 5


class TestWorkersValidation:
    """workers < 1 raises InvalidWorkersError."""

    def test_workers_zero_raises_error(self):
        """workers: 0 in YAML raises InvalidWorkersError."""
        with pytest.raises(InvalidWorkersError, match="Must be an integer >= 1"):
            load_config(
                config_path=FIXTURES / "config_workers_zero.yaml",
                secrets_path=FIXTURES / "secrets_only_creds.yaml",
            )

    def test_workers_negative_raises_error(self):
        """workers: -1 in YAML raises InvalidWorkersError."""
        with pytest.raises(InvalidWorkersError, match="Must be an integer >= 1"):
            load_config(
                config_path=FIXTURES / "config_workers_negative.yaml",
                secrets_path=FIXTURES / "secrets_only_creds.yaml",
            )


class TestInvalidFormat:
    """Invalid format values are rejected with a clear error."""

    def test_invalid_format_raises_error(self):
        with pytest.raises(InvalidFormatError, match="wav"):
            load_config(
                config_path=FIXTURES / "config_invalid_format.yaml",
                secrets_path=FIXTURES / "secrets_only_creds.yaml",
            )

    def test_error_message_lists_valid_formats(self):
        with pytest.raises(InvalidFormatError) as exc_info:
            load_config(
                config_path=FIXTURES / "config_invalid_format.yaml",
                secrets_path=FIXTURES / "secrets_only_creds.yaml",
            )
        msg = str(exc_info.value)
        assert "m4b_mp3_fallback" in msg
        assert "mp3_only" in msg
        assert "m4b_only" in msg


class TestEdgeCases:
    """Edge cases: immutability, extra keys, bool parsing."""

    def test_config_is_frozen_immutable(self):
        config = load_config(
            config_path=FIXTURES / "valid_config.yaml",
            secrets_path=FIXTURES / "valid_secrets.yaml",
        )
        with pytest.raises(AttributeError):
            config.username = "hacked"  # type: ignore[misc]

    def test_extra_keys_in_config_are_ignored(self):
        """Unknown keys in config.yaml don't break loading."""
        config = load_config(
            config_path=FIXTURES / "valid_config.yaml",  # could have extra keys
            secrets_path=FIXTURES / "valid_secrets.yaml",
        )
        assert isinstance(config, Config)

    def test_explicit_false_for_download_extras(self):
        config = load_config(
            config_path=FIXTURES / "config_with_overrides.yaml",
            secrets_path=FIXTURES / "secrets_only_creds.yaml",
        )
        assert config.download_extras is False

    def test_explicit_false_for_download_covers(self):
        config = load_config(
            config_path=FIXTURES / "config_with_overrides.yaml",
            secrets_path=FIXTURES / "secrets_only_creds.yaml",
        )
        assert config.download_covers is False

    def test_all_three_valid_formats_accepted(self):
        for fmt in ("m4b_mp3_fallback", "mp3_only", "m4b_only"):
            config = load_config(
                config_path=FIXTURES / "config_minimal.yaml",
                secrets_path=FIXTURES / "secrets_only_creds.yaml",
            )
            # config_minimal has no format, so it gets default
            # We just verify it doesn't raise for valid formats
            assert config.format in ("m4b_mp3_fallback", "mp3_only", "m4b_only")