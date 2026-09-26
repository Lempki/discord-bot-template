"""This bot's messages and command translations, layered on top of the core ones.

The core cogs' messages live in utils/strings.py in English and Finnish.
This file adds the bot's own messages and may override any core text.
Overrides are how a bot gets its own voice.
Replies follow each user's Discord language.
LOCALE in .env picks the fallback language, and LOCALE=silent mutes public replies.

To add a language, add its Discord locale code to BOT_TEXT and COMMAND_TEXT.
Examples of codes are "de" and "sv-SE".
Any core text a language leaves out falls back to silence, and a test lists the gaps.
"""

from dataclasses import dataclass

from utils.i18n import build_locales, merge_command_text
from utils.strings import CoreStrings

__all__ = ["COMMAND_TEXT", "LOCALES", "Strings"]


@dataclass(frozen=True)
class Strings(CoreStrings):
    """The core messages plus this bot's own. Add a field here for every new message."""


# This bot's texts per language code. They override core texts that share a field name.
BOT_TEXT: dict[str, dict[str, str]] = {
    "en": {},
    "fi": {},
}

# Translations of this bot's own command descriptions, keyed by the English text.
BOT_COMMAND_TEXT: dict[str, dict[str, str]] = {
    "fi": {},
}

LOCALES = build_locales(Strings, BOT_TEXT)
COMMAND_TEXT = merge_command_text(BOT_COMMAND_TEXT)
