"""Tests for the Git repository backup module."""

import os
from unittest.mock import MagicMock, patch

from backup.git_repos import backup_git_repos


def _client(repo_names):
    client = MagicMock()
    client.get.return_value = {"value": [{"name": n} for n in repo_names]}
    return client


def _ok_run(*_args, **_kwargs):
    """Default subprocess.run mock — succeeds with empty stderr."""
    return MagicMock(returncode=0, stderr="")


def test_new_repo_is_cloned_fresh(tmp_path):
    client = _client(["RepoA"])
    dest = tmp_path / "Project1"

    with patch("backup.git_repos.subprocess.run", side_effect=_ok_run) as run:
        count, fsck_errors = backup_git_repos(
            client, "org", "pat", "Project1", str(dest), previous_dir=None
        )

    assert (count, fsck_errors) == (1, 0)
    # Two subprocess calls: clone + fsck.
    clone_args = run.call_args_list[0].args[0]
    fsck_args = run.call_args_list[1].args[0]
    assert clone_args[:3] == ["git", "clone", "--mirror"]
    assert "oauth2:pat@dev.azure.com" in clone_args[3]
    assert clone_args[3].endswith("/Project1/_git/RepoA")
    assert fsck_args == ["git", "fsck", "--no-progress"]


def test_incremental_copies_existing_repo_then_updates(tmp_path):
    # Seed a previous backup containing the bare repo.
    prev = tmp_path / "prev" / "Project1"
    prev_repo = prev / "git" / "RepoA.git"
    prev_repo.mkdir(parents=True)
    (prev_repo / "marker").write_text("old", encoding="utf-8")

    client = _client(["RepoA"])
    dest = tmp_path / "current" / "Project1"

    with patch("backup.git_repos.subprocess.run", side_effect=_ok_run) as run:
        count, fsck_errors = backup_git_repos(
            client, "org", "pat", "Project1", str(dest), previous_dir=str(prev)
        )

    assert (count, fsck_errors) == (1, 0)
    # The existing repo was copied forward...
    target = dest / "git" / "RepoA.git"
    assert (target / "marker").read_text(encoding="utf-8") == "old"
    # ...refreshed with `git remote update` (not re-cloned), then fsck'd.
    cmds = [c.args[0] for c in run.call_args_list]
    assert cmds == [
        ["git", "remote", "update"],
        ["git", "fsck", "--no-progress"],
    ]
    assert all(c.kwargs["cwd"] == str(target) for c in run.call_args_list)


def test_clone_failure_is_logged_and_skipped(tmp_path):
    import subprocess

    client = _client(["RepoA", "RepoB"])
    dest = tmp_path / "Project1"

    def fake_run(cmd, **kwargs):
        # Clone of RepoA blows up; everything else (clone RepoB, fsck) succeeds.
        if cmd[:3] == ["git", "clone", "--mirror"] and "RepoA" in cmd[-1]:
            raise subprocess.CalledProcessError(1, cmd, stderr="boom")
        return MagicMock(returncode=0, stderr="")

    with patch("backup.git_repos.subprocess.run", side_effect=fake_run):
        count, fsck_errors = backup_git_repos(
            client, "org", "pat", "Project1", str(dest), previous_dir=None
        )

    # RepoA failed, RepoB still succeeded and verified.
    assert (count, fsck_errors) == (1, 0)


def test_url_encodes_project_and_repo_with_spaces(tmp_path):
    """ADO names may contain spaces, '&', '#', etc. URLs must be encoded
    or git/curl reject them ("URL rejected: Malformed input to a URL function").
    """
    client = _client(["My Repo"])
    dest = tmp_path / "Project1"

    with patch("backup.git_repos.subprocess.run", side_effect=_ok_run) as run:
        count, fsck_errors = backup_git_repos(
            client, "my org", "pat", "My Project",
            str(dest), previous_dir=None,
        )

    assert (count, fsck_errors) == (1, 0)
    # The project listing path must be URL-encoded.
    api_path = client.get.call_args.args[0]
    assert "My%20Project" in api_path
    assert " " not in api_path
    # The clone URL must be fully encoded — none of org, project, repo name leaks a space.
    clone_url = run.call_args_list[0].args[0][3]
    assert "my%20org" in clone_url
    assert "My%20Project/_git/My%20Repo" in clone_url
    # No raw space anywhere in the constructed URL (after the oauth2: prefix).
    assert " " not in clone_url


def test_fsck_failure_counts_but_keeps_backup(tmp_path):
    client = _client(["RepoA"])
    dest = tmp_path / "Project1"

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "fsck"]:
            return MagicMock(returncode=1, stderr="bad object deadbeef")
        return MagicMock(returncode=0, stderr="")

    with patch("backup.git_repos.subprocess.run", side_effect=fake_run):
        count, fsck_errors = backup_git_repos(
            client, "org", "pat", "Project1", str(dest), previous_dir=None
        )

    # Mirror is on disk (counted) but verification failed (flagged).
    assert (count, fsck_errors) == (1, 1)
