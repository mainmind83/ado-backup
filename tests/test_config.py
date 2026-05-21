"""Tests for config loading, validation and env var substitution."""

import textwrap

import pytest

from config import ConfigError, load_config


def _write(tmp_path, content):
    path = tmp_path / "config.yaml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(path)


def test_valid_config_loads(tmp_path):
    path = _write(tmp_path, """
        schedule: "0 3 * * *"
        azure_devops:
          organization: "myorg"
          pat: "plain-pat"
          projects:
            - "Alpha"
            - "Beta"
        backup:
          destination: "/data"
          retention_days: 7
          resources:
            git: true
            pipelines: false
            wikis: true
    """)
    config = load_config(path)

    assert config.schedule == "0 3 * * *"
    assert config.azure_devops.organization == "myorg"
    assert config.azure_devops.projects == ["Alpha", "Beta"]
    assert config.backup.retention_days == 7
    assert config.backup.resources.pipelines is False
    # Defaults applied for the omitted logging section.
    assert config.logging.level == "INFO"


def test_missing_required_field_raises(tmp_path):
    path = _write(tmp_path, """
        azure_devops:
          organization: "myorg"
          pat: "plain-pat"
    """)
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "projects" in str(exc.value)


def test_empty_projects_raises(tmp_path):
    path = _write(tmp_path, """
        azure_devops:
          organization: "myorg"
          pat: "plain-pat"
          projects: []
    """)
    with pytest.raises(ConfigError):
        load_config(path)


def test_env_var_substitution(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_PAT", "secret-token")
    path = _write(tmp_path, """
        azure_devops:
          organization: "myorg"
          pat: "${MY_PAT}"
          projects:
            - "Alpha"
    """)
    config = load_config(path)
    assert config.azure_devops.pat == "secret-token"


def test_missing_env_var_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("ABSENT_PAT", raising=False)
    path = _write(tmp_path, """
        azure_devops:
          organization: "myorg"
          pat: "${ABSENT_PAT}"
          projects:
            - "Alpha"
    """)
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "ABSENT_PAT" in str(exc.value)
