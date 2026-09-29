"""Issues warnings and applies the warning action, for /warn and for AutoMod alike."""

import logging
from dataclasses import dataclass
from datetime import timedelta

import discord

from utils import database

__all__ = ["MAX_TIMEOUT_MINUTES", "WarningOutcome", "issue_warning"]

log = logging.getLogger(__name__)

# Discord caps a timeout at 28 days.
MAX_TIMEOUT_MINUTES = 28 * 24 * 60


@dataclass(frozen=True)
class WarningOutcome:
    """What issue_warning did.

    Attributes:
        count: The member's warnings in this guild, including the new one.
        threshold: The guild's warning threshold.
        action: "kick", "ban", or "timeout" when the threshold was reached, otherwise None.
        timeout_minutes: The timeout length that applies when action is "timeout".
        error: The Discord error that stopped the action, or None when it succeeded.
    """

    count: int
    threshold: int
    action: str | None = None
    timeout_minutes: int = 0
    error: discord.HTTPException | None = None


async def issue_warning(
    member: discord.Member, moderator_id: int, reason: str | None
) -> WarningOutcome:
    """Records a warning and applies the guild's warning action at the threshold.

    The caller checks the role hierarchy first, because only a command has a moderator to check.

    Args:
        member: The member to warn.
        moderator_id: The member or bot that issued the warning.
        reason: The reason given, or None.

    Returns:
        The warning count and the action that was applied or attempted.
    """
    guild = member.guild
    await database.add_warning(guild.id, member.id, moderator_id, reason)
    count = await database.count_warnings(guild.id, member.id)
    settings = await database.get_settings(guild.id)
    threshold = settings.warn_threshold
    log.info(f"{member} was warned ({count}/{threshold}): {reason}")
    if count < threshold:
        return WarningOutcome(count=count, threshold=threshold)

    action = settings.warn_action
    minutes = min(settings.warn_timeout_minutes, MAX_TIMEOUT_MINUTES)
    audit_reason = f"Warning threshold reached ({count} warnings)"
    try:
        if action == "ban":
            await member.ban(reason=audit_reason)
        elif action == "timeout":
            await member.timeout(timedelta(minutes=minutes), reason=audit_reason)
        else:
            action = "kick"
            await member.kick(reason=audit_reason)
    except discord.HTTPException as error:
        log.warning(f"Could not apply {action} to {member}: {error}")
        return WarningOutcome(count, threshold, action, minutes, error)
    log.info(f"Applied {action} to {member} at the warning threshold.")
    return WarningOutcome(count, threshold, action, minutes)
