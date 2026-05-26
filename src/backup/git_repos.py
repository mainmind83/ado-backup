"""Git repository backup: bare mirrors with an incremental update strategy."""

import os
import shutil
import subprocess
import time

from ado.client import encode_path_segment
from logger import get_logger


def _inject_pat(clone_url, pat):
    """Embed a PAT into an https clone URL: https://oauth2:{PAT}@dev.azure.com/..."""
    return clone_url.replace("https://", f"https://oauth2:{pat}@", 1)


def dir_size(path):
    """Total size in bytes of all files under path (0 if path does not exist)."""
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def _fsck_bare(target):
    """Run `git fsck` on a bare mirror. Returns (ok, stderr_text)."""
    result = subprocess.run(
        ["git", "fsck", "--no-progress"],
        cwd=target, check=False, capture_output=True, text=True,
    )
    return result.returncode == 0, (result.stderr or "").strip()


def backup_git_repos(client, organization, pat, project, dest_dir, previous_dir=None):
    """Back up all Git repos of a project as bare mirrors.

    If a repo already exists in the previous backup, it is copied forward and
    refreshed with `git remote update` (incremental). Otherwise it is cloned
    fresh with `git clone --mirror`. Each mirror is then verified with
    `git fsck`. Returns `(count, fsck_errors)` where `count` is the number of
    mirrors written to disk and `fsck_errors` is how many failed verification.
    """
    log = get_logger()
    git_dir = os.path.join(dest_dir, "git")
    os.makedirs(git_dir, exist_ok=True)

    data = client.get(
        f"/{encode_path_segment(project)}/_apis/git/repositories",
        params={"api-version": "7.1"},
    )
    repos = data.get("value", [])
    count = 0
    fsck_errors = 0

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
                url = (
                    f"https://dev.azure.com/"
                    f"{encode_path_segment(organization)}/"
                    f"{encode_path_segment(project)}/_git/"
                    f"{encode_path_segment(name)}"
                )
                subprocess.run(
                    ["git", "clone", "--mirror", _inject_pat(url, pat), target],
                    check=True, capture_output=True, text=True,
                )
                mode = "full clone"

            ok, stderr = _fsck_bare(target)
            if ok:
                verify = "verified"
            else:
                verify = "FSCK FAILED"
                fsck_errors += 1
                log.error(f"git: fsck failed for {project}/{name}: {stderr}")

            duration = time.time() - start
            log.info(
                f"git: {project}/{name} backed up ({mode}, {verify}, "
                f"{dir_size(target)} bytes, {duration:.1f}s)"
            )
            count += 1
        except subprocess.CalledProcessError as exc:
            log.error(
                f"git: failed to back up {project}/{name}: "
                f"{(exc.stderr or '').strip()}"
            )
        except OSError as exc:
            log.error(f"git: failed to back up {project}/{name}: {exc}")

    return count, fsck_errors
