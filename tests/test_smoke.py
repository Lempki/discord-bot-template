"""Imports every cog module, so a broken import fails CI before the bot ever starts."""

import importlib
import pkgutil

import pytest

import cogs

COG_MODULES = sorted(module.name for module in pkgutil.iter_modules(cogs.__path__))


@pytest.mark.parametrize("name", COG_MODULES)
def test_cog_module_imports(name: str) -> None:
    module = importlib.import_module(f"cogs.{name}")
    assert callable(getattr(module, "setup", None)), "Every cog module needs a setup()."
