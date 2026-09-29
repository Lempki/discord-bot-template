"""Manages the Discord AutoMod rules that this bot owns.

Discord does the filtering. The bot only creates and edits rules through the API.
The bot owns at most one keyword rule and one preset rule per guild.
It recognizes them by creator_id, so rules made in Server Settings are never changed.
Managing rules needs the Manage Server permission.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import discord

__all__ = [
    "KEYWORD_LENGTH",
    "KEYWORD_LIMIT",
    "PRESETS",
    "AutoModState",
    "KeywordLimitError",
    "add_keywords",
    "fetch_state",
    "parse_keywords",
    "remove_keywords",
    "set_alert_channel",
    "set_preset",
]

# Discord's limits for one keyword rule.
KEYWORD_LIMIT = 1000
KEYWORD_LENGTH = 60

# The preset categories of a KEYWORD_PRESET rule, by their AutoModPresets flag name.
PRESETS = ("profanity", "sexual_content", "slurs")

_KEYWORD = discord.AutoModRuleTriggerType.keyword
_PRESET = discord.AutoModRuleTriggerType.keyword_preset
_ALERT = discord.AutoModRuleActionType.send_alert_message


class KeywordLimitError(ValueError):
    """Raised when a change would give the keyword rule more than KEYWORD_LIMIT keywords."""


@dataclass(frozen=True)
class AutoModState:
    """The bot's own AutoMod rules in one guild.

    Attributes:
        keywords: The keywords of the bot's keyword rule, empty when it has none.
        presets: The enabled preset categories of the bot's preset rule.
    """

    keywords: list[str]
    presets: list[str]


def parse_keywords(text: str) -> list[str]:
    """Splits a comma-separated list into distinct lowercase keywords.

    Discord matches keywords without regard to case, so lowercase keeps duplicates out.
    The * wildcard is kept as it is.

    Args:
        text: The keywords as the user typed them.

    Returns:
        The keywords in their first-seen order, without empty entries.
    """
    parts = (part.strip().lower() for part in text.replace("\n", ",").split(","))
    return list(dict.fromkeys(part for part in parts if part))


def _own_rule(
    rules: Iterable[discord.AutoModRule],
    owner_id: int,
    trigger_type: discord.AutoModRuleTriggerType,
) -> discord.AutoModRule | None:
    """Returns the bot's rule of one trigger type, or None when it has none."""
    for rule in rules:
        if rule.creator_id == owner_id and rule.trigger.type == trigger_type:
            return rule
    return None


def _new_actions(alert_channel_id: int | None) -> list[discord.AutoModRuleAction]:
    """Returns the actions of a new rule: block the message, and alert when a channel is set."""
    actions = [
        discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)
    ]
    if alert_channel_id is not None:
        actions.append(discord.AutoModRuleAction(channel_id=alert_channel_id))
    return actions


def _enabled_presets(presets: discord.AutoModPresets) -> list[str]:
    return [name for name in PRESETS if getattr(presets, name)]


async def fetch_state(guild: discord.Guild, owner_id: int) -> AutoModState:
    """Reads the bot's own rules in a guild.

    Args:
        guild: The guild to read.
        owner_id: The bot's user ID.

    Raises:
        discord.Forbidden: When the bot lacks the Manage Server permission.
    """
    rules = await guild.fetch_automod_rules()
    keyword_rule = _own_rule(rules, owner_id, _KEYWORD)
    preset_rule = _own_rule(rules, owner_id, _PRESET)
    return AutoModState(
        keywords=list(keyword_rule.trigger.keyword_filter) if keyword_rule else [],
        presets=_enabled_presets(preset_rule.trigger.presets) if preset_rule else [],
    )


async def add_keywords(
    guild: discord.Guild,
    owner: discord.abc.User,
    keywords: Sequence[str],
    alert_channel_id: int | None,
) -> list[str]:
    """Adds keywords to the bot's keyword rule and creates the rule when it does not exist.

    Args:
        guild: The guild to change.
        owner: The bot's user, whose name labels the rule in Server Settings.
        keywords: The keywords to add, already parsed and checked for length.
        alert_channel_id: The alert channel for a newly created rule, or None.

    Returns:
        Every keyword of the rule after the change.

    Raises:
        KeywordLimitError: When the rule would exceed KEYWORD_LIMIT keywords.
        discord.HTTPException: When Discord refuses the change.
    """
    rule = _own_rule(await guild.fetch_automod_rules(), owner.id, _KEYWORD)
    current = list(rule.trigger.keyword_filter) if rule else []
    combined = list(dict.fromkeys([*current, *keywords]))
    if len(combined) > KEYWORD_LIMIT:
        raise KeywordLimitError(f"The rule would have {len(combined)} keywords.")
    if rule is None:
        await guild.create_automod_rule(
            name=f"{owner.name} keyword filter",
            event_type=discord.AutoModRuleEventType.message_send,
            trigger=discord.AutoModTrigger(type=_KEYWORD, keyword_filter=combined),
            actions=_new_actions(alert_channel_id),
            enabled=True,
        )
    elif combined != current:
        # Keep the allow list and regex patterns an admin may have added in Server Settings.
        await rule.edit(
            trigger=discord.AutoModTrigger(
                type=_KEYWORD,
                keyword_filter=combined,
                regex_patterns=list(rule.trigger.regex_patterns),
                allow_list=list(rule.trigger.allow_list),
            )
        )
    return combined


