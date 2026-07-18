"""Operator-supplied, one-shot editorial notes for an episode."""

import json
import logging
import os
from pathlib import Path

import config

logger = logging.getLogger(__name__)

NOTES_PATH = config.BASE_DIR / "episode_notes.json"


def resolve_episode_note(
    episode_date: str,
    override: str | None = None,
    notes_path: Path = NOTES_PATH,
) -> str:
    """
    Resolve an editorial note for one episode.

    Priority is: explicit CLI value, workflow environment value, then the
    date-keyed notes file. Date-keyed entries naturally expire after that day.
    """
    if override and override.strip():
        return override.strip()

    env_note = os.getenv("EPISODE_SPECIAL_NOTE", "").strip()
    if env_note:
        return env_note

    try:
        notes = json.loads(notes_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ""
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read episode notes from %s: %s", notes_path, exc)
        return ""

    note = notes.get(episode_date, "")
    if isinstance(note, dict):
        note = note.get("note", "")
    return note.strip() if isinstance(note, str) else ""
