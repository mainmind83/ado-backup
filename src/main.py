"""Entry point: load config, configure logging, log banner, start scheduler."""

import sys

from config import ConfigError, load_config
from logger import get_logger, setup_logging
from scheduler import start_scheduler

DEFAULT_CONFIG_PATH = "/app/config.yaml"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    config_path = argv[0] if argv else DEFAULT_CONFIG_PATH

    try:
        config = load_config(config_path)
    except FileNotFoundError:
        print(f"FATAL: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    except ConfigError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        sys.exit(1)

    setup_logging(
        level=config.logging.level,
        file=config.logging.file,
        max_bytes=config.logging.max_bytes,
        backup_count=config.logging.backup_count,
    )
    log = get_logger()

    enabled = [
        name for name, on in (
            ("git", config.backup.resources.git),
            ("pipelines", config.backup.resources.pipelines),
            ("wikis", config.backup.resources.wikis),
        ) if on
    ]

    log.info("=" * 64)
    log.info("ADO Backup Tool starting")
    log.info(f"  organization : {config.azure_devops.organization}")
    log.info(f"  projects     : {', '.join(config.azure_devops.projects)}")
    log.info(f"  resources    : {', '.join(enabled) or '(none)'}")
    log.info(f"  schedule     : {config.schedule}")
    log.info(f"  destination  : {config.backup.destination}")
    log.info(f"  retention    : {config.backup.retention_days} days")
    log.info("=" * 64)

    start_scheduler(config_path, config)


if __name__ == "__main__":
    main()
