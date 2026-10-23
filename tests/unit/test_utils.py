import json
import tempfile
import textwrap
from pathlib import Path

import pytest

from src.utils import (
    AlarmThresholds,
    AppSettings,
    MonitoringConfig,
    load_context_config,
)


def _write(config_dir: Path, name: str, content: str) -> None:
    (config_dir / name).write_text(textwrap.dedent(content))


class TestLoadContextConfig:
    """Test suite for the pydantic-settings based load_context_config."""

    @pytest.mark.parametrize(
        "invalid_env", ["invalid", "test", "production", "development", ""]
    )
    def test_invalid_environment_raises_value_error(self, invalid_env):
        """Invalid environment names raise ValueError."""
        with pytest.raises(ValueError, match=f"Invalid environment '{invalid_env}'"):
            load_context_config(invalid_env)

    @pytest.mark.parametrize("valid_env", ["dev", "stage", "prod"])
    def test_valid_environments(self, valid_env):
        """Valid environment names load their per-environment file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            d = Path(temp_dir)
            _write(
                d,
                f"{valid_env}.yaml",
                f"""
                FQDN: {valid_env}.example.com
                VPC_CIDR: 10.0.0.0/16
                TAGS:
                  Environment: {valid_env}
                """,
            )

            result = load_context_config(valid_env, temp_dir)
            assert result.FQDN == f"{valid_env}.example.com"
            assert result.TAGS["Environment"] == valid_env

    def test_no_env_file_raises_file_not_found_error(self):
        """A missing per-environment file raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(
                FileNotFoundError, match="No config file found for environment 'dev'"
            ):
                load_context_config("dev", temp_dir)

    @pytest.mark.parametrize(
        "extensions", [(".yaml", ".json"), (".yaml", ".yml"), (".yml", ".json")]
    )
    def test_multiple_env_files_raises_value_error(self, extensions):
        """More than one per-environment file raises ValueError."""
        with tempfile.TemporaryDirectory() as temp_dir:
            d = Path(temp_dir)
            for ext in extensions:
                if ext == ".json":
                    (d / f"dev{ext}").write_text(json.dumps({"FQDN": "x"}))
                else:
                    _write(d, f"dev{ext}", "FQDN: x\n")

            with pytest.raises(
                ValueError, match="Multiple config files found for environment 'dev'"
            ):
                load_context_config("dev", temp_dir)

    def test_returns_app_settings_instance(self):
        """load_context_config returns a typed AppSettings object."""
        with tempfile.TemporaryDirectory() as temp_dir:
            d = Path(temp_dir)
            _write(
                d,
                "dev.yaml",
                """
                FQDN: dev.example.com
                VPC_CIDR: 10.0.0.0/16
                """,
            )
            result = load_context_config("dev", temp_dir)
            assert isinstance(result, AppSettings)
            assert isinstance(result.MONITORING, MonitoringConfig)
            assert isinstance(result.MONITORING.alarms, AlarmThresholds)


