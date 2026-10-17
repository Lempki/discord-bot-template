"""The /help command, a short guide to the bot's features, and /about.

A message that only mentions the bot gets a short reply with a button that opens the same guide.
"""

import contextlib
import logging
import math
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from utils import database
from utils.replies import respond

if TYPE_CHECKING:
    from bot import BotApp
    from localization import Strings

log = logging.getLogger(__name__)

# Discord's embed limits.
FIELD_LIMIT = 1024
FIELDS_PER_EMBED = 25
EMBED_LIMIT = 6000
EMBEDS_PER_MESSAGE = 10

AnyCommand = app_commands.Command[commands.Cog, ..., object]

# The guide shows the core features in this order, after the bot's own features.
# The help cog itself has no section, because the guide is what /help shows.
CORE_ORDER = ("media", "voice", "info", "moderation", "admin", "template")

# The reply to a mention deletes itself after this long, so it does not stay in the chat.
MENTION_REPLY_SECONDS = 60

# A member who mentions the bot again within this long gets no second reply.
MENTION_COOLDOWN_SECONDS = 30


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


def _milliseconds(seconds: float) -> str:
    """Shows a latency in milliseconds, or a question mark before the first heartbeat answers."""
    return str(round(seconds * 1000)) if math.isfinite(seconds) else "?"


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


def _feature_order(cog: commands.Cog) -> tuple[int, str]:
    """Sorts the bot's own features first, then the core features in CORE_ORDER."""
    name = cog.qualified_name.lower()
    rank = CORE_ORDER.index(name) + 1 if name in CORE_ORDER else 0
    return rank, name


