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


def status_text(**overrides: object) -> str:
    """The English status reply for default settings, with the given values replaced.

    The test bot never logs in, so it cannot read AutoMod rules and reports them unavailable.
    """
    values: dict[str, object] = {
        "channel": EN.status_any_channel,
        "autorole": EN.status_none,
        "dj": EN.status_none,
        "fair": EN.status_off,
        "loudness": EN.status_on,
        "leavers": EN.status_off,
        "goodbye": EN.status_off,
        "threshold": 3,
        "action": EN.action_kick,
        "timeout": 60,
        "escalation": EN.escalation_none,
        "alert": EN.status_none,
        "keywords": EN.status_unavailable,
        "presets": EN.status_unavailable,
    }
    values.update(overrides)
    return EN.admin_status.format(**values)


async def test_status_shows_defaults(db: None, bot: BotApp) -> None:
    cog = AdminCog(bot)
    interaction = make_interaction()

    await cog.status.callback(cog, interaction)

    assert sent_messages(interaction) == [status_text()]


async def test_status_shows_configured_values(db: None, bot: BotApp) -> None:
    await database.upsert_settings(
        GUILD_ID,
        bot_channel_id=CHANNEL_ID,
        auto_role_id=ROLE_ID,
        warn_threshold=5,
        warn_action="timeout",
        warn_timeout_minutes=90,
        automod_escalation="warn",
        automod_alert_channel_id=CHANNEL_ID,
    )
    cog = AdminCog(bot)
    interaction = make_interaction()

    await cog.status.callback(cog, interaction)

    assert sent_messages(interaction) == [
        status_text(
            channel=f"<#{CHANNEL_ID}>",
            autorole=f"<@&{ROLE_ID}>",
            threshold=5,
            action=EN.action_timeout,
            timeout=90,
            escalation=EN.escalation_warn,
            alert=f"<#{CHANNEL_ID}>",
        )
    ]


async def test_status_shows_legacy_role_name(db: None, bot: BotApp) -> None:
    await database.upsert_settings(GUILD_ID, auto_role_name="Member")
    cog = AdminCog(bot)
    interaction = make_interaction()

    await cog.status.callback(cog, interaction)

    assert sent_messages(interaction) == [status_text(autorole="Member")]


async def test_set_timeout_stores_minutes(db: None, bot: BotApp) -> None:
    cog = AdminCog(bot)
    interaction = make_interaction()

    await cog.set_timeout.callback(cog, interaction, minutes=45)

    assert (await database.get_settings(GUILD_ID)).warn_timeout_minutes == 45
    assert sent_messages(interaction) == [EN.admin_timeout_set.format(minutes=45)]


async def test_admin_replies_even_when_bot_is_silent(db: None) -> None:
    # Admin replies are ephemeral, so LOCALE=silent must not hide them.
    silent_bot = BotApp(Config(discord_token="t", locale="silent"))
    cog = AdminCog(silent_bot)
    interaction = make_interaction()

    await cog.set_threshold.callback(cog, interaction, count=4)

    assert sent_messages(interaction) == [EN.admin_threshold_set.format(count=4)]


async def test_djrole_sets_and_clears_the_dj_role(db: None, bot: BotApp) -> None:
    cog = AdminCog(bot)
    role = MagicMock(spec=discord.Role)
    role.id = 77
    role.mention = "<@&77>"
    interaction = make_interaction()

    await cog.set_dj_role.callback(cog, interaction, role)  # type: ignore[arg-type]
    assert (await database.get_settings(GUILD_ID)).dj_role_id == 77
    assert sent_messages(interaction) == [EN.admin_dj_set.format(role="<@&77>")]

    cleared = make_interaction()
    await cog.set_dj_role.callback(cog, cleared, None)  # type: ignore[arg-type]
    assert (await database.get_settings(GUILD_ID)).dj_role_id is None
    assert sent_messages(cleared) == [EN.admin_dj_cleared]


async def test_fairqueue_turns_taking_turns_on_and_off(db: None, bot: BotApp) -> None:
    cog = AdminCog(bot)
    on = make_interaction()
    await cog.set_fair_queue.callback(cog, on, True)  # type: ignore[arg-type]
    assert (await database.get_settings(GUILD_ID)).fair_queue is True
    assert sent_messages(on) == [EN.admin_fair_on]

    off = make_interaction()
    await cog.set_fair_queue.callback(cog, off, False)  # type: ignore[arg-type]
    assert (await database.get_settings(GUILD_ID)).fair_queue is False
    assert sent_messages(off) == [EN.admin_fair_off]


async def test_goodbye_names_its_channel_or_asks_for_one(db: None, bot: BotApp) -> None:
    cog = AdminCog(bot)
    without = make_interaction()
    await cog.set_goodbye.callback(cog, without, True)  # type: ignore[arg-type]
    assert (await database.get_settings(GUILD_ID)).goodbye_message is True
    # Without a bot channel, the goodbye has nowhere to go yet.
    assert sent_messages(without) == [EN.admin_goodbye_no_channel]

    await database.upsert_settings(GUILD_ID, bot_channel_id=CHANNEL_ID)
    with_channel = make_interaction()
    await cog.set_goodbye.callback(cog, with_channel, True)  # type: ignore[arg-type]
    assert sent_messages(with_channel) == [
        EN.admin_goodbye_on.format(channel=f"<#{CHANNEL_ID}>")
    ]

    off = make_interaction()
    await cog.set_goodbye.callback(cog, off, False)  # type: ignore[arg-type]
    assert (await database.get_settings(GUILD_ID)).goodbye_message is False
    assert sent_messages(off) == [EN.admin_goodbye_off]


async def test_status_shows_the_fair_queue_and_goodbye(db: None, bot: BotApp) -> None:
    await database.upsert_settings(GUILD_ID, fair_queue=True, goodbye_message=True)
    cog = AdminCog(bot)
    interaction = make_interaction()

    await cog.status.callback(cog, interaction)  # type: ignore[arg-type]

    assert sent_messages(interaction) == [
        status_text(fair=EN.status_on, goodbye=EN.status_on)
    ]


async def test_loudness_and_leave_cleanup_turn_on_and_off(
    db: None, bot: BotApp
) -> None:
    cog = AdminCog(bot)
    quiet = make_interaction()
    await cog.set_loudness.callback(cog, quiet, False)  # type: ignore[arg-type]
    leavers = make_interaction()
    await cog.set_leave_cleanup.callback(cog, leavers, True)  # type: ignore[arg-type]

    settings = await database.get_settings(GUILD_ID)
    assert (settings.even_loudness, settings.leave_cleanup) == (False, True)
    assert sent_messages(quiet) == [EN.admin_loudness_off]
    assert sent_messages(leavers) == [EN.admin_leavers_on]

    status = make_interaction()
    await cog.status.callback(cog, status)  # type: ignore[arg-type]
    assert sent_messages(status) == [
        status_text(loudness=EN.status_off, leavers=EN.status_on)
    ]
