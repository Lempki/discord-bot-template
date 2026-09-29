"""Tests for utils/automod.py, the /admin automod commands, and the AutoMod escalation.

Discord is replaced by fakes that record the rules the bot creates, edits, and deletes.
"""

from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot import BotApp
from cogs.admin import AdminCog
from cogs.moderation import ModerationCog
from localization import LOCALES
from tests.conftest import GUILD_ID, make_interaction, sent_messages
from utils import automod, database

BOT_ID = 666666666666666666
USER_ID = 333333333333333333
ALERT_ID = 777777777777777777
OTHER_ID = 123456789012345678
EN = LOCALES["en"]

KEYWORD = discord.AutoModRuleTriggerType.keyword
PRESET = discord.AutoModRuleTriggerType.keyword_preset
BLOCK = discord.AutoModRuleActionType.block_message
ALERT = discord.AutoModRuleActionType.send_alert_message


class FakeRule:
    """An AutoMod rule that applies edits to itself, the way Discord would."""

    def __init__(
        self,
        guild: "FakeGuild",
        creator_id: int,
        trigger: discord.AutoModTrigger,
        actions: list[discord.AutoModRuleAction],
    ) -> None:
        self.guild = guild
        self.creator_id = creator_id
        self.trigger = trigger
        self.actions = actions
        self.edits: list[dict[str, Any]] = []

    async def edit(self, **changes: Any) -> "FakeRule":
        self.edits.append(changes)
        self.trigger = changes.get("trigger", self.trigger)
        self.actions = changes.get("actions", self.actions)
        return self

    async def delete(self) -> None:
        self.guild.rules.remove(self)


class FakeGuild:
    """A guild whose AutoMod rules live in a list."""

    def __init__(self) -> None:
        self.id = GUILD_ID
        self.rules: list[FakeRule] = []
        self.created: list[dict[str, Any]] = []

    async def fetch_automod_rules(self) -> list[FakeRule]:
        return list(self.rules)

    async def create_automod_rule(self, **fields: Any) -> FakeRule:
        self.created.append(fields)
        rule = FakeRule(self, BOT_ID, fields["trigger"], fields["actions"])
        self.rules.append(rule)
        return rule

    def add_rule(
        self,
        creator_id: int,
        trigger: discord.AutoModTrigger,
        actions: list[discord.AutoModRuleAction] | None = None,
    ) -> FakeRule:
        rule = FakeRule(
            self,
            creator_id,
            trigger,
            actions or [discord.AutoModRuleAction(type=BLOCK)],
        )
        self.rules.append(rule)
        return rule


def owner() -> SimpleNamespace:
    return SimpleNamespace(id=BOT_ID, name="TestBot")


def keywords(*words: str) -> discord.AutoModTrigger:
    return discord.AutoModTrigger(type=KEYWORD, keyword_filter=list(words))


def forbidden() -> discord.Forbidden:
    return discord.Forbidden(
        MagicMock(status=403, reason="Forbidden"), "Missing Permissions"
    )


# ---------------------------------------------------------------------------
# Rule management in utils/automod.py.
# ---------------------------------------------------------------------------


def test_parse_keywords_splits_lowercases_and_dedupes() -> None:
    assert automod.parse_keywords(" Spam*, spam* ,,Scam\nfree nitro ") == [
        "spam*",
        "scam",
        "free nitro",
    ]


async def test_add_keywords_creates_an_enabled_blocking_rule() -> None:
    guild = FakeGuild()

    total = await automod.add_keywords(guild, owner(), ["spam"], ALERT_ID)  # type: ignore[arg-type]

    assert total == ["spam"]
    [created] = guild.created
    assert created["enabled"] is True
    assert created["name"] == "TestBot keyword filter"
    assert created["trigger"].keyword_filter == ["spam"]
    assert [a.type for a in created["actions"]] == [BLOCK, ALERT]
    assert created["actions"][1].channel_id == ALERT_ID


async def test_add_keywords_extends_the_bot_rule_and_keeps_admin_extras() -> None:
    guild = FakeGuild()
    trigger = discord.AutoModTrigger(
        type=KEYWORD, keyword_filter=["spam"], allow_list=["spammer"]
    )
    rule = guild.add_rule(BOT_ID, trigger)

    total = await automod.add_keywords(guild, owner(), ["scam", "spam"], None)  # type: ignore[arg-type]

    assert total == ["spam", "scam"]
    assert rule.trigger.keyword_filter == ["spam", "scam"]
    assert rule.trigger.allow_list == ["spammer"]
    assert guild.created == []


