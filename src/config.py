"""Configuration loading, environment variable substitution and validation."""

import os
import re
from typing import List, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ConfigError(Exception):
    """Raised for any configuration problem that must abort startup."""


class AzureDevOpsConfig(BaseModel):
    organization: str
    pat: str
    projects: List[str]

    @field_validator("projects")
    @classmethod
    def _projects_not_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("at least one project must be specified")
        return v


class ResourcesConfig(BaseModel):
    git: bool = True
    pipelines: bool = True
    wikis: bool = True


class BackupConfig(BaseModel):
    destination: str = "/backup"
    retention_days: int = 30
    resources: ResourcesConfig = Field(default_factory=ResourcesConfig)


class LoggingConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    file: str = "/logs/backup.log"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5


class Config(BaseModel):
    schedule: str = "0 2 * * *"
    run_on_start: bool = False
    azure_devops: AzureDevOpsConfig
    backup: BackupConfig = Field(default_factory=BackupConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def _find_missing_env_vars(value) -> List[str]:
    """Walk the raw config and collect names of ${VAR} references not in os.environ."""
    missing: List[str] = []
    if isinstance(value, dict):
        for v in value.values():
            missing.extend(_find_missing_env_vars(v))
    elif isinstance(value, list):
        for v in value:
            missing.extend(_find_missing_env_vars(v))
    elif isinstance(value, str):
        for match in ENV_VAR_PATTERN.finditer(value):
            if match.group(1) not in os.environ:
                missing.append(match.group(1))
    return missing


def _substitute_env_vars(value):
    """Recursively replace every ${VAR} occurrence with its environment value."""
    if isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env_vars(v) for v in value]
    if isinstance(value, str):
        return ENV_VAR_PATTERN.sub(lambda m: os.environ[m.group(1)], value)
    return value


def load_config(path: str) -> Config:
    """Load, substitute and validate the YAML config. Raises ConfigError on any problem."""
    with open(path, "r", encoding="utf-8") as f:
        try:
            raw = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ConfigError(f"invalid YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"config file {path} is empty or malformed")

    missing = sorted(set(_find_missing_env_vars(raw)))
    if missing:
        raise ConfigError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    substituted = _substitute_env_vars(raw)

    try:
        return Config(**substituted)
    except ValidationError as exc:
        lines = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "(root)"
            lines.append(f"  - {loc}: {err['msg']}")
        raise ConfigError("Invalid configuration:\n" + "\n".join(lines)) from exc
