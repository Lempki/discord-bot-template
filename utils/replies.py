"""Sends command replies and cleans up deferred responses that end without one.

A slash command that defers shows "is thinking..." until it replies.
When the active language has no text for a reply, nothing is sent.
The thinking message then has to be removed instead.
"""

import contextlib
from typing import Any

import discord

__all__ = ["finish", "mark_replied", "respond"]

_REPLIED = "replied"


async def respond(
    interaction: discord.Interaction,
    template: str,
    *,
    ephemeral: bool = False,
    **values: Any,
) -> bool:
    """Formats a message and sends it as the reply or as a follow-up.

    Args:
        interaction: The interaction to answer.
        template: The message with {placeholders}. An empty template sends nothing.
        ephemeral: Whether only the user who ran the command sees the message.
        **values: The placeholder values.

    Returns:
        True if a message was sent.
    """
    message = template.format(**values) if template else ""
    if not message:
        return False
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(message, ephemeral=ephemeral)
    interaction.extras[_REPLIED] = True
    return True


def mark_replied(interaction: discord.Interaction) -> None:
    """Records a reply sent without respond(), such as a follow-up with a file.

    Without it, a later finish() would treat the command as unanswered and delete that reply.
    """
    interaction.extras[_REPLIED] = True


async def finish(interaction: discord.Interaction) -> None:
    """Removes the "is thinking..." message of a deferred command that never replied.

    Call it at the end of every command that defers.
    It does nothing when the command already replied.
    """
    if interaction.extras.get(_REPLIED):
        return
    if not interaction.response.is_done():
        # A command must answer within 3 seconds, so an empty reply is replaced by a deleted one.
        await interaction.response.defer(ephemeral=True)
    with contextlib.suppress(discord.HTTPException):
        await interaction.delete_original_response()
