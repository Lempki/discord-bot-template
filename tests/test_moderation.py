"""Tests for cogs/moderation.py, run against a real bot and an in-memory database."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands

from bot import BotApp
from cogs.moderation import ModerationCog, blocked_reason
from localization import LOCALES
from tests.conftest import GUILD_ID, make_interaction, sent_messages
from utils import database
from utils.replies import MESSAGE_LIMIT, chunk_lines

USER_ID = 333333333333333333
MOD_ID = 555555555555555555
BOT_ID = 666666666666666666
EN = LOCALES["en"]


def member(member_id: int, top_role: int, name: str) -> MagicMock:
    """A guild member whose top role is a plain number, so positions compare naturally."""
    fake = MagicMock(spec=discord.Member)
    fake.id = member_id
    fake.top_role = top_role
    fake.display_name = name
    fake.kick = AsyncMock()
    fake.ban = AsyncMock()
    fake.timeout = AsyncMock()
    return fake


@pytest.fixture
def scene() -> SimpleNamespace:
    """A moderator, a lower-ranked target, and the bot above both."""
    moderator = member(MOD_ID, 5, "Mod")
    target = member(USER_ID, 1, "TestUser")
    me = member(BOT_ID, 10, "Bot")
    interaction = make_interaction(user=moderator)
    interaction.guild.me = me
    interaction.guild.owner = member(1, 99, "Owner")
    for person in (moderator, target, me, interaction.guild.owner):
        person.guild = interaction.guild
    return SimpleNamespace(
        moderator=moderator, target=target, me=me, interaction=interaction
    )


def forbidden() -> discord.Forbidden:
    return discord.Forbidden(
        MagicMock(status=403, reason="Forbidden"), "Missing Permissions"
    )


# ---------------------------------------------------------------------------
# The hierarchy guard.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("target_rank", "actor_is_owner", "expected"),
    [
        (1, False, None),
        (5, False, EN.mod_target_higher.format(user="TestUser")),
        (7, False, EN.mod_target_higher.format(user="TestUser")),
        (7, True, None),
        (10, True, EN.mod_bot_too_low.format(user="TestUser")),
    ],
)
def test_blocked_reason_ranks(
    scene: SimpleNamespace, target_rank: int, actor_is_owner: bool, expected: str | None
) -> None:
    scene.target.top_role = target_rank
    if actor_is_owner:
        scene.interaction.guild.owner = scene.moderator
    assert blocked_reason(EN, scene.moderator, scene.target, scene.me) == expected


def test_blocked_reason_refuses_self_owner_and_bot(scene: SimpleNamespace) -> None:
    guild = scene.interaction.guild
    assert (
        blocked_reason(EN, scene.moderator, scene.moderator, scene.me)
        == EN.mod_target_self
    )
    protected = EN.mod_target_protected.format(user="Owner")
    assert blocked_reason(EN, scene.moderator, guild.owner, scene.me) == protected
    assert blocked_reason(EN, scene.moderator, scene.me, scene.me) == (
        EN.mod_target_protected.format(user="Bot")
    )


# ---------------------------------------------------------------------------
# The warn command.
# ---------------------------------------------------------------------------


async def test_warn_records_warning(
    db: None, bot: BotApp, scene: SimpleNamespace
) -> None:
    cog = ModerationCog(bot)

    await cog.warn.callback(cog, scene.interaction, member=scene.target, reason="spam")

    assert await database.count_warnings(GUILD_ID, USER_ID) == 1
    assert sent_messages(scene.interaction) == [
        EN.warn_issued.format(user="TestUser", count=1, threshold=3)
    ]
    scene.target.kick.assert_not_awaited()


@pytest.mark.parametrize("action", ["kick", "ban", "timeout"])
async def test_warn_at_threshold_applies_action(
    db: None, bot: BotApp, scene: SimpleNamespace, action: str
) -> None:
    await database.upsert_settings(
        GUILD_ID, warn_threshold=1, warn_action=action, warn_timeout_minutes=15
    )
    cog = ModerationCog(bot)

    await cog.warn.callback(cog, scene.interaction, member=scene.target, reason=None)

    getattr(scene.target, action).assert_awaited_once()
    announcement = {
        "kick": EN.warn_threshold_kick,
        "ban": EN.warn_threshold_ban,
        "timeout": EN.warn_threshold_timeout,
    }[action]
    expected = announcement.format(user="TestUser", minutes=15)
    assert expected in sent_messages(scene.interaction)


async def test_warn_timeout_lasts_the_configured_minutes(
    db: None, bot: BotApp, scene: SimpleNamespace
) -> None:
    await database.upsert_settings(
        GUILD_ID, warn_threshold=1, warn_action="timeout", warn_timeout_minutes=15
    )
    cog = ModerationCog(bot)

    await cog.warn.callback(cog, scene.interaction, member=scene.target, reason=None)

    [duration] = scene.target.timeout.call_args.args
    assert duration.total_seconds() == 15 * 60


async def test_warn_reports_failed_action(
    db: None, bot: BotApp, scene: SimpleNamespace
) -> None:
    await database.upsert_settings(GUILD_ID, warn_threshold=1)
    scene.target.kick.side_effect = forbidden()
    cog = ModerationCog(bot)

    await cog.warn.callback(cog, scene.interaction, member=scene.target, reason=None)

    [*_, last] = sent_messages(scene.interaction)
    assert last == EN.kick_failed.format(user="TestUser", error=forbidden())


async def test_warn_refuses_higher_ranked_target(
    db: None, bot: BotApp, scene: SimpleNamespace
) -> None:
    scene.target.top_role = 8
    cog = ModerationCog(bot)

    await cog.warn.callback(cog, scene.interaction, member=scene.target, reason=None)

    assert await database.count_warnings(GUILD_ID, USER_ID) == 0
    assert sent_messages(scene.interaction) == [
        EN.mod_target_higher.format(user="TestUser")
    ]


# ---------------------------------------------------------------------------
# /warnings list, remove, and clear.
# ---------------------------------------------------------------------------


async def test_warnings_none(db: None, bot: BotApp, scene: SimpleNamespace) -> None:
    cog = ModerationCog(bot)

    await cog.warnings.callback(cog, scene.interaction, member=scene.target)

    assert sent_messages(scene.interaction) == [
        EN.warnings_none.format(user="TestUser")
    ]


async def test_warnings_lists_entries(
    db: None, bot: BotApp, scene: SimpleNamespace
) -> None:
    await database.add_warning(GUILD_ID, USER_ID, MOD_ID, "spam")
    await database.add_warning(GUILD_ID, USER_ID, MOD_ID, None)
    cog = ModerationCog(bot)

    await cog.warnings.callback(cog, scene.interaction, member=scene.target)

    [message] = sent_messages(scene.interaction)
    assert message.startswith(EN.warnings_list_header.format(user="TestUser", count=2))
    assert "spam" in message
    assert EN.warnings_no_reason in message


async def test_long_warning_lists_are_split(
    db: None, bot: BotApp, scene: SimpleNamespace
) -> None:
    for _ in range(40):
        await database.add_warning(GUILD_ID, USER_ID, MOD_ID, "x" * 90)
    cog = ModerationCog(bot)

    await cog.warnings.callback(cog, scene.interaction, member=scene.target)

    messages = sent_messages(scene.interaction)
    assert len(messages) > 1
    assert all(len(m) <= MESSAGE_LIMIT for m in messages)
    assert sum(m.count("`#") for m in messages) == 40


def test_chunk_lines_respects_limit() -> None:
    assert chunk_lines(["a" * 6, "b" * 6, "c" * 6], limit=13) == [
        "a" * 6 + "\n" + "b" * 6,
        "c" * 6,
    ]


async def test_clearwarning_removes_own_guilds_warning(
    db: None, bot: BotApp, scene: SimpleNamespace
) -> None:
    warning_id = await database.add_warning(GUILD_ID, USER_ID, MOD_ID, "x")
    cog = ModerationCog(bot)

    await cog.clearwarning.callback(cog, scene.interaction, warning_id=warning_id)

    assert await database.count_warnings(GUILD_ID, USER_ID) == 0
    assert sent_messages(scene.interaction) == [
        EN.warning_removed.format(id=warning_id)
    ]


async def test_clearwarning_cannot_delete_another_guilds_warning(
    db: None, bot: BotApp, scene: SimpleNamespace
) -> None:
    # Regression test: warning numbers are global, so the delete must be scoped to the guild.
    other_guild = 222222222222222222
    warning_id = await database.add_warning(other_guild, USER_ID, MOD_ID, "elsewhere")
    cog = ModerationCog(bot)

    await cog.clearwarning.callback(cog, scene.interaction, warning_id=warning_id)

    assert await database.count_warnings(other_guild, USER_ID) == 1
    assert sent_messages(scene.interaction) == [
        EN.warning_not_found.format(id=warning_id)
    ]


async def test_clearwarnings_reports_count(
    db: None, bot: BotApp, scene: SimpleNamespace
) -> None:
    await database.add_warning(GUILD_ID, USER_ID, MOD_ID, "a")
    await database.add_warning(GUILD_ID, USER_ID, MOD_ID, "b")
    cog = ModerationCog(bot)

    await cog.clearwarnings.callback(cog, scene.interaction, member=scene.target)

    assert sent_messages(scene.interaction) == [
        EN.warnings_cleared.format(user="TestUser", count=2)
    ]


# ---------------------------------------------------------------------------
# The kick and ban commands.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("command", ["kick", "ban"])
async def test_kick_and_ban_pass_the_reason(
    db: None, bot: BotApp, scene: SimpleNamespace, command: str
) -> None:
    cog = ModerationCog(bot)

    await getattr(cog, command).callback(
        cog, scene.interaction, member=scene.target, reason="r"
    )

    getattr(scene.target, command).assert_awaited_once_with(reason="r")
    success = {"kick": EN.kick_success, "ban": EN.ban_success}[command]
    assert sent_messages(scene.interaction) == [success.format(user="TestUser")]


@pytest.mark.parametrize("command", ["kick", "ban"])
async def test_kick_and_ban_report_forbidden(
    db: None, bot: BotApp, scene: SimpleNamespace, command: str
) -> None:
    getattr(scene.target, command).side_effect = forbidden()
    cog = ModerationCog(bot)

    await getattr(cog, command).callback(
        cog, scene.interaction, member=scene.target, reason=None
    )

    failed = {"kick": EN.kick_failed, "ban": EN.ban_failed}[command]
    assert sent_messages(scene.interaction) == [
        failed.format(user="TestUser", error=forbidden())
    ]


async def test_kick_refuses_member_above_the_bot(
    db: None, bot: BotApp, scene: SimpleNamespace
) -> None:
    scene.interaction.guild.owner = scene.moderator
    scene.target.top_role = 10
    cog = ModerationCog(bot)

    await cog.kick.callback(cog, scene.interaction, member=scene.target, reason=None)

    scene.target.kick.assert_not_awaited()
    assert sent_messages(scene.interaction) == [
        EN.mod_bot_too_low.format(user="TestUser")
    ]


def timeout_target(*, timed_out: bool = False) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.display_name = "Ada"
    member.timeout = AsyncMock()
    member.is_timed_out.return_value = timed_out
    return member


async def test_timeout_mutes_a_member_until_a_shown_time(bot: BotApp) -> None:
    cog = ModerationCog(bot)
    cog._refuse = AsyncMock(return_value=False)  # type: ignore[method-assign]
    member = timeout_target()
    interaction = make_interaction()
    hour = app_commands.Choice(name="1 hour", value=60)

    await cog.timeout.callback(cog, interaction, member, hour, "Spam")  # type: ignore[arg-type]

    until = member.timeout.call_args.args[0]
    assert abs((until - discord.utils.utcnow()).total_seconds() - 3600) < 5
    assert member.timeout.call_args.kwargs["reason"] == "Spam"
    assert sent_messages(interaction) == [
        EN.timeout_success.format(user="Ada", until=discord.utils.format_dt(until, "f"))
    ]


async def test_untimeout_lifts_a_timeout_or_says_there_is_none(bot: BotApp) -> None:
    cog = ModerationCog(bot)
    cog._refuse = AsyncMock(return_value=False)  # type: ignore[method-assign]
    muted = timeout_target(timed_out=True)
    free = timeout_target()
    first = make_interaction()
    second = make_interaction()

    await cog.untimeout.callback(cog, first, muted)  # type: ignore[arg-type]
    await cog.untimeout.callback(cog, second, free)  # type: ignore[arg-type]

    muted.timeout.assert_awaited_once_with(None)
    assert sent_messages(first) == [EN.untimeout_success.format(user="Ada")]
    free.timeout.assert_not_awaited()
    assert sent_messages(second) == [EN.untimeout_none.format(user="Ada")]


async def test_purge_deletes_only_the_chosen_members_recent_messages(
    bot: BotApp,
) -> None:
    cog = ModerationCog(bot)
    member = MagicMock(spec=discord.Member)
    member.id = 5
    messages = [MagicMock(author=MagicMock(id=n % 2 + 5)) for n in range(10)]
    channel = MagicMock(spec=discord.TextChannel)

    async def purge(**kwargs: Any) -> list[Any]:
        return [m for m in messages[: kwargs["limit"]] if kwargs["check"](m)]

    channel.purge = AsyncMock(side_effect=purge)
    interaction = make_interaction()
    interaction.channel = channel

    await cog.purge.callback(cog, interaction, 3, member)  # type: ignore[arg-type]

    kwargs = channel.purge.call_args.kwargs
    # Messages older than 14 days cannot be deleted in bulk, so purge never looks at them.
    assert (discord.utils.utcnow() - kwargs["after"]).days == 13
    assert sent_messages(interaction) == [EN.purge_done.format(count=3)]


async def test_a_reported_message_reaches_the_alert_channel(
    db: None, bot: BotApp
) -> None:
    cog = ModerationCog(bot)
    await database.upsert_settings(GUILD_ID, automod_alert_channel_id=77)
    alerts = MagicMock(spec=discord.TextChannel)
    alerts.send = AsyncMock()
    interaction = make_interaction()
    interaction.guild.get_channel = MagicMock(return_value=alerts)
    interaction.user.mention = "<@9>"
    message = MagicMock(spec=discord.Message)
    message.content = "Something rude"
    message.jump_url = "https://discord.com/channels/1/2/3"
    message.author.mention = "<@5>"
    message.channel.mention = "<#2>"
    message.attachments = []

    await cog.report_message(interaction, message)

    embed = alerts.send.call_args.kwargs["embed"]
    assert embed.title == EN.report_title
    assert embed.description == "Something rude"
    assert embed.url == "https://discord.com/channels/1/2/3"
    assert [field.value for field in embed.fields] == ["<@5>", "<#2>", "<@9>"]
    assert sent_messages(interaction) == [EN.report_sent]


async def test_a_report_without_an_alert_channel_says_so(db: None, bot: BotApp) -> None:
    cog = ModerationCog(bot)
    interaction = make_interaction()

    await cog.report_message(interaction, MagicMock(spec=discord.Message))

    assert sent_messages(interaction) == [EN.report_no_channel]


async def test_the_warn_menu_asks_for_a_reason_and_warns(bot: BotApp) -> None:
    cog = ModerationCog(bot)
    cog.warn_member = AsyncMock()  # type: ignore[method-assign]
    member = MagicMock(spec=discord.Member)
    member.display_name = "Ada"
    interaction = make_interaction()
    interaction.response.send_modal = AsyncMock()

    await cog.warn_from_menu(interaction, member)
    modal = interaction.response.send_modal.call_args.args[0]
    assert modal.title == EN.warn_modal_title.format(user="Ada")
    modal.reason._value = "Spam"
    submit = make_interaction()
    await modal.on_submit(submit)

    cog.warn_member.assert_awaited_once_with(submit, member, "Spam")


async def test_the_right_click_menus_are_translated_but_commands_are_not(
    bot: BotApp,
) -> None:
    from discord.app_commands import (
        TranslationContext,
        TranslationContextLocation,
        locale_str,
    )

    from localization import COMMAND_TEXT
    from utils.i18n import LocaleTranslator

    translator = LocaleTranslator(COMMAND_TEXT)
    cog = ModerationCog(bot)
    location = TranslationContextLocation.command_name
    as_menu = TranslationContext(location, cog._warn_menu)
    as_command = TranslationContext(location, cog.timeout)

    menu_name = await translator.translate(
        locale_str("Warn"), discord.Locale.finnish, as_menu
    )
    command_name = await translator.translate(
        locale_str("timeout"), discord.Locale.finnish, as_command
    )

    assert (menu_name, command_name) == ("Varoita", None)
