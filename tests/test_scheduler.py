"""Tests for the per-run config reload wrapper."""

from unittest.mock import patch

import scheduler


VALID_YAML = """\
schedule: "0 2 * * *"
azure_devops:
  organization: "testorg"
  pat: "testpat"
  projects: ["*"]
backup:
  destination: '{dest}'
"""


def test_scheduled_run_reloads_config_each_call(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    dest = (tmp_path / "backup").as_posix()
    cfg_path.write_text(VALID_YAML.format(dest=dest), encoding="utf-8")

    with patch.object(scheduler, "run_backup") as run_backup:
        scheduler._scheduled_run(str(cfg_path))

        # Edit projects mid-life and run again — second call must see the change.
        cfg_path.write_text(VALID_YAML.format(dest=dest).replace(
            'projects: ["*"]', 'projects: ["OnlyOne"]'
        ), encoding="utf-8")
        scheduler._scheduled_run(str(cfg_path))

    assert run_backup.call_count == 2
    first_cfg = run_backup.call_args_list[0].args[0]
    second_cfg = run_backup.call_args_list[1].args[0]
    assert first_cfg.azure_devops.projects == ["*"]
    assert second_cfg.azure_devops.projects == ["OnlyOne"]


def test_scheduled_run_skips_when_config_missing(tmp_path):
    missing = tmp_path / "nope.yaml"

    with patch.object(scheduler, "run_backup") as run_backup:
        scheduler._scheduled_run(str(missing))

    run_backup.assert_not_called()


def test_scheduled_run_skips_when_config_invalid(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "azure_devops:\n  organization: missing-pat-and-projects\n",
        encoding="utf-8",
    )

    with patch.object(scheduler, "run_backup") as run_backup:
        scheduler._scheduled_run(str(cfg_path))

    run_backup.assert_not_called()
