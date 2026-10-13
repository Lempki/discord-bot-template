"""Tests for cogs/info.py."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import discord

from bot import BotApp
from cogs.info import ROLES_SHOWN, InfoCog, when
from localization import LOCALES
from tests.conftest import make_interaction

EN = LOCALES["en"]


def info_interaction(user: MagicMock | None = None) -> MagicMock:
    interaction = make_interaction(user=user)
    interaction.response.send_message = AsyncMock()
    return interaction


def embed_of(interaction: MagicMock) -> discord.Embed:
    kwargs = interaction.response.send_message.call_args.kwargs
    assert kwargs["ephemeral"] is True
    embed: discord.Embed = kwargs["embed"]
    return embed


def fields(embed: discord.Embed) -> dict[str, str]:
    return {str(field.name): str(field.value) for field in embed.fields}


async def test_server_info_shows_age_size_and_boosts(bot: BotApp) -> None:
    cog = InfoCog(bot)
    interaction = info_interaction()
    guild = interaction.guild
    guild.name = "Lähettämö"
    guild.icon = None
    guild.created_at = datetime(2020, 1, 2, tzinfo=UTC)
    guild.owner_id = 7
    guild.member_count = 42
    guild.text_channels = [MagicMock()] * 3
    guild.voice_channels = [MagicMock()] * 2
    guild.roles = [MagicMock()] * 6
    guild.premium_tier = 1
    guild.premium_subscription_count = 4

    await cog.server.callback(cog, interaction)  # type: ignore[arg-type]

    embed = embed_of(interaction)
    assert embed.title == "Lähettämö"
    assert fields(embed) == {
        EN.info_created: when(guild.created_at),
        EN.info_owner: "<@7>",
        EN.info_members: "42",
        EN.info_channels: EN.info_channel_counts.format(text=3, voice=2),
        EN.info_roles: "5",
        EN.info_boosts: EN.info_boost_level.format(level=1, count=4),
    }


def member_with_roles(count: int) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.display_name = "Ada"
    member.mention = "<@5>"
    member.colour = discord.Colour.default()
    member.created_at = datetime(2019, 5, 6, tzinfo=UTC)
    member.joined_at = datetime(2021, 7, 8, tzinfo=UTC)
    member.premium_since = None
    everyone = MagicMock(mention="@everyone")
    everyone.is_default.return_value = True
    roles = []
    for n in range(count):
        role = MagicMock(mention=f"<@&{n}>")
        role.is_default.return_value = False
        roles.append(role)
    # discord.py lists a member's roles lowest first.
    member.roles = [everyone, *roles]
    return member


async def test_member_info_lists_the_highest_roles_first(bot: BotApp) -> None:
    cog = InfoCog(bot)
    member = member_with_roles(ROLES_SHOWN + 2)
    interaction = info_interaction()

    await cog.member.callback(cog, interaction, member)  # type: ignore[arg-type]

    embed = embed_of(interaction)
    shown = fields(embed)
    assert embed.title == "Ada"
    assert shown[EN.info_joined] == when(member.joined_at)
    roles = shown[EN.info_roles].split(" ")
    assert roles[0] == f"<@&{ROLES_SHOWN + 1}>"
    assert "@everyone" not in shown[EN.info_roles]
    assert shown[EN.info_roles].endswith(EN.info_more.format(count=2))


async def test_avatar_shows_the_members_picture_in_full_size(bot: BotApp) -> None:
    cog = InfoCog(bot)
    member = member_with_roles(0)
    image = MagicMock(url="https://cdn.discordapp.com/avatars/5/a.png?size=1024")
    member.display_avatar.with_size.return_value = image
    interaction = info_interaction()

    await cog.avatar.callback(cog, interaction, member)  # type: ignore[arg-type]

    embed = embed_of(interaction)
    member.display_avatar.with_size.assert_called_once_with(1024)
    assert embed.title == EN.info_avatar_title.format(user="Ada")
    assert embed.image.url == image.url
