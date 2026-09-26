"""Tests for cogs/help.py."""

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
from tests.conftest import make_interaction


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
    assert any(line.startswith("`/ban`") for line in lines)


async def test_regular_member_does_not_see_moderation_commands(bot: BotApp) -> None:
    lines = await _visible_lines(bot, discord.Permissions.none())
    assert [line.split("`")[1] for line in lines] == ["/help"]
