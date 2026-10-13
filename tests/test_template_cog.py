"""Tests for cogs/template.py, the starting point for new features."""

from bot import BotApp
from cogs.template import TemplateCog
from localization import LOCALES
from tests.conftest import make_interaction, sent_messages


async def test_the_example_command_says_hello_privately(bot: BotApp) -> None:
    cog = TemplateCog(bot)
    interaction = make_interaction()

    await cog.hello.callback(cog, interaction)  # type: ignore[arg-type]

    assert sent_messages(interaction) == [LOCALES["en"].example_hello]
    assert interaction.response.send_message.call_args.kwargs["ephemeral"] is True