async def test_add_keywords_never_touches_rules_made_by_people() -> None:
    guild = FakeGuild()
    theirs = guild.add_rule(OTHER_ID, keywords("theirs"))

    await automod.add_keywords(guild, owner(), ["mine"], None)  # type: ignore[arg-type]

    assert theirs.edits == []
    assert len(guild.created) == 1


async def test_add_keywords_refuses_to_exceed_the_limit() -> None:
    guild = FakeGuild()
    guild.add_rule(BOT_ID, keywords(*[f"w{i}" for i in range(automod.KEYWORD_LIMIT)]))

    with pytest.raises(automod.KeywordLimitError):
        await automod.add_keywords(guild, owner(), ["one-more"], None)  # type: ignore[arg-type]


async def test_remove_keywords_deletes_the_rule_once_empty() -> None:
    guild = FakeGuild()
    rule = guild.add_rule(BOT_ID, keywords("spam", "scam"))

    assert await automod.remove_keywords(guild, BOT_ID, ["scam"]) == ["spam"]  # type: ignore[arg-type]
    assert rule.trigger.keyword_filter == ["spam"]
    assert await automod.remove_keywords(guild, BOT_ID, ["spam"]) == []  # type: ignore[arg-type]
    assert guild.rules == []


async def test_set_preset_creates_changes_and_deletes_the_preset_rule() -> None:
    guild = FakeGuild()

    assert await automod.set_preset(guild, owner(), "slurs", True, None) == ["slurs"]  # type: ignore[arg-type]
    [rule] = guild.rules
    assert rule.trigger.type == PRESET

    enabled = await automod.set_preset(guild, owner(), "profanity", True, None)  # type: ignore[arg-type]
    assert enabled == ["profanity", "slurs"]
    assert rule.trigger.presets.profanity and rule.trigger.presets.slurs

    await automod.set_preset(guild, owner(), "profanity", False, None)  # type: ignore[arg-type]
    assert await automod.set_preset(guild, owner(), "slurs", False, None) == []  # type: ignore[arg-type]
    assert guild.rules == []


async def test_set_preset_rejects_unknown_categories() -> None:
    with pytest.raises(ValueError, match="Unknown preset"):
        await automod.set_preset(FakeGuild(), owner(), "memes", True, None)  # type: ignore[arg-type]


async def test_set_alert_channel_replaces_only_the_alert_action() -> None:
    guild = FakeGuild()
    timeout = discord.AutoModRuleAction(duration=timedelta(minutes=5))
    rule = guild.add_rule(
        BOT_ID,
        keywords("spam"),
        [
            discord.AutoModRuleAction(type=BLOCK),
            discord.AutoModRuleAction(channel_id=OTHER_ID),
            timeout,
        ],
    )
    theirs = guild.add_rule(OTHER_ID, keywords("theirs"))

    assert await automod.set_alert_channel(guild, BOT_ID, ALERT_ID) == 1  # type: ignore[arg-type]
    assert [a.type for a in rule.actions] == [BLOCK, timeout.type, ALERT]
    assert rule.actions[-1].channel_id == ALERT_ID
    assert theirs.edits == []

    await automod.set_alert_channel(guild, BOT_ID, None)  # type: ignore[arg-type]
    assert ALERT not in [a.type for a in rule.actions]


async def test_fetch_state_reads_only_the_bot_rules() -> None:
    guild = FakeGuild()
    guild.add_rule(BOT_ID, keywords("spam"))
    guild.add_rule(OTHER_ID, keywords("theirs"))
    guild.add_rule(
        BOT_ID,
        discord.AutoModTrigger(
            type=PRESET, presets=discord.AutoModPresets(sexual_content=True)
        ),
    )

    state = await automod.fetch_state(guild, BOT_ID)  # type: ignore[arg-type]

    assert state == automod.AutoModState(keywords=["spam"], presets=["sexual_content"])


# ---------------------------------------------------------------------------
# The /admin automod commands.
# ---------------------------------------------------------------------------


@pytest.fixture
def online_bot(bot: BotApp) -> BotApp:
    """A bot that knows its own user, as it does once it has logged in."""
    user = MagicMock(spec=discord.ClientUser)
    user.id = BOT_ID
    user.name = "TestBot"
    bot._connection.user = user
    return bot


