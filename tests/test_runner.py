"""Tests for the backup run orchestration: retention and error isolation."""

import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import backup.runner as runner


def test_retention_deletes_old_folders(tmp_path):
    old = (datetime.now() - timedelta(days=60)).strftime(runner.TIMESTAMP_FORMAT)
    recent = (datetime.now() - timedelta(days=2)).strftime(runner.TIMESTAMP_FORMAT)
    current = datetime.now().strftime(runner.TIMESTAMP_FORMAT)
    for name in (old, recent, current):
        (tmp_path / name).mkdir()
    (tmp_path / "not-a-timestamp").mkdir()

    runner._cleanup_retention(str(tmp_path), 30, current, MagicMock())

    assert not (tmp_path / old).exists()          # older than retention -> deleted
    assert (tmp_path / recent).exists()           # within retention -> kept
    assert (tmp_path / current).exists()          # current run -> never deleted
    assert (tmp_path / "not-a-timestamp").exists()  # non-backup folders untouched


def test_retention_zero_keeps_everything(tmp_path):
    old = (datetime.now() - timedelta(days=999)).strftime(runner.TIMESTAMP_FORMAT)
    (tmp_path / old).mkdir()

    runner._cleanup_retention(str(tmp_path), 0, "x", MagicMock())

    assert (tmp_path / old).exists()


def test_resource_error_does_not_stop_other_resources(make_config):
    config = make_config()

    with patch.object(runner, "ADOClient"), \
         patch.object(runner, "backup_git_repos",
                      side_effect=RuntimeError("git exploded")) as git, \
         patch.object(runner, "backup_pipelines", return_value=3) as pipelines, \
         patch.object(runner, "backup_wikis", return_value=2) as wikis:
        summary = runner.run_backup(config)

    # Git failed but the run continued through pipelines and wikis.
    git.assert_called_once()
    pipelines.assert_called_once()
    wikis.assert_called_once()
    assert summary["errors"] == 1
    assert summary["pipelines"] == 3
    assert summary["wikis"] == 2


def test_run_creates_timestamped_folder(make_config):
    config = make_config()

    with patch.object(runner, "ADOClient"), \
         patch.object(runner, "backup_git_repos", return_value=1), \
         patch.object(runner, "backup_pipelines", return_value=1), \
         patch.object(runner, "backup_wikis", return_value=1):
        runner.run_backup(config)

    entries = [e for e in os.listdir(config.backup.destination)
               if runner._is_timestamp(e)]
    assert len(entries) == 1
    # The configured project folder exists inside the run folder.
    assert os.path.isdir(
        os.path.join(config.backup.destination, entries[0], "Project1")
    )
