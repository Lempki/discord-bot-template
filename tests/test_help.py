"""Tests for cogs/help.py."""

from pathlib import Path

import discord

from bot import BotApp
from cogs.admin import AdminCog
from cogs.help import (
    EMBED_LIMIT,
    FIELD_LIMIT,
    FIELDS_PER_EMBED,
    HelpCog,
    Section,
    build_embeds,
)
from cogs.moderation import ModerationCog
from localization import LOCALES
from tests.conftest import make_interaction, sent_messages
from utils.about import ProjectInfo, read_project_info


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


async def _visible_lines(bot: BotApp, permissions: discord.Permissions) -> list[str]:
    await bot.add_cog(AdminCog(bot))
    await bot.add_cog(ModerationCog(bot))
    await bot.add_cog(HelpCog(bot))
    interaction = make_interaction()
    interaction.permissions = permissions
    interaction.translate.return_value = None
    sections = await bot.cogs["Help"]._sections(interaction)  # type: ignore[attr-defined]
    return [line for section in sections for line in section.lines]


async def test_admin_sees_group_subcommands(bot: BotApp) -> None:
    lines = await _visible_lines(bot, discord.Permissions.all())
    assert any(line.startswith("`/admin channel`") for line in lines)
    assert any(line.startswith("`/admin automod add`") for line in lines)
    assert any(line.startswith("`/ban`") for line in lines)


async def test_regular_member_does_not_see_moderation_commands(bot: BotApp) -> None:
    lines = await _visible_lines(bot, discord.Permissions.none())
    assert [line.split("`")[1] for line in lines] == ["/about", "/help"]


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
