"""Chooses a language per user and localizes slash command text.

Replies follow the Discord language of the user who ran the command.
When no translation exists for that language, the bot's LOCALE is used, and English after that.
Command descriptions, option descriptions, and choice names are localized natively by Discord.
Command and option names always stay English, so everyone types the same commands.
"""

from collections.abc import Mapping

import discord
from discord import app_commands
from discord.app_commands import TranslationContextLocation, TranslationContextTypes

from utils.strings import CORE_COMMAND_TEXT, CORE_TEXT, CoreStrings

__all__ = [
    "SILENT",
    "LocaleTranslator",
    "build_locales",
    "merge_command_text",
    "pick_locale",
]

SILENT = "silent"

_NAME_LOCATIONS = frozenset(
    {
        TranslationContextLocation.command_name,
        TranslationContextLocation.group_name,
        TranslationContextLocation.parameter_name,
    }
)


def build_locales[S: CoreStrings](
    strings_cls: type[S], bot_text: Mapping[str, Mapping[str, str]]
) -> dict[str, S]:
    """Builds every locale from the core texts plus a bot's own texts.

    Args:
        strings_cls: The bot's Strings class, which extends CoreStrings.
        bot_text: The bot's texts per language code.
            They override core texts with the same field name.

    Returns:
        One Strings instance per language code, plus an all-empty "silent" locale.
    """
    locales: dict[str, S] = {SILENT: strings_cls()}
    for code in sorted(CORE_TEXT.keys() | bot_text.keys()):
        fields = {**CORE_TEXT.get(code, {}), **bot_text.get(code, {})}
        locales[code] = strings_cls(**fields)
    return locales


def merge_command_text(
    bot_text: Mapping[str, Mapping[str, str]],
) -> dict[str, dict[str, str]]:
    """Combines the core command translations with a bot's own, per language code."""
    merged: dict[str, dict[str, str]] = {}
    for code in CORE_COMMAND_TEXT.keys() | bot_text.keys():
        merged[code] = {**CORE_COMMAND_TEXT.get(code, {}), **bot_text.get(code, {})}
    return merged


def pick_locale[S: CoreStrings](
    available: Mapping[str, S], code: str | None, default: str
) -> S:
    """Returns the best locale for a Discord language code.

    The order is the exact code, then its language part, then the bot's default, then English.
    The language part of en-GB is en.

    Args:
        available: The locales by language code.
        code: The user's or guild's Discord language code, such as "fi" or "en-US".
        default: The bot's configured LOCALE.

    Returns:
        The first match that is not the silent locale, or the silent locale when nothing matches.
    """
    candidates = [code, code.split("-")[0] if code else None, default, "en"]
    for candidate in candidates:
        if candidate and candidate != SILENT and candidate in available:
            return available[candidate]
    return available[SILENT]


class LocaleTranslator(app_commands.Translator):
    """Localizes descriptions and choice names from a table of English texts.

    Args:
        command_text: Translations per language code, keyed by the English text.
    """

    def __init__(self, command_text: Mapping[str, Mapping[str, str]]) -> None:
        self._text = command_text

    async def translate(
        self,
        string: app_commands.locale_str,
        locale: discord.Locale,
        context: TranslationContextTypes,
    ) -> str | None:
        """Returns the translation of one string, or None to keep the English text."""
        if context.location in _NAME_LOCATIONS:
            return None
        table = self._text.get(locale.value) or self._text.get(
            locale.value.split("-")[0]
        )
        return table.get(string.message) if table else None
