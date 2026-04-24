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

    # --- General ---
    bot_channel_only: str = ""

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

    # --- Media cog ---
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
    stopped: str = ""
    paused: str = ""
    resumed: str = ""

    # --- Help cog ---
    help_title: str = ""
    # optional tagline shown in the embed footer
    help_footer: str = ""

    # --- Admin cog ---
    # {channel}
    admin_channel_set: str = ""
    admin_channel_cleared: str = ""
    # {role}
    admin_autorole_set: str = ""
    admin_autorole_cleared: str = ""
    # {count}
    admin_threshold_set: str = ""
    # {action}
    admin_action_set: str = ""
    # {channel}, {autorole}, {threshold}, {action}
    admin_status: str = ""

    # --- Moderation cog ---
    # {user}, {count}, {threshold}
    warn_issued: str = ""
    # {user}, {action}
    warn_threshold_reached: str = ""
    # {user}, {action}, {error}
    warn_action_failed: str = ""
    # {user}, {count}
    warnings_list_header: str = ""
    # {id}, {reason}, {date}
    warnings_list_entry: str = ""
    # {user}
    warnings_none: str = ""
    # {user}, {count}
    warnings_cleared: str = ""
    # {id}
    warning_removed: str = ""
    # {id}
    warning_not_found: str = ""
    # {user}
    kick_success: str = ""
    # {user}
    ban_success: str = ""
    # {user}, {action}, {error}
    mod_action_failed: str = ""

    # --- Events cog ---
    # {member}
    member_join_welcome: str = ""


# ---------------------------------------------------------------------------
# Built-in locale presets
# ---------------------------------------------------------------------------

SILENT = Strings()  # all empty strings — bot sends no messages

ENGLISH = Strings(
    bot_channel_only="This command can only be used in the designated bot channel.",
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
    stopped="Stopped and cleared the queue.",
    paused="Paused.",
    resumed="Resumed.",
    help_title="Commands",
    admin_channel_set="Bot channel set to {channel}.",
    admin_channel_cleared="Bot channel restriction removed.",
    admin_autorole_set="Auto-role set to **{role}**.",
    admin_autorole_cleared="Auto-role cleared.",
    admin_threshold_set="Warning threshold set to {count}.",
    admin_action_set="Warning action set to **{action}**.",
    admin_status="**Bot settings**\nChannel: {channel}\nAuto-role: {autorole}\nWarn threshold: {threshold}\nWarn action: {action}",
    warn_issued="⚠️ **{user}** warned ({count}/{threshold}).",
    warn_threshold_reached="🚨 Threshold reached — **{user}** will be **{action}**ed.",
    warn_action_failed="Failed to {action} **{user}**: {error}",
    warnings_list_header="**Warnings for {user}** ({count} total)",
    warnings_list_entry="`#{id}` — {reason} _({date})_",
    warnings_none="No warnings on record for **{user}**.",
    warnings_cleared="Cleared {count} warning(s) for **{user}**.",
    warning_removed="Warning `#{id}` removed.",
    warning_not_found="Warning `#{id}` not found.",
    kick_success="**{user}** has been kicked.",
    ban_success="**{user}** has been banned.",
    mod_action_failed="Could not {action} **{user}**: {error}",
    member_join_welcome="Welcome, {member}! 👋",
)

#: Map LOCALE env var values to Strings instances.
#: Add your own locale here after creating a Strings(...) instance.
LOCALES: dict[str, Strings] = {
    "silent": SILENT,
    "en": ENGLISH,
}
