"""Tests for utils/replies.py."""

from tests.conftest import make_interaction, sent_messages
from utils.replies import finish, mark_replied, respond


async def test_respond_sends_the_first_reply_as_a_response() -> None:
    interaction = make_interaction()
    assert await respond(interaction, "Hello, {name}.", name="Ada") is True
    interaction.response.send_message.assert_awaited_once_with(
        "Hello, Ada.", ephemeral=False
    )


async def test_respond_after_defer_sends_a_follow_up() -> None:
    interaction = make_interaction(deferred=True)
    await respond(interaction, "Done.", ephemeral=True)
    interaction.followup.send.assert_awaited_once_with("Done.", ephemeral=True)


async def test_empty_template_sends_nothing() -> None:
    interaction = make_interaction(deferred=True)
    assert await respond(interaction, "") is False
    assert sent_messages(interaction) == []


async def test_finish_removes_the_thinking_message_when_nothing_was_sent() -> None:
    interaction = make_interaction(deferred=True)
    await respond(interaction, "")
    await finish(interaction)
    interaction.delete_original_response.assert_awaited_once()


async def test_finish_keeps_a_sent_reply() -> None:
    interaction = make_interaction(deferred=True)
    await respond(interaction, "Kept.")
    await finish(interaction)
    interaction.delete_original_response.assert_not_awaited()


async def test_finish_answers_an_undeferred_command_before_deleting() -> None:
    # Discord requires an answer within 3 seconds, so an empty command is deferred and deleted.
    interaction = make_interaction()
    await finish(interaction)
    interaction.response.defer.assert_awaited_once()
    interaction.delete_original_response.assert_awaited_once()


async def test_finish_keeps_a_reply_that_was_marked_by_hand() -> None:
    # A file sent with followup.send bypasses respond(), so the command marks it itself.
    interaction = make_interaction(deferred=True)
    await interaction.followup.send(file=object())
    mark_replied(interaction)
    await finish(interaction)
    interaction.delete_original_response.assert_not_awaited()