class HelpCog(commands.Cog, name="Help"):
    """Explains the loaded features that the user may use, with their commands."""

    def __init__(self, bot: "BotApp") -> None:
        self.bot = bot
        # When each member last got a reply to a mention.
        self._mentioned: dict[int, float] = {}

    async def _sections(self, interaction: discord.Interaction) -> list[Section]:
        s = self.bot.strings_for(interaction, private=True)
        in_guild = interaction.guild is not None
        sections: list[Section] = []
        for cog in sorted(self.bot.cogs.values(), key=_feature_order):
            if cog is self:
                # /help would explain itself, and the footer names /about instead.
                continue
            visible: list[AnyCommand] = []
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
                visible.append(command)
            if not visible:
                # A feature that the member cannot use, such as moderation, stays out.
                continue
            name = cog.qualified_name.lower()
            guide: str = getattr(s, f"guide_{name}", "")
            if guide:
                # A group such as /music counts once, so the line stays short.
                roots = list(
                    dict.fromkeys(c.qualified_name.split()[0] for c in visible)
                )
                commands_line = s.help_commands.format(
                    commands=", ".join(f"`/{root}`" for root in roots)
                )
                lines = [guide, commands_line] if commands_line else [guide]
            else:
                # A feature without a guide text lists its commands, so it never goes missing.
                lines = []
                for command in visible:
                    description = await interaction.translate(command.description)
                    lines.append(
                        f"`/{command.qualified_name}` {description or command.description}"
                    )
            title = getattr(s, f"section_{name}", "")
            sections.append(Section(title or cog.qualified_name, lines))
        return sections

    async def _introduction(self, interaction: discord.Interaction) -> str:
        """Says what the bot is for, and where its commands work when a server limits them."""
        s = self.bot.strings_for(interaction, private=True)
        lines = [s.help_intro]
        if interaction.guild is not None:
            try:
                settings = await database.get_settings(interaction.guild.id)
            except Exception as error:
                log.info(f"Could not read the bot channel for the guide: {error!r}")
            else:
                if settings.bot_channel_id:
                    channel = f"<#{settings.bot_channel_id}>"
                    lines.append(s.help_bot_channel.format(channel=channel))
        return "\n\n".join(line for line in lines if line)

    @app_commands.command(name="help")
    async def help_command(self, interaction: discord.Interaction) -> None:
        """Show a short guide to the bot and the commands you can use here."""
        await self.send_guide(interaction)

    async def send_guide(self, interaction: discord.Interaction) -> None:
        """Shows the guide privately, for /help and the button under a reply to a mention."""
        s = self.bot.strings_for(interaction, private=True)
        sections = await self._sections(interaction)
        if not sections:
            await respond(interaction, s.help_empty, ephemeral=True)
            return
        embeds = build_embeds(sections, s.help_title, s.help_footer)
        if introduction := await self._introduction(interaction):
            embeds[0].description = introduction
        await interaction.response.send_message(embeds=embeds, ephemeral=True)

    @app_commands.command(name="about")
    async def about(self, interaction: discord.Interaction) -> None:
        """Show the bot's version, how long it has been online, and its response time."""
        s = self.bot.strings_for(interaction, private=True)
        project = self.bot.project
        lines = [
            s.about_text.format(
                name=project.name,
                version=project.version,
                since=discord.utils.format_dt(self.bot.started_at, "R"),
                latency=_milliseconds(self.bot.latency),
                servers=len(self.bot.guilds),
            )
        ]
        if project.repository:
            lines.append(s.about_link.format(url=project.repository))
        # Placeholders are filled already, so braces in the values must stay as they are.
        message = "\n".join(line for line in lines if line)
        await respond(
            interaction,
            message.replace("{", "{{").replace("}", "}}"),
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Answers a message that only mentions the bot with a button that opens the guide.

        Discord gives a bot the text of a message that mentions it, without Message Content.
        A mention with other words gets no answer, because it may be meant for people.
        """
        user = self.bot.user
        if user is None or message.author.bot or message.guild is None:
            return
        if message.content.strip() not in (f"<@{user.id}>", f"<@!{user.id}>"):
            return
        now = time.monotonic()
        # Expired cooldowns go, so the record never grows past the members of the last half minute.
        self._mentioned = {
            member: at
            for member, at in self._mentioned.items()
            if now - at < MENTION_COOLDOWN_SECONDS
        }
        last = self._mentioned.get(message.author.id)
        if last is not None and now - last < MENTION_COOLDOWN_SECONDS:
            return
        self._mentioned[message.author.id] = now
        # The member asked, and the reply deletes itself, so it is sent even under LOCALE=silent.
        s = self.bot.strings_for(message.guild, private=True)
        if not s.mention_reply:
            return
        view = GuideButton(self, s)
        try:
            await message.reply(
                s.mention_reply,
                view=view,
                mention_author=False,
                delete_after=MENTION_REPLY_SECONDS,
            )
        except discord.Forbidden:
            # A reply needs Read Message History, so a bot without it answers in the channel.
            with contextlib.suppress(discord.HTTPException):
                await message.channel.send(
                    s.mention_reply, view=view, delete_after=MENTION_REPLY_SECONDS
                )
        except discord.HTTPException as error:
            log.info(f"Could not answer a mention in {message.guild.id}: {error!r}")

    async def cog_load(self) -> None:
        """Logs that the cog is ready."""
        log.info(f"{self.qualified_name} cog loaded.")


class GuideButton(discord.ui.View):
    """The button under a reply to a mention, which opens the guide for whoever presses it."""

    def __init__(self, cog: HelpCog, s: "Strings") -> None:
        super().__init__(timeout=MENTION_REPLY_SECONDS)
        self.cog = cog
        self.show.label = s.mention_button or None

    @discord.ui.button(emoji="📖", style=discord.ButtonStyle.primary)
    async def show(
        self, interaction: discord.Interaction, _: discord.ui.Button["GuideButton"]
    ) -> None:
        """Shows the guide privately, in the presser's own language."""
        await self.cog.send_guide(interaction)


async def setup(bot: "BotApp") -> None:
    """Adds the cog. discord.py calls this when the extension loads."""
    await bot.add_cog(HelpCog(bot))
