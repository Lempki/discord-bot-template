"""Localization support for discord-bot-template.

Usage
-----
Set ``LOCALE=en`` (or ``fi``, or leave blank for silent) in your ``.env``.
The bot attaches the resolved ``Strings`` instance to ``bot.strings`` at startup.

In cogs, use the walrus pattern to send only when a string is configured::

    if msg := self.bot.strings.joined_voice.format(channel=target):
        await reply.send(msg)

Adding a new locale
-------------------
Create a ``Strings`` instance with your translated strings and add it to
``LOCALES`` under a new key (e.g. ``"de"``).  No other code needs to change.
"""
from dataclasses import dataclass


@dataclass
class Strings:
    """All user-facing bot messages.

    Every field defaults to an empty string — the bot says nothing unless a
    locale explicitly sets the string.  Fields use Python str.format() with
    named placeholders documented in the comments below.
    """

    # --- Voice cog ---
    # {user}
    not_in_voice: str = ""
    # {user}
    bot_not_in_voice: str = ""
    # {user}
    already_same_channel: str = ""
    # {channel}
    joined_voice: str = ""
    # {channel}
    moved_voice: str = ""
    # {channel}
    left_voice: str = ""
    skipped: str = ""
    nothing_to_skip: str = ""

    # --- YouTube cog ---
    # {user}
    queued_one: str = ""
    # {count}, {user}
    queued_many: str = ""
    # {title}, {channel}
    now_playing: str = ""
    # {user}
    load_error: str = ""
    # {prefix}
    play_usage: str = ""


# ---------------------------------------------------------------------------
# Built-in locale presets
# ---------------------------------------------------------------------------

SILENT = Strings()  # all empty strings — bot sends no messages

ENGLISH = Strings(
    not_in_voice="You are not in a voice channel, `{user}`.",
    bot_not_in_voice="Not in a voice channel.",
    already_same_channel="Already in your voice channel, `{user}`.",
    joined_voice="Joined `{channel}`.",
    moved_voice="Moved to `{channel}`.",
    left_voice="Left `{channel}`.",
    skipped="Skipped.",
    nothing_to_skip="Nothing to skip.",
    queued_one="Added to queue, `{user}`.",
    queued_many="Added {count} videos to queue, `{user}`.",
    now_playing="Now playing `{title}` in `{channel}`.",
    load_error="Failed to load audio. Try again, `{user}`.",
    play_usage="Provide a URL: `{prefix}play <url>`",
)

#: Map LOCALE env var values to Strings instances.
#: Add your own locale here after creating a Strings(...) instance.
LOCALES: dict[str, Strings] = {
    "silent": SILENT,
    "en": ENGLISH,
}
