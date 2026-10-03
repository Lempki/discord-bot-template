"""The /help command, which lists the commands the user can run, grouped by cog."""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from utils.replies import respond

if TYPE_CHECKING:
    from bot import BotApp

log = logging.getLogger(__name__)

# Discord's embed limits.
FIELD_LIMIT = 1024
FIELDS_PER_EMBED = 25
EMBED_LIMIT = 6000
EMBEDS_PER_MESSAGE = 10

AnyCommand = app_commands.Command[commands.Cog, ..., object]


@dataclass(frozen=True)
class Section:
    """One cog's visible commands, already formatted as lines."""

    title: str
    lines: list[str]


def _required_permissions(command: AnyCommand) -> discord.Permissions | None:
    """Returns the default permissions of a command or of its nearest parent group."""
    node: AnyCommand | app_commands.Group | None = command
    while node is not None:
        if node.default_permissions is not None:
            return node.default_permissions
        node = node.parent
    return None


def _is_guild_only(command: AnyCommand) -> bool:
    node: AnyCommand | app_commands.Group | None = command
    while node is not None:
        if node.guild_only or (
            node.allowed_contexts is not None and not node.allowed_contexts.dm_channel
        ):
            return True
        node = node.parent
    return False


def _leaf_commands(cog: commands.Cog) -> list[AnyCommand]:
    """Returns every runnable command of a cog, including subcommands of its groups."""
    leaves: list[AnyCommand] = []
    for command in cog.get_app_commands():
        if isinstance(command, app_commands.Group):
            leaves.extend(
                c
                for c in command.walk_commands()
                if isinstance(c, app_commands.Command)
            )
        else:
            leaves.append(command)
    return sorted(leaves, key=lambda c: c.qualified_name)


def build_embeds(
    sections: list[Section], title: str, footer: str
) -> list[discord.Embed]:
    """Packs sections into embeds that respect every Discord embed limit.

    A section longer than one field continues in the next field under the same title.
    """
    embeds: list[discord.Embed] = []
    embed: discord.Embed | None = None
    for section in sections:
        chunks: list[str] = []
        current = ""
        for line in section.lines:
            line = line[:FIELD_LIMIT]
            candidate = f"{current}\n{line}" if current else line
            if len(candidate) > FIELD_LIMIT:
                chunks.append(current)
                candidate = line
            current = candidate
        chunks.append(current)
        for chunk in chunks:
            size = len(section.title) + len(chunk)
            if (
                embed is None
                or len(embed.fields) >= FIELDS_PER_EMBED
                or len(embed) + size > EMBED_LIMIT
            ):
                embed = discord.Embed(
                    colour=discord.Colour.blurple(), title=title or None
                )
                if footer:
                    embed.set_footer(text=footer)
                embeds.append(embed)
            embed.add_field(name=section.title, value=chunk, inline=False)
    return embeds[:EMBEDS_PER_MESSAGE]


class HelpCog(commands.Cog, name="Help"):
    """Lists the loaded commands the user may run, grouped by cog."""

    def __init__(self, bot: "BotApp") -> None:
        self.bot = bot

    async def _sections(self, interaction: discord.Interaction) -> list[Section]:
        s = self.bot.strings_for(interaction, private=True)
        in_guild = interaction.guild is not None
        sections: list[Section] = []
        for cog in sorted(self.bot.cogs.values(), key=lambda c: c.qualified_name):
            lines: list[str] = []
            for command in _leaf_commands(cog):
                required = _required_permissions(command)
                if (
                    in_guild
                    and required is not None
                    and not required <= interaction.permissions
                ):
                    continue
                if not in_guild and _is_guild_only(command):
                    continue
                description = await interaction.translate(command.description)
                lines.append(
                    f"`/{command.qualified_name}` {description or command.description}"
                )
            if lines:
                title = getattr(s, f"section_{cog.qualified_name.lower()}", "")
                sections.append(Section(title or cog.qualified_name, lines))
        return sections

    @app_commands.command(name="help")
    async def help_command(self, interaction: discord.Interaction) -> None:
        """Show the commands you can use here."""
        s = self.bot.strings_for(interaction, private=True)
        sections = await self._sections(interaction)
        if not sections:
            await respond(interaction, s.help_empty, ephemeral=True)
            return
        embeds = build_embeds(sections, s.help_title, s.help_footer)
        await interaction.response.send_message(embeds=embeds, ephemeral=True)

    async def cog_load(self) -> None:
        """Logs that the cog is ready."""
        log.info(f"{self.qualified_name} cog loaded.")


async def setup(bot: "BotApp") -> None:
    """Adds the cog. discord.py calls this when the extension loads."""
    await bot.add_cog(HelpCog(bot))
