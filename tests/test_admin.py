"""Tests for cogs/admin.py, run against a real bot and an in-memory database."""

from unittest.mock import MagicMock

import discord

from bot import BotApp
from cogs.admin import AdminCog
from config import Config
from localization import LOCALES
from tests.conftest import GUILD_ID, make_interaction, sent_messages
from utils import database

CHANNEL_ID = 777777777777777777
ROLE_ID = 999999999999999999
EN = LOCALES["en"]
FI = LOCALES["fi"]


def choice(value: str) -> MagicMock:
    return MagicMock(value=value)


async def test_set_channel_stores_it(db: None, bot: BotApp) -> None:
    cog = AdminCog(bot)
    interaction = make_interaction()
    channel = MagicMock(id=CHANNEL_ID, mention="<#777>")

    await cog.set_channel.callback(cog, interaction, channel=channel)

    assert (await database.get_settings(GUILD_ID)).bot_channel_id == CHANNEL_ID
    assert sent_messages(interaction) == [EN.admin_channel_set.format(channel="<#777>")]


async def test_set_channel_without_channel_clears_it(db: None, bot: BotApp) -> None:
    await database.upsert_settings(GUILD_ID, bot_channel_id=CHANNEL_ID)
    cog = AdminCog(bot)

    await cog.set_channel.callback(cog, make_interaction(), channel=None)

    assert (await database.get_settings(GUILD_ID)).bot_channel_id is None


async def test_set_autorole_stores_id_and_clears_legacy_name(
    db: None, bot: BotApp
) -> None:
    await database.upsert_settings(GUILD_ID, auto_role_name="Legacy")
    cog = AdminCog(bot)
    role = MagicMock(id=ROLE_ID, mention="<@&999>")

    await cog.set_autorole.callback(cog, make_interaction(), role=role)

    settings = await database.get_settings(GUILD_ID)
    assert (settings.auto_role_id, settings.auto_role_name) == (ROLE_ID, None)


async def test_set_autorole_without_role_clears_it(db: None, bot: BotApp) -> None:
    await database.upsert_settings(GUILD_ID, auto_role_id=ROLE_ID)
    cog = AdminCog(bot)

    await cog.set_autorole.callback(cog, make_interaction(), role=None)

    assert (await database.get_settings(GUILD_ID)).auto_role_id is None


async def test_set_threshold(db: None, bot: BotApp) -> None:
    cog = AdminCog(bot)

    await cog.set_threshold.callback(cog, make_interaction(), count=5)

    assert (await database.get_settings(GUILD_ID)).warn_threshold == 5


async def test_set_action_replies_with_localized_action_name(
    db: None, bot: BotApp
) -> None:
    cog = AdminCog(bot)
    interaction = make_interaction(locale=discord.Locale.finnish)

    await cog.set_action.callback(cog, interaction, action=choice("ban"))

    assert (await database.get_settings(GUILD_ID)).warn_action == "ban"
    assert sent_messages(interaction) == [
        FI.admin_action_set.format(action=FI.action_ban)
    ]


async def test_status_shows_defaults(db: None, bot: BotApp) -> None:
    cog = AdminCog(bot)
    interaction = make_interaction()

    await cog.status.callback(cog, interaction)

    assert sent_messages(interaction) == [
        EN.admin_status.format(
            channel=EN.status_any_channel,
            autorole=EN.status_none,
            threshold=3,
            action=EN.action_kick,
        )
    ]


async def test_status_shows_configured_values(db: None, bot: BotApp) -> None:
    await database.upsert_settings(
        GUILD_ID,
        bot_channel_id=CHANNEL_ID,
        auto_role_id=ROLE_ID,
        warn_threshold=5,
        warn_action="ban",
    )
    cog = AdminCog(bot)
    interaction = make_interaction()

    await cog.status.callback(cog, interaction)

    assert sent_messages(interaction) == [
        EN.admin_status.format(
            channel=f"<#{CHANNEL_ID}>",
            autorole=f"<@&{ROLE_ID}>",
            threshold=5,
            action=EN.action_ban,
        )
    ]


async def test_status_shows_legacy_role_name(db: None, bot: BotApp) -> None:
    await database.upsert_settings(GUILD_ID, auto_role_name="Member")
    cog = AdminCog(bot)
    interaction = make_interaction()

    await cog.status.callback(cog, interaction)

    [message] = sent_messages(interaction)
    assert message == EN.admin_status.format(
        channel=EN.status_any_channel,
        autorole="Member",
        threshold=3,
        action=EN.action_kick,
    )


async def test_admin_replies_even_when_bot_is_silent(db: None) -> None:
    # Admin replies are ephemeral, so LOCALE=silent must not hide them.
    silent_bot = BotApp(Config(discord_token="t", locale="silent"))
    cog = AdminCog(silent_bot)
    interaction = make_interaction()

    await cog.set_threshold.callback(cog, interaction, count=4)

    assert sent_messages(interaction) == [EN.admin_threshold_set.format(count=4)]