async def remove_keywords(
    guild: discord.Guild, owner_id: int, keywords: Sequence[str]
) -> list[str]:
    """Removes keywords from the bot's keyword rule and deletes the rule once it is empty.

    Args:
        guild: The guild to change.
        owner_id: The bot's user ID.
        keywords: The keywords to remove.

    Returns:
        The keywords that remain.

    Raises:
        discord.HTTPException: When Discord refuses the change.
    """
    rule = _own_rule(await guild.fetch_automod_rules(), owner_id, _KEYWORD)
    if rule is None:
        return []
    current = list(rule.trigger.keyword_filter)
    removed = set(keywords)
    remaining = [keyword for keyword in current if keyword not in removed]
    if not remaining and not rule.trigger.regex_patterns:
        await rule.delete()
    elif remaining != current:
        await rule.edit(
            trigger=discord.AutoModTrigger(
                type=_KEYWORD,
                keyword_filter=remaining,
                regex_patterns=list(rule.trigger.regex_patterns),
                allow_list=list(rule.trigger.allow_list),
            )
        )
    return remaining


async def set_preset(
    guild: discord.Guild,
    owner: discord.abc.User,
    preset: str,
    enabled: bool,
    alert_channel_id: int | None,
) -> list[str]:
    """Turns one preset category of the bot's preset rule on or off.

    The rule is created for the first category and deleted when none remain.

    Args:
        guild: The guild to change.
        owner: The bot's user, whose name labels the rule in Server Settings.
        preset: One of PRESETS.
        enabled: Whether the category should be filtered.
        alert_channel_id: The alert channel for a newly created rule, or None.

    Returns:
        The enabled categories after the change.

    Raises:
        ValueError: When preset is not one of PRESETS.
        discord.HTTPException: When Discord refuses the change.
            A guild allows only one preset rule, so a rule made in Server Settings blocks this one.
    """
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset: {preset}.")
    rule = _own_rule(await guild.fetch_automod_rules(), owner.id, _PRESET)
    current = _enabled_presets(rule.trigger.presets) if rule else []
    wanted = [
        name
        for name in PRESETS
        if (name == preset and enabled) or (name != preset and name in current)
    ]
    if wanted == current:
        return current
    presets = discord.AutoModPresets(**dict.fromkeys(wanted, True))
    if rule is None:
        await guild.create_automod_rule(
            name=f"{owner.name} preset filter",
            event_type=discord.AutoModRuleEventType.message_send,
            trigger=discord.AutoModTrigger(type=_PRESET, presets=presets),
            actions=_new_actions(alert_channel_id),
            enabled=True,
        )
    elif not wanted:
        await rule.delete()
    else:
        await rule.edit(
            trigger=discord.AutoModTrigger(
                type=_PRESET,
                presets=presets,
                allow_list=list(rule.trigger.allow_list),
            )
        )
    return wanted


async def set_alert_channel(
    guild: discord.Guild, owner_id: int, channel_id: int | None
) -> int:
    """Points the alert action of every rule the bot owns at a channel, or removes it.

    Other actions, such as a timeout an admin added in Server Settings, are kept.

    Args:
        guild: The guild to change.
        owner_id: The bot's user ID.
        channel_id: The alert channel, or None to stop alerts.

    Returns:
        How many rules were updated.

    Raises:
        discord.HTTPException: When Discord refuses the change.
    """
    updated = 0
    for rule in await guild.fetch_automod_rules():
        if rule.creator_id != owner_id:
            continue
        actions = [action for action in rule.actions if action.type != _ALERT]
        if channel_id is not None:
            actions.append(discord.AutoModRuleAction(channel_id=channel_id))
        await rule.edit(actions=actions)
        updated += 1
    return updated
