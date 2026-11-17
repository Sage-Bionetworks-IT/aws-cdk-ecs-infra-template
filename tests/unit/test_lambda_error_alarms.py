import json
import runpy
from pathlib import Path

import aws_cdk as cdk
import pytest

import src.utils

REPO_ROOT = Path(__file__).resolve().parents[2]


def _synth_app(env, tmp_path, monkeypatch, monitoring=None):
    """
    Synthesize the real app.py for `env` and return its templates by stack.
    `monitoring` overrides the config's MONITORING section when given.
    """
    context = json.loads((REPO_ROOT / "cdk.json").read_text())["context"]
    app = cdk.App(context={**context, "env": env}, outdir=str(tmp_path))
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setattr(cdk, "App", lambda: app)
    if monitoring is not None:
        load_config = src.utils.load_context_config
        monkeypatch.setattr(
            src.utils,
            "load_context_config",
            lambda **kwargs: {**load_config(**kwargs), "MONITORING": monitoring},
        )
    runpy.run_path(str(REPO_ROOT / "app.py"))
    return {
        path.name: json.loads(path.read_text())
        for path in tmp_path.glob("*.template.json")
    }


def _lambda_error_alarms_by_stack(templates):
    """Map each stack to (its Lambda logical ids, its AWS/Lambda alarm properties)."""
    result = {}
    for name, template in templates.items():
        resources = template.get("Resources", {})
        functions = {
            logical_id
            for logical_id, resource in resources.items()
            if resource["Type"] == "AWS::Lambda::Function"
        }
        alarms = [
            resource["Properties"]
            for resource in resources.values()
            if resource["Type"] == "AWS::CloudWatch::Alarm"
            and resource["Properties"].get("Namespace") == "AWS/Lambda"
        ]
        result[name] = (functions, alarms)
    return result


def _assert_every_lambda_alarmed(templates):
    function_count = 0
    for name, (functions, alarms) in _lambda_error_alarms_by_stack(templates).items():
        alarmed = {
            dim["Value"]["Ref"]
            for alarm in alarms
            for dim in alarm["Dimensions"]
            if dim["Name"] == "FunctionName"
        }
        assert alarmed == functions, name
        for alarm in alarms:
            assert alarm["MetricName"] == "Errors", name
        function_count += len(functions)
    assert function_count >= 1


@pytest.mark.parametrize("env", ["dev", "stage", "prod"])
def test_every_lambda_in_the_app_has_an_errors_alarm(env, tmp_path, monkeypatch):
    _assert_every_lambda_alarmed(_synth_app(env, tmp_path, monkeypatch))


def test_lambda_errors_alarms_notify_the_alarm_topic_with_monitoring(
    tmp_path, monkeypatch
):
    templates = _synth_app(
        "dev",
        tmp_path,
        monkeypatch,
        monitoring={"enabled": True, "notification_email": "test@example.com"},
    )
    assert any(name.endswith("-alarms.template.json") for name in templates)
    _assert_every_lambda_alarmed(templates)
    for name, (_, alarms) in _lambda_error_alarms_by_stack(templates).items():
        for alarm in alarms:
            assert alarm["AlarmActions"] and alarm["OKActions"], name
