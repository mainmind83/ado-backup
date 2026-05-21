"""Tests for the Git repository backup module."""

import os
from unittest.mock import MagicMock, patch

from backup.git_repos import backup_git_repos


def _client(repo_names):
    client = MagicMock()
    client.get.return_value = {"value": [{"name": n} for n in repo_names]}
    return client


def test_new_repo_is_cloned_fresh(tmp_path):
    client = _client(["RepoA"])
    dest = tmp_path / "Project1"

    with patch("backup.git_repos.subprocess.run") as run:
        count = backup_git_repos(
            client, "org", "pat", "Project1", str(dest), previous_dir=None
        )

    assert count == 1
    args = run.call_args[0][0]
    assert args[:3] == ["git", "clone", "--mirror"]
    assert "oauth2:pat@dev.azure.com" in args[3]
    assert args[3].endswith("/Project1/_git/RepoA")


def test_incremental_copies_existing_repo_then_updates(tmp_path):
    # Seed a previous backup containing the bare repo.
    prev = tmp_path / "prev" / "Project1"
    prev_repo = prev / "git" / "RepoA.git"
    prev_repo.mkdir(parents=True)
    (prev_repo / "marker").write_text("old", encoding="utf-8")

    client = _client(["RepoA"])
    dest = tmp_path / "current" / "Project1"

    with patch("backup.git_repos.subprocess.run") as run:
        count = backup_git_repos(
            client, "org", "pat", "Project1", str(dest), previous_dir=str(prev)
        )

    assert count == 1
    # The existing repo was copied forward...
    target = dest / "git" / "RepoA.git"
    assert (target / "marker").read_text(encoding="utf-8") == "old"
    # ...and refreshed with `git remote update` (not re-cloned).
    args = run.call_args[0][0]
    assert args == ["git", "remote", "update"]
    assert run.call_args[1]["cwd"] == str(target)


def test_clone_failure_is_logged_and_skipped(tmp_path):
    import subprocess

    client = _client(["RepoA", "RepoB"])
    dest = tmp_path / "Project1"

    def fake_run(cmd, **kwargs):
        if "RepoA" in cmd[-1]:
            raise subprocess.CalledProcessError(1, cmd, stderr="boom")
        return MagicMock()

    with patch("backup.git_repos.subprocess.run", side_effect=fake_run):
        count = backup_git_repos(
            client, "org", "pat", "Project1", str(dest), previous_dir=None
        )

    # RepoA failed, RepoB still succeeded.
    assert count == 1
