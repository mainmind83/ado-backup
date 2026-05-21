"""Backup run orchestration: creates a timestamped folder, runs every enabled
resource module per project, then applies retention cleanup.
"""

import os
import shutil
import time
from datetime import datetime, timedelta

from ado.client import ADOClient, ADOAuthError
from backup.git_repos import backup_git_repos
from backup.pipelines import backup_pipelines
from backup.wikis import backup_wikis
from logger import get_logger

TIMESTAMP_FORMAT = "%Y-%m-%dT%H%M%S"


def _is_timestamp(name):
    try:
        datetime.strptime(name, TIMESTAMP_FORMAT)
        return True
    except ValueError:
        return False


def _find_previous_backup(destination, exclude=None):
    """Return the path of the most recent existing timestamped backup, or None."""
    if not os.path.isdir(destination):
        return None
    stamps = sorted(
        name for name in os.listdir(destination)
        if name != exclude
        and _is_timestamp(name)
        and os.path.isdir(os.path.join(destination, name))
    )
    return os.path.join(destination, stamps[-1]) if stamps else None


def _resolve_projects(client, configured):
    """Expand ['*'] to all project names; otherwise return the list as-is."""
    if configured == ["*"]:
        data = client.get("/_apis/projects", params={"api-version": "7.1"})
        return [p["name"] for p in data.get("value", [])]
    return list(configured)


def _cleanup_retention(destination, retention_days, current, log):
    """Delete timestamped backup folders older than retention_days."""
    if retention_days <= 0:
        return
    cutoff = datetime.now() - timedelta(days=retention_days)
    for name in os.listdir(destination):
        path = os.path.join(destination, name)
        if name == current or not _is_timestamp(name) or not os.path.isdir(path):
            continue
        if datetime.strptime(name, TIMESTAMP_FORMAT) < cutoff:
            shutil.rmtree(path, ignore_errors=True)
            log.info(f"retention: deleted old backup {name}")


def run_backup(config):
    """Execute a single backup run. Never raises — all errors are logged."""
    log = get_logger()
    start = time.time()
    destination = config.backup.destination

    try:
        os.makedirs(destination, exist_ok=True)
    except OSError as exc:
        log.error(f"destination not writable, aborting run: {exc}")
        return
    if not os.access(destination, os.W_OK):
        log.error(f"destination not writable, aborting run: {destination}")
        return

    timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
    run_dir = os.path.join(destination, timestamp)
    previous = _find_previous_backup(destination, exclude=timestamp)
    os.makedirs(run_dir, exist_ok=True)
    log.info(f"backup run started -> {run_dir}")
    if previous:
        log.info(f"previous backup for incremental git: {previous}")

    client = ADOClient(config.azure_devops.organization, config.azure_devops.pat)

    try:
        projects = _resolve_projects(client, config.azure_devops.projects)
    except ADOAuthError as exc:
        log.error(f"{exc} — aborting run, previous backup preserved")
        shutil.rmtree(run_dir, ignore_errors=True)
        return
    except Exception as exc:  # noqa: BLE001 - run must never crash
        log.error(f"failed to list projects, aborting run: {exc}")
        shutil.rmtree(run_dir, ignore_errors=True)
        return

    resources = config.backup.resources
    summary = {"repos": 0, "pipelines": 0, "wikis": 0, "errors": 0}

    for project in projects:
        project_dir = os.path.join(run_dir, project)
        os.makedirs(project_dir, exist_ok=True)
        prev_project = os.path.join(previous, project) if previous else None

        if resources.git:
            try:
                summary["repos"] += backup_git_repos(
                    client, config.azure_devops.organization,
                    config.azure_devops.pat, project, project_dir, prev_project,
                )
            except ADOAuthError as exc:
                log.error(f"{exc} — aborting run, previous backup preserved")
                return
            except Exception as exc:  # noqa: BLE001
                log.error(f"git backup failed for {project}: {exc}")
                summary["errors"] += 1

        if resources.pipelines:
            try:
                summary["pipelines"] += backup_pipelines(
                    client, config.azure_devops.organization, project, project_dir,
                )
            except ADOAuthError as exc:
                log.error(f"{exc} — aborting run, previous backup preserved")
                return
            except Exception as exc:  # noqa: BLE001
                log.error(f"pipeline backup failed for {project}: {exc}")
                summary["errors"] += 1

        if resources.wikis:
            try:
                summary["wikis"] += backup_wikis(client, project, project_dir)
            except ADOAuthError as exc:
                log.error(f"{exc} — aborting run, previous backup preserved")
                return
            except Exception as exc:  # noqa: BLE001
                log.error(f"wiki backup failed for {project}: {exc}")
                summary["errors"] += 1

    try:
        _cleanup_retention(
            destination, config.backup.retention_days, timestamp, log
        )
    except OSError as exc:
        log.error(f"retention cleanup failed: {exc}")

    duration = time.time() - start
    log.info(
        f"backup run finished in {duration:.1f}s — "
        f"repos={summary['repos']} pipelines={summary['pipelines']} "
        f"wikis={summary['wikis']} errors={summary['errors']}"
    )
    return summary
