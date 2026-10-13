"""Application configuration loading built on pydantic-settings.

Settings are resolved from three layers, in increasing order of precedence:

1. ``config/base.yaml``          - defaults shared by every environment
2. ``config/<env>.{yaml,yml,json}`` - per-environment overrides (dev/stage/prod)
3. operating-system environment  - overrides for CI / deploy-time changes

Later layers override individual values from earlier ones. Nested values
(for example a single threshold inside the ``MONITORING`` block) can be
overridden on their own without having to restate the whole block, because
the file layers are deep-merged and environment variables use a nested
delimiter.

The per-environment file may be YAML (``.yaml``/``.yml``) or JSON (``.json``),
but only one such file may exist for a given environment.

Environment variable overrides use the ``APP_`` prefix and ``__`` as the
nested delimiter, e.g.::

    APP_FQDN=example.com
    APP_MONITORING__ENABLED=true
    APP_MONITORING__ALARMS__ECS_CPU_THRESHOLD=90
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

VALID_ENVS = ("dev", "stage", "prod")
DEFAULT_CONFIG_DIR = "config"
JSON_SUFFIXES = (".json",)
YAML_SUFFIXES = (".yaml", ".yml")


class AlarmThresholds(BaseModel):
    """Thresholds used by the optional monitoring stack's CloudWatch alarms."""

    ecs_cpu_threshold: int = 80
    ecs_memory_threshold: int = 80
    alb_5xx_threshold: int = 10
    alb_p99_latency_threshold: int = 5
    unhealthy_host_threshold: int = 1
    healthy_host_min: int = 1
    running_task_min: int = 1


class MonitoringConfig(BaseModel):
    """Monitoring configuration. Opt-in via ``enabled``."""

    enabled: bool = False
    notification_email: str = ""
    slack_webhook_url: str = ""
    enable_dashboard: bool = True
    alarms: AlarmThresholds = Field(default_factory=AlarmThresholds)


class AppSettings(BaseSettings):
    """Typed application settings for a single deployment environment.

    Prefer :func:`load_context_config` to build an instance so the correct
    per-environment file is layered on top of ``base.yaml``.
    """

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_nested_delimiter="__",
        extra="allow",
        case_sensitive=False,
    )

    VPC_CIDR: str = ""
    FQDN: str = ""
    CERTIFICATE_ARN: Optional[str] = None
    TAGS: Dict[str, Any] = Field(default_factory=dict)
    MONITORING: MonitoringConfig = Field(default_factory=MonitoringConfig)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        # Highest priority first. OS environment variables win over the file
        # layers; ``init_settings`` carries the per-call config file list that
        # ``load_context_config`` resolved (base first, env file last).
        #
        # Each file gets a source matching its extension (YAML or JSON), with
        # deep_merge so nested values from later files override individual keys
        # without discarding the rest of the block. Sources listed earlier win,
        # so the env file (listed last in ``_config_files``) is given a
        # higher-priority source than ``base.yaml``.
        config_files: List[Path] = init_settings.init_kwargs.get("_config_files", [])

        file_sources: List[PydanticBaseSettingsSource] = []
        for path in reversed(config_files):
            if path.suffix in JSON_SUFFIXES:
                file_sources.append(
                    JsonConfigSettingsSource(
                        settings_cls, json_file=path, deep_merge=True
                    )
                )
            else:
                file_sources.append(
                    YamlConfigSettingsSource(
                        settings_cls, yaml_file=path, deep_merge=True
                    )
                )

        return (env_settings, *file_sources)

    # ------------------------------------------------------------------ #
    # Backwards-compatible, dict-like access so existing call sites that
    # used the old plain-dict config keep working.
    # ------------------------------------------------------------------ #
    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


def load_context_config(
    env_name: str, config_dir: str = DEFAULT_CONFIG_DIR
) -> AppSettings:
    """Load typed settings for ``env_name``.

    Layers ``base.yaml`` and the per-environment file (the env file overriding
    the base, deep-merged) and finally applies any ``APP_``-prefixed operating
    system environment variables on top. The per-environment file may be YAML
    (``.yaml``/``.yml``) or JSON (``.json``).

    Raises:
        ValueError: if ``env_name`` is not one of dev/stage/prod, or if more
            than one per-environment config file exists.
        FileNotFoundError: if no per-environment config file is found.
    """

    if env_name not in VALID_ENVS:
        raise ValueError(
            f"Invalid environment '{env_name}'. "
            f"Must be one of: {', '.join(VALID_ENVS)}"
        )

    config_path = Path(config_dir)
    base_file = config_path / "base.yaml"

    # The env file may be YAML or JSON, but only one may exist.
    candidate_suffixes = YAML_SUFFIXES + JSON_SUFFIXES
    env_files = [
        config_path / f"{env_name}{suffix}"
        for suffix in candidate_suffixes
        if (config_path / f"{env_name}{suffix}").exists()
    ]

    if not env_files:
        expected = ", ".join(f"{env_name}{s}" for s in candidate_suffixes)
        raise FileNotFoundError(
            f"No config file found for environment '{env_name}' "
            f"in {config_dir}. Expected one of: {expected}"
        )

    if len(env_files) > 1:
        names = ", ".join(p.name for p in env_files)
        raise ValueError(
            f"Multiple config files found for environment '{env_name}': "
            f"{names}. Use only one (.yaml/.yml OR .json)."
        )

    # Order matters: base first, env file last so it overrides base.
    config_files = [p for p in (base_file, env_files[0]) if p.exists()]

    return AppSettings(_config_files=config_files)
