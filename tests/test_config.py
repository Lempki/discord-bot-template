"""Tests for config.py, which reads the bot's settings from the environment."""

from pathlib import Path

import pytest

from config import Config, ConfigError, InstallTarget, ServiceConfig


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


def test_heartbeat_url_is_optional() -> None:
    assert Config.from_env({"DISCORD_TOKEN": "t"}).heartbeat_url is None
    config = Config.from_env(
        {"DISCORD_TOKEN": "t", "HEARTBEAT_URL": " https://hc-ping.com/abc "}
    )
    assert config.heartbeat_url == "https://hc-ping.com/abc"


def test_heartbeat_url_without_a_scheme_raises() -> None:
    with pytest.raises(ConfigError, match="HEARTBEAT_URL"):
        Config.from_env({"DISCORD_TOKEN": "t", "HEARTBEAT_URL": "hc-ping.com/abc"})


def test_services_are_discovered_by_name() -> None:
    config = Config.from_env(
        {
            "DISCORD_TOKEN": "t",
            "API_MEDIA_URL": "http://media:8000",
            "API_MEDIA_SECRET": "s1",
            "API_SPEECH_URL": "http://speech:8000",
            "API_SPEECH_SECRET": "s2",
        }
    )
    assert config.service("media") == ServiceConfig("http://media:8000", "s1")
    assert config.service("SPEECH") == ServiceConfig("http://speech:8000", "s2")


def test_service_without_secret_is_not_configured() -> None:
    config = Config.from_env({"DISCORD_TOKEN": "t", "API_MEDIA_URL": "http://x"})
    with pytest.raises(ConfigError, match="API_MEDIA_SECRET"):
        config.service("media")


def test_the_queue_holds_500_songs_unless_set() -> None:
    assert Config.from_env({"DISCORD_TOKEN": "t"}).max_queue_length == 500
    config = Config.from_env({"DISCORD_TOKEN": "t", "MAX_QUEUE_LENGTH": " 50 "})
    assert config.max_queue_length == 50


@pytest.mark.parametrize("value", ["0", "-5", "lots", "2.5"])
def test_a_queue_limit_that_is_not_a_positive_whole_number_raises(value: str) -> None:
    with pytest.raises(ConfigError, match="MAX_QUEUE_LENGTH"):
        Config.from_env({"DISCORD_TOKEN": "t", "MAX_QUEUE_LENGTH": value})


def test_the_bot_installs_to_servers_unless_set() -> None:
    config = Config.from_env({"DISCORD_TOKEN": "t"})
    assert config.install_to == {InstallTarget.SERVERS}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("users", {InstallTarget.USERS}),
        (" Servers , USERS ", {InstallTarget.SERVERS, InstallTarget.USERS}),
        (",", {InstallTarget.SERVERS}),
    ],
)
def test_install_to_lists_servers_and_users(
    value: str, expected: set[InstallTarget]
) -> None:
    config = Config.from_env({"DISCORD_TOKEN": "t", "INSTALL_TO": value})
    assert config.install_to == expected


def test_install_to_rejects_other_names() -> None:
    with pytest.raises(ConfigError, match="INSTALL_TO accepts servers and users"):
        Config.from_env({"DISCORD_TOKEN": "t", "INSTALL_TO": "servers,guilds"})


def test_a_dev_guild_needs_server_installs() -> None:
    with pytest.raises(ConfigError, match="DEV_GUILD_ID"):
        Config.from_env(
            {"DISCORD_TOKEN": "t", "INSTALL_TO": "users", "DEV_GUILD_ID": "123"}
        )
    config = Config.from_env(
        {"DISCORD_TOKEN": "t", "INSTALL_TO": "servers,users", "DEV_GUILD_ID": "123"}
    )
    assert config.dev_guild_id == 123
