# -*- coding: utf-8 -*-
"""Reading and writing environment variables.

Persistence strategy (two layers):

1. **envs.json** – canonical store, survives process restarts.
2. **os.environ** – injected into the current Python process so that
   ``os.getenv()`` and child subprocesses (``subprocess.run``, etc.)
   can read them immediately.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from copaw.constant import WORKING_DIR

logger = logging.getLogger(__name__)

# Legacy path (inside package directory, no longer used for writing)
_LEGACY_ENVS_DIR = Path(__file__).resolve().parent
_LEGACY_ENVS_JSON = _LEGACY_ENVS_DIR / "envs.json"

# New path (in working directory for persistence)
_ENVS_JSON = WORKING_DIR / "envs.json"


def get_envs_json_path() -> Path:
    """Return the default envs.json path."""
    return _ENVS_JSON


def _migrate_legacy_envs_json() -> None:
    """Migrate envs.json from package dir to working dir if needed.

    This handles the transition from storing envs.json inside the
    Python package (which gets reset on Docker rebuild) to the working
    directory (which can be persisted via volume mounts).
    """
    if _ENVS_JSON.exists():
        return

    if _LEGACY_ENVS_JSON.exists():
        try:
            _ENVS_JSON.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_LEGACY_ENVS_JSON, _ENVS_JSON)
            logger.info(
                "Migrated envs.json from %s to %s",
                _LEGACY_ENVS_JSON,
                _ENVS_JSON,
            )
        except Exception as e:
            logger.warning(
                "Failed to migrate envs.json: %s. "
                "Will create a new one in working directory.",
                e,
            )


# ------------------------------------------------------------------
# os.environ helpers
# ------------------------------------------------------------------


def _apply_to_environ(envs: dict[str, str]) -> None:
    """Set every key/value into ``os.environ``."""
    for key, value in envs.items():
        os.environ[key] = value


def _remove_from_environ(key: str) -> None:
    """Remove *key* from ``os.environ`` if present."""
    os.environ.pop(key, None)


def _sync_environ(
    old: dict[str, str],
    new: dict[str, str],
) -> None:
    """Synchronise ``os.environ``: set *new*, remove stale *old*."""
    for key in old:
        if key not in new:
            _remove_from_environ(key)
    _apply_to_environ(new)


# ------------------------------------------------------------------
# JSON persistence
# ------------------------------------------------------------------


def load_envs(
    path: Optional[Path] = None,
) -> dict[str, str]:
    """Load env vars from envs.json."""
    if path is None:
        # Try to migrate from legacy location before using new path
        _migrate_legacy_envs_json()
        path = get_envs_json_path()
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return {k: str(v) for k, v in data.items()}
    except (json.JSONDecodeError, ValueError):
        pass
    return {}


def save_envs(
    envs: dict[str, str],
    path: Optional[Path] = None,
) -> None:
    """Write env vars to envs.json and sync to ``os.environ``."""
    old = load_envs(path)

    if path is None:
        path = get_envs_json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(envs, fh, indent=2, ensure_ascii=False)

    _sync_environ(old, envs)


def set_env_var(
    key: str,
    value: str,
) -> dict[str, str]:
    """Set a single env var. Returns updated dict."""
    envs = load_envs()
    envs[key] = value
    save_envs(envs)
    return envs


def delete_env_var(key: str) -> dict[str, str]:
    """Delete a single env var. Returns updated dict."""
    envs = load_envs()
    envs.pop(key, None)
    save_envs(envs)
    return envs


def load_envs_into_environ() -> dict[str, str]:
    """Load envs.json and apply all entries to ``os.environ``.

    Call this once at application startup so that environment
    variables persisted from a previous session are available
    immediately.
    """
    envs = load_envs()
    _apply_to_environ(envs)
    return envs
