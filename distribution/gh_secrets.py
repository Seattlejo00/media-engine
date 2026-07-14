"""
Persist rotated tokens back into GitHub repository secrets.

Some platforms rotate credentials (Instagram 60-day tokens, TikTok
refresh tokens). On CI the runner can't outlive the run, so rotated
values must be written back to the repo's secrets or posting silently
dies when the old credential expires.

Requires a fine-grained PAT with "Secrets: read and write" on this repo,
provided as the GH_SECRETS_PAT env var. Without it, rotation still works
for the current run but can't be persisted — callers should warn.
"""

import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def persist_secret(name: str, value: str) -> bool:
    """Write a repo secret via the gh CLI. Returns True on success."""
    pat = os.getenv("GH_SECRETS_PAT", "")
    repo = os.getenv("GITHUB_REPOSITORY", "")
    if not (pat and repo):
        return False
    try:
        subprocess.run(
            ["gh", "secret", "set", name, "--repo", repo, "--body", value],
            env={**os.environ, "GH_TOKEN": pat},
            check=True,
            capture_output=True,
            timeout=30,
        )
        logger.info(f"Persisted rotated secret {name} to {repo}")
        return True
    except Exception as e:
        logger.error(f"Failed to persist secret {name}: {e}")
        return False
