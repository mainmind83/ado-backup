"""Entry point: load config, configure logging, log banner, start scheduler."""

import sys

import requests

from config import ConfigError, load_config
from logger import get_logger, setup_logging
from scheduler import start_scheduler

__version__ = "0.2.2"

DEFAULT_CONFIG_PATH = "/app/config.yaml"
LATEST_RELEASE_URL = (
    "https://api.github.com/repos/mainmind83/ado-backup/releases/latest"
)


def _check_latest_version(log):
    """Log one informational line about whether a newer release exists.

    Read-only and best-effort — any network/parse failure is logged at
    WARNING and swallowed; the rest of startup is never blocked.
    """
    try:
        resp = requests.get(LATEST_RELEASE_URL, timeout=5)
        resp.raise_for_status()
        latest = resp.json().get("tag_name", "").lstrip("v")
    except Exception as exc:  # noqa: BLE001 - version check must never crash startup
        log.warning(
            f"version check: skipped ({exc.__class__.__name__}: {exc})"
        )
        return

    if not latest:
        log.warning("version check: skipped (empty tag_name from GitHub)")
        return

    if latest == __version__:
        log.info(f"version check: v{__version__} is the latest release")
    else:
        log.info(
            f"version check: running v{__version__}, latest is v{latest} — "
            f"consider updating "
            f"(https://github.com/mainmind83/ado-backup/releases/tag/v{latest})"
        )


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
    log.info(f"ADO Backup Tool v{__version__} starting")
    log.info(f"  organization : {config.azure_devops.organization}")
    log.info(f"  projects     : {', '.join(config.azure_devops.projects)}")
    log.info(f"  resources    : {', '.join(enabled) or '(none)'}")
    log.info(f"  schedule     : {config.schedule}")
    log.info(f"  destination  : {config.backup.destination}")
    log.info(f"  retention    : {config.backup.retention_days} days")
    log.info("=" * 64)

    _check_latest_version(log)

    start_scheduler(config_path, config)


if __name__ == "__main__":
    main()
