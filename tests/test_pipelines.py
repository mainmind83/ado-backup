"""Tests for the pipeline backup module."""

import json
import os
from unittest.mock import MagicMock

from backup.pipelines import backup_pipelines


def _client():
    client = MagicMock()

    def fake_get(path, params=None):
        if path.endswith("/build/definitions"):
            return {"value": [{"id": 101, "name": "My Pipeline!"}]}
        if path.endswith("/release/definitions"):
            return {"value": [{"id": 1, "name": "Deploy Prod"}]}
        raise AssertionError(f"unexpected path {path}")

    client.get.side_effect = fake_get
    return client


def test_build_and_release_definitions_saved_with_correct_filenames(tmp_path):
    dest = tmp_path / "Project1"

    count = backup_pipelines(_client(), "org", "Project1", str(dest))

    assert count == 2

    build_file = dest / "pipelines" / "build" / "pipeline-101-My-Pipeline.json"
    release_file = dest / "pipelines" / "release" / "release-1-Deploy-Prod.json"
    assert build_file.is_file()
    assert release_file.is_file()

    saved = json.loads(build_file.read_text(encoding="utf-8"))
    assert saved["id"] == 101


def test_release_uses_vsrm_host(tmp_path):
    client = _client()
    backup_pipelines(client, "org", "Project1", str(tmp_path / "Project1"))

    release_call = [
        c for c in client.get.call_args_list
        if c[0][0].endswith("/release/definitions")
    ][0]
    assert release_call[0][0].startswith("https://vsrm.dev.azure.com/")
