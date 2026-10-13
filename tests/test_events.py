"""Tests for cogs/events.py, which greets new members and gives them the auto-role."""

from unittest.mock import AsyncMock, MagicMock

import discord

from bot import BotApp
from cogs.events import EventsCog
from localization import LOCALES
from tests.conftest import GUILD_ID
from utils import database

EN = LOCALES["en"]


def joining_member(*roles: discord.Role) -> MagicMock:
    """A member who just joined a guild that has the given roles and a bot channel 30."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = GUILD_ID
    guild.preferred_locale = discord.Locale.american_english
    guild.roles = list(roles)
    guild.get_role = MagicMock(
        side_effect=lambda role_id: next((r for r in roles if r.id == role_id), None)
    )
    channel = MagicMock(spec=discord.TextChannel)
    channel.name = "bot"
    channel.send = AsyncMock()
    guild.get_channel = MagicMock(return_value=channel)
    member = MagicMock(spec=discord.Member)
    member.guild = guild
    member.mention = "<@5>"
    member.add_roles = AsyncMock()
    return member


def role(role_id: int, name: str) -> MagicMock:
    made = MagicMock(spec=discord.Role)
    made.id = role_id
    made.name = name
    return made


async def test_a_new_member_gets_the_auto_role_and_a_welcome(
    db: None, bot: BotApp
) -> None:
    member_role = role(11, "Members")
    await database.upsert_settings(GUILD_ID, auto_role_id=11, bot_channel_id=30)
    member = joining_member(member_role)

    await EventsCog(bot).on_member_join(member)

    member.add_roles.assert_awaited_once_with(member_role)
    channel = member.guild.get_channel.return_value
    channel.send.assert_awaited_once_with(EN.member_join_welcome.format(member="<@5>"))


async def test_an_auto_role_stored_by_name_is_upgraded_to_its_id(
    db: None, bot: BotApp
) -> None:
    member_role = role(11, "Members")
    await database.upsert_settings(GUILD_ID, auto_role_name="Members")

    await EventsCog(bot).on_member_join(joining_member(member_role))

    settings = await database.get_settings(GUILD_ID)
    assert (settings.auto_role_id, settings.auto_role_name) == (11, None)


async def test_without_settings_nothing_happens(db: None, bot: BotApp) -> None:
    member = joining_member(role(11, "Members"))

    await EventsCog(bot).on_member_join(member)

    member.add_roles.assert_not_awaited()
    member.guild.get_channel.return_value.send.assert_not_awaited()


async def test_a_role_the_bot_may_not_give_still_lets_the_welcome_through(
    db: None, bot: BotApp
) -> None:
    await database.upsert_settings(GUILD_ID, auto_role_id=11, bot_channel_id=30)
    member = joining_member(role(11, "Members"))
    member.add_roles.side_effect = discord.Forbidden(MagicMock(status=403), "Missing")

    await EventsCog(bot).on_member_join(member)

    member.guild.get_channel.return_value.send.assert_awaited_once()