class TestBaseAndEnvFileMerge:
    """Requirement: base.yaml plus a per-environment file, env file overrides."""

    def test_env_file_overrides_base_top_level(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            d = Path(temp_dir)
            _write(
                d,
                "base.yaml",
                """
                VPC_CIDR: 10.0.0.0/16
                FQDN: base.example.com
                TAGS:
                  CostCenter: base
                """,
            )
            _write(
                d,
                "dev.yaml",
                """
                FQDN: dev.example.com
                """,
            )

            result = load_context_config("dev", temp_dir)
            # from env file (overrides base)
            assert result.FQDN == "dev.example.com"
            # inherited from base
            assert result.VPC_CIDR == "10.0.0.0/16"
            assert result.TAGS["CostCenter"] == "base"

    def test_env_file_overrides_single_nested_monitoring_value(self):
        """A single nested value inside MONITORING can be overridden alone."""
        with tempfile.TemporaryDirectory() as temp_dir:
            d = Path(temp_dir)
            _write(
                d,
                "base.yaml",
                """
                MONITORING:
                  enabled: false
                  notification_email: ""
                  alarms:
                    ecs_cpu_threshold: 80
                    ecs_memory_threshold: 80
                """,
            )
            _write(
                d,
                "dev.yaml",
                """
                FQDN: dev.example.com
                VPC_CIDR: 10.0.0.0/16
                MONITORING:
                  enabled: true
                  notification_email: team@example.com
                  alarms:
                    ecs_cpu_threshold: 90
                """,
            )

            result = load_context_config("dev", temp_dir)
            mon = result.MONITORING
            # overridden by env file
            assert mon.enabled is True
            assert mon.notification_email == "team@example.com"
            assert mon.alarms.ecs_cpu_threshold == 90
            # untouched nested value still comes from base (deep merge)
            assert mon.alarms.ecs_memory_threshold == 80

    def test_no_base_file_uses_env_file_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            d = Path(temp_dir)
            _write(
                d,
                "dev.yaml",
                """
                FQDN: dev.example.com
                VPC_CIDR: 10.0.0.0/16
                """,
            )
            result = load_context_config("dev", temp_dir)
            assert result.FQDN == "dev.example.com"

    def test_empty_env_file_falls_back_to_base(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            d = Path(temp_dir)
            _write(
                d,
                "base.yaml",
                """
                VPC_CIDR: 10.0.0.0/16
                FQDN: base.example.com
                """,
            )
            _write(d, "dev.yaml", "")
            result = load_context_config("dev", temp_dir)
            assert result.VPC_CIDR == "10.0.0.0/16"


class TestJsonEnvFile:
    """The per-environment file may be JSON instead of YAML."""

    def test_json_env_file_loads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            d = Path(temp_dir)
            (d / "dev.json").write_text(
                json.dumps({"FQDN": "dev.example.com", "VPC_CIDR": "10.0.0.0/16"})
            )
            result = load_context_config("dev", temp_dir)
            assert result.FQDN == "dev.example.com"
            assert result.VPC_CIDR == "10.0.0.0/16"

    def test_json_env_file_deep_merges_over_yaml_base(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            d = Path(temp_dir)
            _write(
                d,
                "base.yaml",
                """
                MONITORING:
                  enabled: false
                  alarms:
                    ecs_cpu_threshold: 80
                    ecs_memory_threshold: 80
                """,
            )
            (d / "dev.json").write_text(
                json.dumps(
                    {
                        "FQDN": "dev.example.com",
                        "VPC_CIDR": "10.0.0.0/16",
                        "MONITORING": {
                            "enabled": True,
                            "alarms": {"ecs_cpu_threshold": 42},
                        },
                    }
                )
            )
            result = load_context_config("dev", temp_dir)
            mon = result.MONITORING
            # from JSON env file
            assert mon.enabled is True
            assert mon.alarms.ecs_cpu_threshold == 42
            # untouched nested value still from the YAML base (deep merge)
            assert mon.alarms.ecs_memory_threshold == 80

    def test_env_var_overrides_json_env_file(self, monkeypatch):
        with tempfile.TemporaryDirectory() as temp_dir:
            d = Path(temp_dir)
            (d / "dev.json").write_text(
                json.dumps({"FQDN": "dev.example.com", "VPC_CIDR": "10.0.0.0/16"})
            )
            monkeypatch.setenv("APP_FQDN", "ci.example.com")
            result = load_context_config("dev", temp_dir)
            assert result.FQDN == "ci.example.com"


class TestEnvironmentVariableOverrides:
    """Requirement: an OS env var overrides whatever is in the files."""

    def test_env_var_overrides_top_level_value(self, monkeypatch):
        with tempfile.TemporaryDirectory() as temp_dir:
            d = Path(temp_dir)
            _write(
                d,
                "base.yaml",
                """
                FQDN: base.example.com
                VPC_CIDR: 10.0.0.0/16
                """,
            )
            _write(d, "dev.yaml", "FQDN: dev.example.com\n")

            monkeypatch.setenv("APP_FQDN", "ci.example.com")
            result = load_context_config("dev", temp_dir)
            assert result.FQDN == "ci.example.com"

    def test_env_var_overrides_single_nested_monitoring_value(self, monkeypatch):
        with tempfile.TemporaryDirectory() as temp_dir:
            d = Path(temp_dir)
            _write(
                d,
                "base.yaml",
                """
                VPC_CIDR: 10.0.0.0/16
                MONITORING:
                  alarms:
                    ecs_cpu_threshold: 80
                    ecs_memory_threshold: 80
                """,
            )
            _write(
                d,
                "dev.yaml",
                """
                FQDN: dev.example.com
                MONITORING:
                  alarms:
                    ecs_cpu_threshold: 90
                """,
            )

            monkeypatch.setenv("APP_MONITORING__ALARMS__ECS_CPU_THRESHOLD", "55")
            result = load_context_config("dev", temp_dir)
            # env var wins over both files for this nested value
            assert result.MONITORING.alarms.ecs_cpu_threshold == 55
            # other nested values untouched
            assert result.MONITORING.alarms.ecs_memory_threshold == 80

    def test_env_var_overrides_boolean_in_monitoring(self, monkeypatch):
        with tempfile.TemporaryDirectory() as temp_dir:
            d = Path(temp_dir)
            _write(
                d,
                "dev.yaml",
                """
                FQDN: dev.example.com
                VPC_CIDR: 10.0.0.0/16
                MONITORING:
                  enabled: true
                """,
            )

            monkeypatch.setenv("APP_MONITORING__ENABLED", "false")
            result = load_context_config("dev", temp_dir)
            assert result.MONITORING.enabled is False


class TestDictCompatibility:
    """AppSettings supports dict-style access for backward compatibility."""

    def test_getitem_and_get(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            d = Path(temp_dir)
            _write(
                d,
                "dev.yaml",
                """
                FQDN: dev.example.com
                VPC_CIDR: 10.0.0.0/16
                """,
            )
            result = load_context_config("dev", temp_dir)

            assert result["FQDN"] == "dev.example.com"
            assert result.get("FQDN") == "dev.example.com"
            assert result.get("DOES_NOT_EXIST", "fallback") == "fallback"
            with pytest.raises(KeyError):
                _ = result["DOES_NOT_EXIST"]
