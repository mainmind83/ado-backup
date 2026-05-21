"""Internal cron scheduler driving periodic backup runs."""

from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from backup.runner import run_backup
from logger import get_logger


def start_scheduler(config):
    """Start the blocking cron scheduler. Blocks until interrupted."""
    log = get_logger()
    trigger = CronTrigger.from_crontab(config.schedule)

    if config.run_on_start:
        log.info("run_on_start enabled — triggering an immediate backup")
        run_backup(config)

    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_backup, trigger, args=[config], id="backup",
        max_instances=1, coalesce=True,
    )

    next_run = trigger.get_next_fire_time(None, datetime.now(trigger.timezone))
    log.info(f"scheduler started — next run at {next_run}")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("scheduler stopped")
