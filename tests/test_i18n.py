"""Tests for utils/i18n.py and for the completeness of every language this bot ships.

The coverage tests read localization.py, so they check each bot's own languages.
They do not only check the template's.
"""

import importlib
import inspect
import pkgutil
from dataclasses import fields
from types import SimpleNamespace

import discord
import pytest
from discord import app_commands
from discord.app_commands import TranslationContextLocation as Location
from discord.ext import commands

import cogs
from localization import COMMAND_TEXT, LOCALES
from utils.i18n import SILENT, LocaleTranslator, build_locales, pick_locale
from utils.strings import CORE_TEXT, CoreStrings

# ---------------------------------------------------------------------------
# Mechanics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "default", "expected"),
    [
        ("fi", "en", "fi"),
        ("en-GB", "fi", "en"),
        ("ja", "fi", "fi"),
        ("ja", "xx", "en"),
        (None, "fi", "fi"),
        ("fi", SILENT, "fi"),
    ],
)
def test_pick_locale_fallback_chain(
    code: str | None, default: str, expected: str
) -> None:
    locales = {
        SILENT: CoreStrings(),
        "en": CoreStrings(ping_reply="en"),
        "fi": CoreStrings(ping_reply="fi"),
    }
    assert pick_locale(locales, code, default) is locales[expected]


def test_build_locales_lets_bot_text_override_core_text() -> None:
    locales = build_locales(
        CoreStrings, {"en": {"ping_reply": "Custom."}, "de": {"paused": "Pausiert."}}
    )
    assert locales["en"].ping_reply == "Custom."
    assert locales["en"].paused == CORE_TEXT["en"]["paused"]
    assert locales["de"].paused == "Pausiert."
    assert locales[SILENT] == CoreStrings()


@pytest.mark.parametrize(
    "location",
    [Location.command_name, Location.group_name, Location.parameter_name],
)
async def test_translator_never_translates_names(location: Location) -> None:
    translator = LocaleTranslator({"fi": {"help": "apua"}})
    context = SimpleNamespace(location=location, data=None)
    result = await translator.translate(
        app_commands.locale_str("help"), discord.Locale.finnish, context
    )  # type: ignore[arg-type]
    assert result is None


async def test_translator_translates_descriptions_by_language_part() -> None:
    translator = LocaleTranslator({"en": {"Join.": "Join!"}})
    context = SimpleNamespace(location=Location.command_description, data=None)
    result = await translator.translate(
        app_commands.locale_str("Join."),
        discord.Locale.british_english,
        context,  # type: ignore[arg-type]
    )
    assert result == "Join!"


# ---------------------------------------------------------------------------
# Coverage of this bot's languages.
# ---------------------------------------------------------------------------


def _command_texts() -> list[str]:
    """Collects every description, option description, and choice name of every cog."""
    texts: list[str] = []
    for module_info in pkgutil.iter_modules(cogs.__path__):
        module = importlib.import_module(f"cogs.{module_info.name}")
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if not issubclass(cls, commands.Cog) or cls.__module__ != module.__name__:
                continue
            for command in cls.__cog_app_commands__:
                nodes = [command]
                if isinstance(command, app_commands.Group):
                    nodes += list(command.walk_commands())
                for node in nodes:
                    texts.append(node.description)
                    if isinstance(node, app_commands.Command):
                        for parameter in node.parameters:
                            texts.append(parameter.description)
                            texts += [choice.name for choice in parameter.choices]
    return list(dict.fromkeys(texts))


@pytest.mark.parametrize("code", [code for code in LOCALES if code != SILENT])
def test_every_language_defines_every_message(code: str) -> None:
    strings = LOCALES[code]
    optional = {"help_footer"}
    missing = [
        f.name
        for f in fields(strings)
        if not getattr(strings, f.name) and f.name not in optional
    ]
    assert missing == [], f"Language '{code}' has no text for: {', '.join(missing)}"


def test_every_command_text_is_described_and_short() -> None:
    texts = _command_texts()
    assert "…" not in texts, "An option is missing @app_commands.describe."
    assert [t for t in texts if len(t) > 100] == []


@pytest.mark.parametrize("code", sorted(COMMAND_TEXT))
def test_every_command_text_is_translated(code: str) -> None:
    table = COMMAND_TEXT[code]
    missing = [text for text in _command_texts() if text not in table]
    assert missing == [], f"Language '{code}' lacks command translations for: {missing}"
    assert [t for t in table.values() if len(t) > 100] == []
