"""Shared pytest fixtures."""

import pytest

from config import Config


@pytest.fixture
def make_config(tmp_path):
    """Factory returning a valid Config pointing at a temp destination."""
    def _make(**overrides):
        data = {
            "schedule": "0 2 * * *",
            "azure_devops": {
                "organization": "testorg",
                "pat": "testpat",
                "projects": ["Project1"],
            },
            "backup": {
                "destination": str(tmp_path / "backup"),
                "retention_days": 30,
                "resources": {"git": True, "pipelines": True, "wikis": True},
            },
            "logging": {"file": str(tmp_path / "logs" / "backup.log")},
        }
        data.update(overrides)
        return Config(**data)

    return _make
