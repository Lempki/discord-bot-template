"""Tests for cogs/help.py."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from bot import BotApp
from cogs.admin import AdminCog
from cogs.help import (
    EMBED_LIMIT,
    FIELD_LIMIT,
    FIELDS_PER_EMBED,
    MENTION_REPLY_SECONDS,
    GuideButton,
    HelpCog,
    Section,
    build_embeds,
)
from cogs.moderation import ModerationCog
from localization import LOCALES
from tests.conftest import GUILD_ID, make_interaction, sent_messages
from utils import database
from utils.about import ProjectInfo, read_project_info

EN = LOCALES["en"]


def test_embeds_respect_every_discord_limit() -> None:
    sections = [
        Section(f"Section {n}", [f"`/cmd{i}` " + "x" * 200 for i in range(12)])
        for n in range(8)
    ]
    embeds = build_embeds(sections, "Commands", "")
    for embed in embeds:
        assert len(embed.fields) <= FIELDS_PER_EMBED
        assert len(embed) <= EMBED_LIMIT
        assert all(len(field.value or "") <= FIELD_LIMIT for field in embed.fields)
    assert (
        sum(
            field.value.count("`/cmd")
            for e in embeds
            for field in e.fields
            if field.value
        )
        == 96
    )


async def _sections(
    bot: BotApp, permissions: discord.Permissions, *cogs: commands.Cog
) -> list[Section]:
    await bot.add_cog(AdminCog(bot))
    await bot.add_cog(ModerationCog(bot))
    await bot.add_cog(HelpCog(bot))
    for cog in cogs:
        await bot.add_cog(cog)
    interaction = make_interaction()
    interaction.permissions = permissions
    interaction.translate.return_value = None
    return await bot.cogs["Help"]._sections(interaction)  # type: ignore[attr-defined, no-any-return]


class GuideLessCog(commands.Cog, name="Gadgets"):
    """A bot's own feature that has no guide text yet."""

    @app_commands.command(name="gizmo")
    async def gizmo(self, interaction: discord.Interaction) -> None:
        """Do a gizmo thing."""


async def test_an_admin_reads_the_setup_and_moderation_guides(bot: BotApp) -> None:
    sections = await _sections(bot, discord.Permissions.all())
    by_title = {section.title: section.lines for section in sections}

    assert by_title[EN.section_admin] == [
        EN.guide_admin,
        EN.help_commands.format(commands="`/admin`"),
    ]
    # A group such as /warnings counts once in the commands line.
    assert by_title[EN.section_moderation][1] == EN.help_commands.format(
        commands="`/ban`, `/kick`, `/purge`, `/timeout`, `/untimeout`, `/warn`, `/warnings`"
    )
    # The guide is what /help shows, so the help cog has no section of its own.
    assert [section.title for section in sections] == [
        EN.section_moderation,
        EN.section_admin,
    ]


async def test_a_member_reads_only_the_guides_they_can_use(bot: BotApp) -> None:
    sections = await _sections(bot, discord.Permissions.none(), GuideLessCog())

    assert [section.title for section in sections] == ["Gadgets"]


async def test_a_feature_without_a_guide_lists_its_commands_first(bot: BotApp) -> None:
    sections = await _sections(bot, discord.Permissions.none(), GuideLessCog())

    # The bot's own features come before the core ones.
    assert sections[0] == Section("Gadgets", ["`/gizmo` Do a gizmo thing."])


async def test_the_introduction_names_the_bot_channel(db: None, bot: BotApp) -> None:
    await database.upsert_settings(GUILD_ID, bot_channel_id=42)
    cog = HelpCog(bot)
    interaction = make_interaction()

    introduction = await cog._introduction(interaction)

    assert introduction == "\n\n".join(
        [EN.help_intro, EN.help_bot_channel.format(channel="<#42>")]
    )


async def test_about_shows_the_version_and_the_link(bot: BotApp) -> None:
    await bot.add_cog(HelpCog(bot))
    bot.project = ProjectInfo("discord-bot-x", "9.9.9", "https://github.com/x/y")
    interaction = make_interaction()

    await bot.cogs["Help"].about.callback(bot.cogs["Help"], interaction)  # type: ignore[attr-defined]

    (message,) = sent_messages(interaction)
    assert message.startswith("**discord-bot-x** 9.9.9")
    assert "<t:" in message
    assert message.endswith(
        LOCALES["en"].about_link.format(url="https://github.com/x/y")
    )
    assert interaction.response.send_message.call_args.kwargs["ephemeral"] is True


