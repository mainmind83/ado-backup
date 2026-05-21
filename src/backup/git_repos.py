"""Git repository backup: bare mirrors with an incremental update strategy."""

import os
import shutil
import subprocess
import time

from logger import get_logger


def _inject_pat(clone_url, pat):
    """Embed a PAT into an https clone URL: https://oauth2:{PAT}@dev.azure.com/..."""
    return clone_url.replace("https://", f"https://oauth2:{pat}@", 1)


def _dir_size(path):
    """Total size in bytes of all files under path (0 if path does not exist)."""
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def backup_git_repos(client, organization, pat, project, dest_dir, previous_dir=None):
    """Back up all Git repos of a project as bare mirrors.

    If a repo already exists in the previous backup, it is copied forward and
    refreshed with `git remote update` (incremental). Otherwise it is cloned
    fresh with `git clone --mirror`. Returns the number of repos backed up.
    """
    log = get_logger()
    git_dir = os.path.join(dest_dir, "git")
    os.makedirs(git_dir, exist_ok=True)

    data = client.get(
        f"/{project}/_apis/git/repositories", params={"api-version": "7.1"}
    )
    repos = data.get("value", [])
    count = 0

    for repo in repos:
        name = repo["name"]
        bare_name = f"{name}.git"
        target = os.path.join(git_dir, bare_name)
        start = time.time()

        try:
            prev_repo = (
                os.path.join(previous_dir, "git", bare_name)
                if previous_dir else None
            )
            if prev_repo and os.path.isdir(prev_repo):
                shutil.copytree(prev_repo, target)
                subprocess.run(
                    ["git", "remote", "update"],
                    cwd=target, check=True, capture_output=True, text=True,
                )
                mode = "incremental"
            else:
                url = f"https://dev.azure.com/{organization}/{project}/_git/{name}"
                subprocess.run(
                    ["git", "clone", "--mirror", _inject_pat(url, pat), target],
                    check=True, capture_output=True, text=True,
                )
                mode = "full clone"

            duration = time.time() - start
            log.info(
                f"git: {project}/{name} backed up ({mode}, "
                f"{_dir_size(target)} bytes, {duration:.1f}s)"
            )
            count += 1
        except subprocess.CalledProcessError as exc:
            log.error(
                f"git: failed to back up {project}/{name}: "
                f"{(exc.stderr or '').strip()}"
            )
        except OSError as exc:
            log.error(f"git: failed to back up {project}/{name}: {exc}")

    return count
