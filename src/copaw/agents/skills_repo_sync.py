# -*- coding: utf-8 -*-
"""Sync skills from a Git repository.

This module provides functionality to sync skills from a configured Git repository
to the customized_skills directory. Configuration is done via environment variables:

- COPAW_SKILLS_REPO_URL: Git repository URL (required)
- COPAW_SKILLS_REPO_TOKEN: GitHub PAT for private repos (optional)
- COPAW_SKILLS_REPO_BRANCH: Branch name (optional, default: main)
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

from ..constant import CUSTOMIZED_SKILLS_DIR, WORKING_DIR

logger = logging.getLogger(__name__)

# Environment variable names
ENV_REPO_URL = "COPAW_SKILLS_REPO_URL"
ENV_REPO_TOKEN = "COPAW_SKILLS_REPO_TOKEN"
ENV_REPO_BRANCH = "COPAW_SKILLS_REPO_BRANCH"

# Default branch
DEFAULT_BRANCH = "main"

# Directory name for the cloned repo inside working dir
REPO_DIR_NAME = "skills_repo"


class RepoConfig(NamedTuple):
    """Configuration for skills repository."""

    url: str
    token: str | None
    branch: str


class SyncResult(NamedTuple):
    """Result of a sync operation."""

    success: bool
    added: list[str]
    updated: list[str]
    removed: list[str]
    message: str


def get_repo_config() -> RepoConfig | None:
    """Get repository configuration from environment variables.

    Returns:
        RepoConfig if URL is set, None otherwise.
    """
    url = os.environ.get(ENV_REPO_URL, "").strip()
    if not url:
        return None

    token = os.environ.get(ENV_REPO_TOKEN, "").strip() or None
    branch = os.environ.get(ENV_REPO_BRANCH, "").strip() or DEFAULT_BRANCH

    return RepoConfig(url=url, token=token, branch=branch)


def _get_repo_dir() -> Path:
    """Get the path to the cloned repository directory."""
    return WORKING_DIR / REPO_DIR_NAME


def _build_auth_url(url: str, token: str | None) -> str:
    """Build authenticated URL for private repositories.

    For GitHub URLs, inject the token into the URL.
    Example: https://github.com/org/repo.git -> https://TOKEN@github.com/org/repo.git
    """
    if not token:
        return url

    # Handle GitHub URLs
    if url.startswith("https://github.com/"):
        return url.replace("https://", f"https://{token}@", 1)

    # For other Git hosting services, try the same pattern
    if url.startswith("https://"):
        return url.replace("https://", f"https://{token}@", 1)

    return url


def _run_git_command(
    args: list[str],
    cwd: Path | None = None,
    env: dict | None = None,
) -> tuple[bool, str]:
    """Run a git command and return (success, output/error)."""
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout
            env={**os.environ, **(env or {})},
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, result.stderr.strip() or result.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "Git operation timed out"
    except FileNotFoundError:
        return False, "Git is not installed or not found in PATH"
    except Exception as e:
        return False, str(e)


def _clone_repo(config: RepoConfig) -> tuple[bool, str]:
    """Clone the repository.

    Returns:
        Tuple of (success, message).
    """
    repo_dir = _get_repo_dir()
    auth_url = _build_auth_url(config.url, config.token)

    # Remove existing directory if exists
    if repo_dir.exists():
        shutil.rmtree(repo_dir)

    # Clone with depth 1 for efficiency
    success, output = _run_git_command(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            config.branch,
            auth_url,
            str(repo_dir),
        ]
    )

    if success:
        logger.info("Cloned skills repo from %s (branch: %s)", config.url, config.branch)
        return True, "Repository cloned successfully"
    else:
        logger.error("Failed to clone skills repo: %s", output)
        # Clean up failed clone attempt
        if repo_dir.exists():
            shutil.rmtree(repo_dir, ignore_errors=True)
        return False, f"Failed to clone repository: {output}"


def _pull_repo(config: RepoConfig) -> tuple[bool, str]:
    """Pull latest changes from the repository.

    Returns:
        Tuple of (success, message).
    """
    repo_dir = _get_repo_dir()
    auth_url = _build_auth_url(config.url, config.token)

    # Update remote URL with fresh token
    success, _ = _run_git_command(
        ["git", "remote", "set-url", "origin", auth_url],
        cwd=repo_dir,
    )
    if not success:
        # If we can't set remote URL, try re-cloning
        logger.warning("Failed to update remote URL, re-cloning...")
        return _clone_repo(config)

    # Fetch and reset to latest
    success, output = _run_git_command(
        ["git", "fetch", "origin", config.branch],
        cwd=repo_dir,
    )
    if not success:
        logger.error("Failed to fetch from skills repo: %s", output)
        return False, f"Failed to fetch: {output}"

    # Hard reset to latest
    success, output = _run_git_command(
        ["git", "reset", "--hard", f"origin/{config.branch}"],
        cwd=repo_dir,
    )
    if not success:
        logger.error("Failed to reset skills repo: %s", output)
        return False, f"Failed to reset: {output}"

    logger.info("Pulled latest changes from skills repo (branch: %s)", config.branch)
    return True, "Repository updated successfully"


def _collect_skills_from_repo() -> dict[str, Path]:
    """Collect skills from the cloned repository.

    Returns:
        Dictionary mapping skill names to their paths.
    """
    repo_dir = _get_repo_dir()
    skills: dict[str, Path] = {}

    if not repo_dir.exists():
        return skills

    for item in repo_dir.iterdir():
        # Skip hidden directories and files
        if item.name.startswith("."):
            continue
        # Skip non-directories
        if not item.is_dir():
            continue
        # Check for SKILL.md
        skill_md = item / "SKILL.md"
        if skill_md.exists() and skill_md.is_file():
            skills[item.name] = item

    return skills


def _collect_skills_from_customized() -> dict[str, Path]:
    """Collect skills from customized_skills directory that came from repo.

    We identify repo-synced skills by checking if the same skill exists in the repo.
    """
    customized_dir = CUSTOMIZED_SKILLS_DIR
    skills: dict[str, Path] = {}

    if not customized_dir.exists():
        return skills

    for item in customized_dir.iterdir():
        if item.is_dir() and (item / "SKILL.md").exists():
            skills[item.name] = item

    return skills


def sync_skills_from_repo(config: RepoConfig | None = None) -> SyncResult:
    """Sync skills from the configured Git repository.

    This function:
    1. Clones or pulls the repository
    2. Scans for skills (directories with SKILL.md)
    3. Syncs to customized_skills directory
    4. Removes skills that no longer exist in the repo
    5. Enables all synced skills

    Args:
        config: Repository configuration. If None, reads from environment.

    Returns:
        SyncResult with details of the operation.
    """
    if config is None:
        config = get_repo_config()

    if config is None:
        return SyncResult(
            success=False,
            added=[],
            updated=[],
            removed=[],
            message="No skills repository configured. Set COPAW_SKILLS_REPO_URL environment variable.",
        )

    repo_dir = _get_repo_dir()

    # Clone or pull the repository
    if repo_dir.exists():
        success, message = _pull_repo(config)
    else:
        success, message = _clone_repo(config)

    if not success:
        return SyncResult(
            success=False,
            added=[],
            updated=[],
            removed=[],
            message=message,
        )

    # Collect skills from repo and customized_skills
    repo_skills = _collect_skills_from_repo()
    customized_skills = _collect_skills_from_customized()

    # Identify previous repo-synced skills (those that exist in customized but match repo structure)
    # For simplicity, we track by checking what's in the repo now vs before
    # Skills that were in the repo but are no longer there should be removed
    added: list[str] = []
    updated: list[str] = []
    removed: list[str] = []

    # Ensure customized_skills directory exists
    CUSTOMIZED_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    # Sync skills from repo to customized_skills
    for skill_name, skill_path in repo_skills.items():
        target_dir = CUSTOMIZED_SKILLS_DIR / skill_name

        if target_dir.exists():
            # Update existing skill
            try:
                shutil.rmtree(target_dir)
                shutil.copytree(skill_path, target_dir)
                updated.append(skill_name)
                logger.debug("Updated skill '%s' from repo", skill_name)
            except Exception as e:
                logger.error("Failed to update skill '%s': %s", skill_name, e)
        else:
            # Add new skill
            try:
                shutil.copytree(skill_path, target_dir)
                added.append(skill_name)
                logger.debug("Added skill '%s' from repo", skill_name)
            except Exception as e:
                logger.error("Failed to add skill '%s': %s", skill_name, e)

    # Remove skills that are no longer in the repo
    # We identify these as skills that exist in customized_skills but not in repo
    # AND were previously synced (we can't perfectly track this, so we use a marker file)
    for skill_name in customized_skills:
        if skill_name not in repo_skills:
            # Check if this skill was synced from repo by checking a marker
            skill_dir = CUSTOMIZED_SKILLS_DIR / skill_name
            marker_file = skill_dir / ".repo-synced"

            if marker_file.exists():
                # This skill was previously synced, remove it
                try:
                    shutil.rmtree(skill_dir)
                    removed.append(skill_name)
                    logger.debug("Removed skill '%s' (no longer in repo)", skill_name)
                except Exception as e:
                    logger.error("Failed to remove skill '%s': %s", skill_name, e)

    # Add marker files to all synced skills
    for skill_name in repo_skills:
        marker_file = CUSTOMIZED_SKILLS_DIR / skill_name / ".repo-synced"
        try:
            marker_file.touch()
        except Exception:
            pass  # Non-critical

    # Enable all synced skills
    from .skills_manager import SkillService

    for skill_name in repo_skills:
        SkillService.enable_skill(skill_name, force=True)
        logger.debug("Enabled skill '%s'", skill_name)

    # Build result message
    parts = []
    if added:
        parts.append(f"Added: {', '.join(added)}")
    if updated:
        parts.append(f"Updated: {', '.join(updated)}")
    if removed:
        parts.append(f"Removed: {', '.join(removed)}")

    if not parts:
        message = "Skills are already up to date"
    else:
        message = "; ".join(parts)

    logger.info(
        "Synced skills from repo: %d added, %d updated, %d removed",
        len(added),
        len(updated),
        len(removed),
    )

    return SyncResult(
        success=True,
        added=added,
        updated=updated,
        removed=removed,
        message=message,
    )


def is_repo_configured() -> bool:
    """Check if a skills repository is configured."""
    return get_repo_config() is not None