async def test_about_answers_even_when_public_replies_are_muted() -> None:
    from config import Config

    muted = BotApp(Config(discord_token="t", locale="silent"))
    await muted.add_cog(HelpCog(muted))
    interaction = make_interaction()

    await muted.cogs["Help"].about.callback(muted.cogs["Help"], interaction)  # type: ignore[attr-defined]

    assert sent_messages(interaction)


def test_project_info_comes_from_pyproject(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text(
        """\
[project]
name = "discord-bot-x"
version = "1.2.3"

[project.urls]
Repository = "https://github.com/x/y"
""",
        encoding="utf-8",
    )

    assert read_project_info(path) == ProjectInfo(
        "discord-bot-x", "1.2.3", "https://github.com/x/y"
    )
    assert read_project_info(tmp_path / "missing.toml").version == "unknown"


def mention(
    bot: BotApp, content: str, *, author_id: int = 7, is_bot: bool = False
) -> MagicMock:
    """A message in a guild that says content, from a member or another bot."""
    message = MagicMock(spec=discord.Message)
    message.content = content
    message.author = MagicMock(id=author_id, bot=is_bot)
    message.guild = MagicMock(
        id=GUILD_ID, preferred_locale=discord.Locale.american_english
    )
    message.reply = AsyncMock()
    message.channel.send = AsyncMock()
    return message


def bot_user(bot: BotApp, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(type(bot), "user", property(lambda _: MagicMock(id=999)))


async def test_a_bare_mention_gets_a_reply_with_the_guide_button(
    bot: BotApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    bot_user(bot, monkeypatch)
    cog = HelpCog(bot)
    message = mention(bot, " <@999> ")

    await cog.on_message(message)

    message.reply.assert_awaited_once()
    call = message.reply.call_args
    assert call.args == (EN.mention_reply,)
    assert call.kwargs["mention_author"] is False
    assert call.kwargs["delete_after"] == MENTION_REPLY_SECONDS
    assert isinstance(call.kwargs["view"], GuideButton)
    assert call.kwargs["view"].show.label == EN.mention_button


async def test_a_mention_with_words_or_from_a_bot_gets_no_reply(
    bot: BotApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    bot_user(bot, monkeypatch)
    cog = HelpCog(bot)
    talk = mention(bot, "<@999> what do you think?")
    other_bot = mention(bot, "<@999>", is_bot=True)

    await cog.on_message(talk)
    await cog.on_message(other_bot)

    talk.reply.assert_not_awaited()
    other_bot.reply.assert_not_awaited()


async def test_a_member_who_mentions_again_soon_gets_one_reply(
    bot: BotApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    bot_user(bot, monkeypatch)
    cog = HelpCog(bot)
    first, second = mention(bot, "<@!999>"), mention(bot, "<@999>")

    await cog.on_message(first)
    await cog.on_message(second)

    first.reply.assert_awaited_once()
    second.reply.assert_not_awaited()


async def test_without_read_message_history_the_reply_goes_to_the_channel(
    bot: BotApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    bot_user(bot, monkeypatch)
    cog = HelpCog(bot)
    message = mention(bot, "<@999>")
    message.reply.side_effect = discord.Forbidden(
        MagicMock(status=403), "Missing Permissions"
    )

    await cog.on_message(message)

    message.channel.send.assert_awaited_once()
    assert message.channel.send.call_args.args == (EN.mention_reply,)


async def test_the_guide_button_shows_the_guide_privately(bot: BotApp) -> None:
    await bot.add_cog(HelpCog(bot))
    await bot.add_cog(AdminCog(bot))
    cog = bot.cogs["Help"]
    press = make_interaction()
    press.permissions = discord.Permissions.all()
    press.translate.return_value = None

    await GuideButton(cog, EN).show.callback(press)  # type: ignore[arg-type, call-arg]

    kwargs = press.response.send_message.call_args.kwargs
    assert kwargs["ephemeral"] is True
    assert kwargs["embeds"][0].title == EN.help_title
    assert kwargs["embeds"][-1].footer.text == EN.help_footer
