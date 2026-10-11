"""Reads the bot's name, version, and repository link from its pyproject.toml.

The file ships in the Docker image too, so /about shows the release that actually runs.
"""

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path

__all__ = ["ProjectInfo", "read_project_info"]

log = logging.getLogger(__name__)

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


@dataclass(frozen=True)
class ProjectInfo:
    """What /about tells about the bot.

    Attributes:
        name: The project name, such as discord-bot-morshu.
        version: The release version, such as 2.5.0.
        repository: The link to the source code, or None when the project names none.
    """

    name: str
    version: str
    repository: str | None = None


def read_project_info(path: Path = PYPROJECT) -> ProjectInfo:
    """Reads the project table of pyproject.toml.

    Returns:
        The project's details, or placeholders when the file is missing or broken.
    """
    try:
        project = tomllib.loads(path.read_text(encoding="utf-8")).get("project", {})
    except (OSError, tomllib.TOMLDecodeError) as error:
        log.warning(f"Could not read {path.name}: {error}")
        project = {}
    urls = project.get("urls", {})
    return ProjectInfo(
        name=str(project.get("name", "bot")),
        version=str(project.get("version", "unknown")),
        repository=urls.get("Repository") if isinstance(urls, dict) else None,
    )
