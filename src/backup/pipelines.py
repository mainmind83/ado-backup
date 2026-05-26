"""Pipeline backup: export build and release definitions as JSON files."""

import json
import os
import re

from ado.client import encode_path_segment
from logger import get_logger

# Release pipelines live on a separate host.
VSRM_BASE = "https://vsrm.dev.azure.com"


def _sanitize(name, max_len=80):
    """Replace non-alphanumeric runs with '-' and trim to max_len chars."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-")
    return cleaned[:max_len]


def _write_definition(directory, prefix, definition):
    """Write a single definition to <prefix>-<id>-<name>.json. Returns 1."""
    def_id = definition.get("id", "unknown")
    name = _sanitize(str(definition.get("name", "unknown")))
    path = os.path.join(directory, f"{prefix}-{def_id}-{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(definition, f, indent=2)
    return 1


def backup_pipelines(client, organization, project, dest_dir):
    """Back up build and release pipeline definitions for a project.

    Returns the number of definitions saved.
    """
    log = get_logger()
    build_dir = os.path.join(dest_dir, "pipelines", "build")
    release_dir = os.path.join(dest_dir, "pipelines", "release")
    os.makedirs(build_dir, exist_ok=True)
    os.makedirs(release_dir, exist_ok=True)
    count = 0

    # Build pipeline definitions.
    build_data = client.get(
        f"/{encode_path_segment(project)}/_apis/build/definitions",
        params={"api-version": "7.1", "$expand": "process"},
    )
    for definition in build_data.get("value", []):
        count += _write_definition(build_dir, "pipeline", definition)
    log.info(f"pipelines: {project} build definitions saved "
             f"({len(build_data.get('value', []))})")

    # Release pipeline definitions (separate vsrm host).
    release_data = client.get(
        f"{VSRM_BASE}/{encode_path_segment(organization)}"
        f"/{encode_path_segment(project)}/_apis/release/definitions",
        params={"api-version": "7.1", "$expand": "environments"},
    )
    for definition in release_data.get("value", []):
        count += _write_definition(release_dir, "release", definition)
    log.info(f"pipelines: {project} release definitions saved "
             f"({len(release_data.get('value', []))})")

    return count