def admin_interaction(guild: FakeGuild) -> MagicMock:
    interaction = make_interaction()
    interaction.guild = guild
    return interaction


async def test_automod_add_reports_the_new_total(db: None, online_bot: BotApp) -> None:
    guild = FakeGuild()
    cog = AdminCog(online_bot)
    interaction = admin_interaction(guild)

    await cog.automod_add.callback(cog, interaction, keywords="spam, scam")

    assert guild.rules[0].trigger.keyword_filter == ["spam", "scam"]
    assert sent_messages(interaction) == [EN.automod_keywords_saved.format(count=2)]


async def test_automod_add_uses_the_stored_alert_channel(
    db: None, online_bot: BotApp
) -> None:
    await database.upsert_settings(GUILD_ID, automod_alert_channel_id=ALERT_ID)
    guild = FakeGuild()
    cog = AdminCog(online_bot)

    await cog.automod_add.callback(cog, admin_interaction(guild), keywords="spam")

    assert guild.rules[0].actions[-1].channel_id == ALERT_ID


async def test_automod_add_refuses_long_keywords(db: None, online_bot: BotApp) -> None:
    guild = FakeGuild()
    cog = AdminCog(online_bot)
    interaction = admin_interaction(guild)
    long_word = "x" * (automod.KEYWORD_LENGTH + 1)

    await cog.automod_add.callback(cog, interaction, keywords=f"ok, {long_word}")

    assert guild.rules == []
    [message] = sent_messages(interaction)
    assert long_word in message


async def test_automod_add_explains_a_missing_permission(
    db: None, online_bot: BotApp
) -> None:
    guild = FakeGuild()
    guild.fetch_automod_rules = AsyncMock(side_effect=forbidden())  # type: ignore[method-assign]
    cog = AdminCog(online_bot)
    interaction = admin_interaction(guild)

    await cog.automod_add.callback(cog, interaction, keywords="spam")

    assert sent_messages(interaction) == [EN.automod_no_permission]


async def test_automod_list_shows_every_keyword(db: None, online_bot: BotApp) -> None:
    guild = FakeGuild()
    guild.add_rule(BOT_ID, keywords("spam", "scam"))
    cog = AdminCog(online_bot)
    interaction = admin_interaction(guild)

    await cog.automod_list.callback(cog, interaction)

    [message] = sent_messages(interaction)
    assert message.startswith(EN.automod_keywords_header.format(count=2))
    assert "`spam`" in message and "`scam`" in message


async def test_automod_list_when_empty(db: None, online_bot: BotApp) -> None:
    cog = AdminCog(online_bot)
    interaction = admin_interaction(FakeGuild())

    await cog.automod_list.callback(cog, interaction)

    assert sent_messages(interaction) == [EN.automod_keywords_none]


async def test_automod_alert_stores_the_channel_after_updating_rules(
    db: None, online_bot: BotApp
) -> None:
    guild = FakeGuild()
    rule = guild.add_rule(BOT_ID, keywords("spam"))
    cog = AdminCog(online_bot)
    interaction = admin_interaction(guild)
    channel = MagicMock(id=ALERT_ID, mention=f"<#{ALERT_ID}>")

    await cog.automod_alert.callback(cog, interaction, channel=channel)

    assert rule.actions[-1].channel_id == ALERT_ID
    settings = await database.get_settings(GUILD_ID)
    assert settings.automod_alert_channel_id == ALERT_ID
    assert sent_messages(interaction) == [
        EN.automod_alert_set.format(channel=f"<#{ALERT_ID}>")
    ]


async def test_automod_preset_reports_the_category(
    db: None, online_bot: BotApp
) -> None:
    guild = FakeGuild()
    cog = AdminCog(online_bot)
    interaction = admin_interaction(guild)

    await cog.automod_preset.callback(
        cog, interaction, category=MagicMock(value="slurs"), enabled=True
    )

    assert sent_messages(interaction) == [
        EN.automod_preset_on.format(preset=EN.preset_slurs)
    ]


async def test_automod_preset_reports_a_refusal(db: None, online_bot: BotApp) -> None:
    guild = FakeGuild()
    error = discord.HTTPException(MagicMock(status=400, reason="Bad"), "Max rules")
    guild.create_automod_rule = AsyncMock(side_effect=error)  # type: ignore[method-assign]
    cog = AdminCog(online_bot)
    interaction = admin_interaction(guild)

    await cog.automod_preset.callback(
        cog, interaction, category=MagicMock(value="slurs"), enabled=True
    )

    assert sent_messages(interaction) == [EN.automod_failed.format(error=error)]


