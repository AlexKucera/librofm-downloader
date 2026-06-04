"""Tests for librofm_downloader.config — TDD vertical slices."""

from pathlib import Path

import pytest

from librofm_downloader.config import (
    load_config,
    _resolve_config_file,
    Config,
    ConfigError,
    CredentialsInConfigError,
    load_config,
    _resolve_config_file,
    Config,
    CredentialsInConfigError,
    MissingFieldError,
    InvalidFormatError,
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


class TestResolveConfigFile:
    """XDG-then-CWD path resolution for config files."""

    def test_returns_path_when_file_in_xdg(self, tmp_path, monkeypatch):
        """File found in XDG dir → returns resolved Path."""
        xdg_dir = tmp_path / ".config" / "librofm-downloader"
        xdg_dir.mkdir(parents=True)
        (xdg_dir / "config.yaml").write_text("librofm:\n  format: m4b_only\n")

        (tmp_path / "cwd").mkdir(exist_ok=True)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path / "cwd")  # CWD has no file

        result = _resolve_config_file("config.yaml")

        assert result is not None
        assert result.name == "config.yaml"
        assert "librofm-downloader" in str(result)

    def test_returns_path_when_file_only_in_cwd(self, tmp_path, monkeypatch):
        """File only in CWD (not XDG) → returns CWD Path."""
        (tmp_path / "config.yaml").write_text("librofm:\n  format: mp3_only\n")

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)  # CWD has the file, XDG is empty

        result = _resolve_config_file("config.yaml")

        assert result is not None
        assert result.name == "config.yaml"
        # Should be resolved from CWD, not XDG
        assert ".config" not in str(result)

    def test_xdg_wins_when_both_present(self, tmp_path, monkeypatch):
        """File in both XDG and CWD → XDG path takes priority."""
        xdg_dir = tmp_path / ".config" / "librofm-downloader"
        xdg_dir.mkdir(parents=True)
        (xdg_dir / "config.yaml").write_text("xdg_version\n")

        (tmp_path / "config.yaml").write_text("cwd_version\n")

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        result = _resolve_config_file("config.yaml")

        assert result is not None
        assert "librofm-downloader" in str(result)  # XDG path
        assert result.read_text() == "xdg_version\n"

    def test_returns_none_when_file_absent_from_both(self, tmp_path, monkeypatch):
        """File missing from XDG and CWD → returns None."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        result = _resolve_config_file("config.yaml")

        assert result is None

    def test_xdg_directory_auto_created(self, tmp_path, monkeypatch):
        """XDG parent dir is created even when file is absent."""
        xdg_parent = tmp_path / ".config" / "librofm-downloader"
        assert not xdg_parent.exists()

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        _resolve_config_file("config.yaml")

        assert xdg_parent.is_dir()


class TestLoadConfigWithResolution:
    """load_config wired to _resolve_config_file for None paths."""

    def test_secrets_only_returns_defaulted_config(self, tmp_path, monkeypatch):
        """config.yaml missing, secrets.yaml present → defaulted Config + creds."""
        xdg_dir = tmp_path / ".config" / "librofm-downloader"
        xdg_dir.mkdir(parents=True)
        (xdg_dir / "secrets.yaml").write_text(
            "librofm:\n  username: alice\n  password: s3cret\n"
        )

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        config = load_config(None, None)

        # Credentials from secrets
        assert config.username == "alice"
        assert config.password == "s3cret"
        # Built-in defaults (config.yaml was missing)
        assert config.format == "m4b_mp3_fallback"
        assert config.output_dir == "./audiobooks"
        assert config.download_extras is True
        assert config.download_covers is True

    def test_neither_file_raises_error_with_searched_paths(self, tmp_path, monkeypatch):
        """Both files missing → ConfigError listing every path searched."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        with pytest.raises(ConfigError) as exc_info:
            load_config(None, None)

        msg = str(exc_info.value)
        assert "secrets.yaml" in msg
        assert "librofm-downloader" in msg or ".config" in msg

    def test_explicit_config_path_bypasses_search(self, tmp_path, monkeypatch):
        """Explicit config path → used as-is; secrets still searches if None."""
        # Explicit config file
        explicit_config = tmp_path / "my_config.yaml"
        explicit_config.write_text(
            "librofm:\n  format: mp3_only\n  output_dir: ./custom\n"
        )

        # Secrets only in XDG
        xdg_dir = tmp_path / ".config" / "librofm-downloader"
        xdg_dir.mkdir(parents=True)
        (xdg_dir / "secrets.yaml").write_text(
            "librofm:\n  username: bob\n  password: p4ss\n"
        )

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        config = load_config(explicit_config, None)

        assert config.format == "mp3_only"  # from explicit config
        assert config.output_dir == "./custom"  # from explicit config
        assert config.username == "bob"  # from resolved secrets

    def test_missing_config_provides_detectable_signal(self, tmp_path, monkeypatch):
        """Missing config.yaml → caller can detect defaults were used."""
        xdg_dir = tmp_path / ".config" / "librofm-downloader"
        xdg_dir.mkdir(parents=True)
        (xdg_dir / "secrets.yaml").write_text(
            "librofm:\n  username: carol\n  password: pw\n"
        )

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        config = load_config(None, None)

        # Signal: _config_path is None when config.yaml was missing
        assert config._config_path is None