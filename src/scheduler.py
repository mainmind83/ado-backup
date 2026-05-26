"""Internal cron scheduler driving periodic backup runs."""

from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from backup.runner import run_backup
from config import ConfigError, load_config
from logger import get_logger


def _scheduled_run(config_path):
    """Reload the YAML from disk and trigger one backup run.

    Re-reading per run means edits to projects, resources, retention, PAT,
    organization and destination apply at the next fire without a restart.
    `schedule` and `logging` are bound at boot and still require a restart.
    """
    log = get_logger()
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ConfigError) as exc:
        log.error(f"config reload failed, skipping this run: {exc}")
        return
    run_backup(config)


def start_scheduler(config_path, config):
    """Start the blocking cron scheduler. Blocks until interrupted."""
    log = get_logger()
    trigger = CronTrigger.from_crontab(config.schedule)

    if config.run_on_start:
        log.info("run_on_start enabled — triggering an immediate backup")
        run_backup(config)

    scheduler = BlockingScheduler()
    scheduler.add_job(
        _scheduled_run, trigger, args=[config_path], id="backup",
        max_instances=1, coalesce=True,
    )

    next_run = trigger.get_next_fire_time(None, datetime.now(trigger.timezone))
    log.info(f"scheduler started — next run at {next_run}")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("scheduler stopped")
