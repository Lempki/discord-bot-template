"""Tests for config.py, which reads the bot's settings from the environment."""

from pathlib import Path

import pytest

from config import Config, ConfigError, ServiceConfig


def test_minimal_environment_uses_defaults() -> None:
    config = Config.from_env({"DISCORD_TOKEN": "token"})
    assert config == Config(discord_token="token")
    assert config.database_path == Path("data/bot.db")
    assert config.cogs_to_load == ("help",)


def test_missing_token_raises() -> None:
    with pytest.raises(ConfigError, match="DISCORD_TOKEN"):
        Config.from_env({})


def test_cogs_are_trimmed_and_empty_entries_dropped() -> None:
    config = Config.from_env(
        {"DISCORD_TOKEN": "t", "COGS_TO_LOAD": " help, voice ,,media "}
    )
    assert config.cogs_to_load == ("help", "voice", "media")


@pytest.mark.parametrize(("value", "expected"), [("", None), ("123", 123)])
def test_dev_guild_id(value: str, expected: int | None) -> None:
    config = Config.from_env({"DISCORD_TOKEN": "t", "DEV_GUILD_ID": value})
    assert config.dev_guild_id == expected


def test_non_numeric_dev_guild_id_raises() -> None:
    with pytest.raises(ConfigError, match="DEV_GUILD_ID"):
        Config.from_env({"DISCORD_TOKEN": "t", "DEV_GUILD_ID": "my-server"})


def test_services_are_discovered_by_name() -> None:
    config = Config.from_env(
        {
            "DISCORD_TOKEN": "t",
            "DISCORD_API_MEDIA_URL": "http://media:8000",
            "DISCORD_API_MEDIA_SECRET": "s1",
            "DISCORD_API_MORSHU_URL": "http://morshu:8000",
            "DISCORD_API_MORSHU_SECRET": "s2",
        }
    )
    assert config.service("media") == ServiceConfig("http://media:8000", "s1")
    assert config.service("MORSHU") == ServiceConfig("http://morshu:8000", "s2")


def test_service_without_secret_is_not_configured() -> None:
    config = Config.from_env(
        {"DISCORD_TOKEN": "t", "DISCORD_API_MEDIA_URL": "http://x"}
    )
    with pytest.raises(ConfigError, match="DISCORD_API_MEDIA_SECRET"):
        config.service("media")