async def test_automod_escalation_is_stored(db: None, online_bot: BotApp) -> None:
    cog = AdminCog(online_bot)
    interaction = make_interaction()

    await cog.automod_escalation.callback(
        cog, interaction, mode=MagicMock(value="warn")
    )

    assert (await database.get_settings(GUILD_ID)).automod_escalation == "warn"
    assert sent_messages(interaction) == [EN.automod_escalation_warn]


# ---------------------------------------------------------------------------
# Warnings for blocked messages.
# ---------------------------------------------------------------------------


def execution(
    action_type: discord.AutoModRuleActionType = BLOCK,
    keyword: str | None = "spam",
) -> SimpleNamespace:
    """An AutoMod execution by a lower-ranked member, whose guild has an alert channel."""
    alert_channel = MagicMock(spec=discord.TextChannel)
    alert_channel.send = AsyncMock()
    guild = MagicMock(spec=discord.Guild)
    guild.id = GUILD_ID
    guild.preferred_locale = discord.Locale.american_english
    guild.get_channel.return_value = alert_channel
    member = MagicMock(spec=discord.Member)
    member.id = USER_ID
    member.bot = False
    member.guild = guild
    member.display_name = "TestUser"
    member.kick = AsyncMock()
    member.ban = AsyncMock()
    member.timeout = AsyncMock()
    return SimpleNamespace(
        action=discord.AutoModRuleAction(type=action_type)
        if action_type != ALERT
        else discord.AutoModRuleAction(channel_id=ALERT_ID),
        guild_id=GUILD_ID,
        user_id=USER_ID,
        guild=guild,
        member=member,
        matched_keyword=keyword,
        alert_channel=alert_channel,
    )


async def test_blocked_message_becomes_a_warning_with_a_report(
    db: None, online_bot: BotApp
) -> None:
    await database.upsert_settings(
        GUILD_ID, automod_escalation="warn", automod_alert_channel_id=ALERT_ID
    )
    cog = ModerationCog(online_bot)
    event = execution()

    await cog.on_automod_action(event)  # type: ignore[arg-type]

    [warning] = await database.get_warnings(GUILD_ID, USER_ID)
    assert (warning.moderator_id, warning.reason) == (BOT_ID, "AutoMod: spam")
    [report] = event.alert_channel.send.call_args.args
    assert report == EN.automod_warned.format(user="TestUser", count=1, threshold=3)


async def test_escalation_is_off_by_default(db: None, online_bot: BotApp) -> None:
    cog = ModerationCog(online_bot)

    await cog.on_automod_action(execution())  # type: ignore[arg-type]

    assert await database.count_warnings(GUILD_ID, USER_ID) == 0


async def test_only_the_block_action_counts(db: None, online_bot: BotApp) -> None:
    await database.upsert_settings(GUILD_ID, automod_escalation="warn")
    cog = ModerationCog(online_bot)

    await cog.on_automod_action(execution(ALERT))  # type: ignore[arg-type]

    assert await database.count_warnings(GUILD_ID, USER_ID) == 0


async def test_a_burst_of_blocks_warns_once(db: None, online_bot: BotApp) -> None:
    await database.upsert_settings(GUILD_ID, automod_escalation="warn")
    cog = ModerationCog(online_bot)

    for _ in range(3):
        await cog.on_automod_action(execution())  # type: ignore[arg-type]

    assert await database.count_warnings(GUILD_ID, USER_ID) == 1


async def test_escalation_applies_the_timeout_at_the_threshold(
    db: None, online_bot: BotApp
) -> None:
    await database.upsert_settings(
        GUILD_ID,
        automod_escalation="warn",
        automod_alert_channel_id=ALERT_ID,
        warn_threshold=1,
        warn_action="timeout",
        warn_timeout_minutes=30,
    )
    cog = ModerationCog(online_bot)
    event = execution()

    await cog.on_automod_action(event)  # type: ignore[arg-type]

    [duration] = event.member.timeout.call_args.args
    assert duration.total_seconds() == 30 * 60
    [report] = event.alert_channel.send.call_args.args
    assert EN.warn_threshold_timeout.format(user="TestUser", minutes=30) in report
