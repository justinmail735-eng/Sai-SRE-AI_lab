#!/usr/bin/env python3
"""Generate and verify observability-as-code from a service specification."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.contracts import AgentResult, ValidationResult

REQUIRED_METRICS = {
    "request_rate",
    "error_rate",
    "latency_p95",
    "cpu_utilization",
}
SAFE_NAME = re.compile(r"^[a-z][a-z0-9-]{1,62}$")


def load_spec(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read service specification '{path}': {exc}") from exc
    validate_spec(data)
    return data


def validate_spec(data: dict[str, Any]) -> None:
    if data.get("api_version") != "saiops/v1":
        raise ValueError("api_version must be 'saiops/v1'")
    if data.get("kind") != "ServiceObservability":
        raise ValueError("kind must be 'ServiceObservability'")

    metadata = data.get("metadata")
    spec = data.get("spec")
    if not isinstance(metadata, dict) or not isinstance(spec, dict):
        raise ValueError("metadata and spec must be objects")

    name = metadata.get("name", "")
    if not isinstance(name, str) or not SAFE_NAME.fullmatch(name):
        raise ValueError("metadata.name must be a lowercase DNS-style service name")
    for field in ("owner", "environment", "cloud"):
        if not isinstance(metadata.get(field), str) or not metadata[field].strip():
            raise ValueError(f"metadata.{field} must be a non-empty string")
    if metadata["cloud"] not in {"aws", "azure", "multi-cloud", "local"}:
        raise ValueError("metadata.cloud must be aws, azure, multi-cloud, or local")

    metrics = spec.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("spec.metrics must be an object")
    missing = sorted(REQUIRED_METRICS - set(metrics))
    if missing:
        raise ValueError(f"spec.metrics is missing required metrics: {', '.join(missing)}")
    for logical_name, query in metrics.items():
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"spec.metrics.{logical_name} must be a non-empty query")

    slo = spec.get("slo")
    if not isinstance(slo, dict):
        raise ValueError("spec.slo must be an object")
    target = float(slo.get("availability_target", 0))
    latency = int(slo.get("latency_p95_ms", 0))
    if not 0.9 <= target < 1:
        raise ValueError("spec.slo.availability_target must be between 0.9 and 1")
    if latency <= 0:
        raise ValueError("spec.slo.latency_p95_ms must be positive")

    alerts = spec.get("alerts")
    if not isinstance(alerts, dict):
        raise ValueError("spec.alerts must be an object")
    warning = float(alerts.get("warning_burn_rate", 0))
    critical = float(alerts.get("critical_burn_rate", 0))
    if warning <= 0 or critical <= warning:
        raise ValueError("alert burn rates must be positive and critical must exceed warning")


def grafana_dashboard(data: dict[str, Any]) -> dict[str, Any]:
    metadata = data["metadata"]
    metrics = data["spec"]["metrics"]
    panels = []
    panel_titles = {
        "request_rate": "Request rate",
        "error_rate": "Error rate",
        "latency_p95": "Latency p95",
        "cpu_utilization": "CPU utilization",
    }
    for index, logical_name in enumerate(sorted(REQUIRED_METRICS), start=1):
        panels.append(
            {
                "id": index,
                "title": panel_titles[logical_name],
                "type": "timeseries",
                "datasource": {"type": "prometheus", "uid": "${datasource}"},
                "targets": [{"refId": "A", "expr": metrics[logical_name]}],
                "gridPos": {
                    "h": 8,
                    "w": 12,
                    "x": 0 if index % 2 else 12,
                    "y": ((index - 1) // 2) * 8,
                },
            }
        )
    return {
        "title": f"{metadata['name']} — Golden Signals",
        "uid": f"sai-{metadata['name']}",
        "schemaVersion": 39,
        "editable": False,
        "tags": ["sai-ops", metadata["cloud"], metadata["environment"]],
        "templating": {
            "list": [
                {
                    "name": "datasource",
                    "type": "datasource",
                    "query": "prometheus",
                    "current": {"text": "Prometheus", "value": "Prometheus"},
                }
            ]
        },
        "panels": panels,
        "time": {"from": "now-1h", "to": "now"},
    }


def prometheus_rules(data: dict[str, Any]) -> str:
    metadata = data["metadata"]
    spec = data["spec"]
    name = metadata["name"]
    owner = metadata["owner"]
    error_query = spec["metrics"]["error_rate"]
    latency_query = spec["metrics"]["latency_p95"]
    warning = float(spec["alerts"]["warning_burn_rate"])
    critical = float(spec["alerts"]["critical_burn_rate"])
    latency = int(spec["slo"]["latency_p95_ms"])
    budget = 1 - float(spec["slo"]["availability_target"])
    return f"""# Generated by ObservabilityEngineerAgent. Do not edit manually.
groups:
  - name: {name}.slo
    rules:
      - alert: {name.replace('-', '_')}_error_budget_fast_burn
        expr: ({error_query}) / {budget:.6f} >= {critical:g}
        for: 5m
        labels:
          severity: critical
          service: {name}
          owner: {owner}
        annotations:
          summary: {name} is consuming its error budget rapidly
          runbook: {spec['runbook_url']}
      - alert: {name.replace('-', '_')}_error_budget_slow_burn
        expr: ({error_query}) / {budget:.6f} >= {warning:g}
        for: 30m
        labels:
          severity: warning
          service: {name}
          owner: {owner}
        annotations:
          summary: {name} has sustained error-budget burn
          runbook: {spec['runbook_url']}
      - alert: {name.replace('-', '_')}_latency_slo_violation
        expr: ({latency_query}) > {latency}
        for: 10m
        labels:
          severity: warning
          service: {name}
          owner: {owner}
        annotations:
          summary: {name} p95 latency exceeds {latency}ms
          runbook: {spec['runbook_url']}
"""


def artifact_payloads(data: dict[str, Any]) -> dict[str, str]:
    dashboard = json.dumps(grafana_dashboard(data), indent=2, sort_keys=True) + "\n"
    rules = prometheus_rules(data)
    return {"dashboard.json": dashboard, "prometheus-rules.yaml": rules}


def validate_artifacts(data: dict[str, Any], payloads: dict[str, str]) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    try:
        dashboard = json.loads(payloads["dashboard.json"])
        panel_titles = {panel["title"] for panel in dashboard["panels"]}
        expected = {"Request rate", "Error rate", "Latency p95", "CPU utilization"}
        passed = panel_titles == expected and dashboard["editable"] is False
        results.append(ValidationResult("grafana-dashboard", passed, "golden-signal panels and immutable dashboard"))
    except (KeyError, json.JSONDecodeError, TypeError) as exc:
        results.append(ValidationResult("grafana-dashboard", False, str(exc)))

    rules = payloads["prometheus-rules.yaml"]
    required_fragments = ["fast_burn", "slow_burn", "latency_slo_violation", data["spec"]["runbook_url"]]
    rules_valid = all(fragment in rules for fragment in required_fragments)
    results.append(ValidationResult("prometheus-rules", rules_valid, "burn-rate, latency, and runbook coverage"))
    results.append(
        ValidationResult(
            "approval-policy",
            True,
            "agent produces reviewable files only; no infrastructure or production mutation",
        )
    )
    return results


def run_agent(spec_path: Path, output_dir: Path, check: bool = False) -> AgentResult:
    data = load_spec(spec_path)
    payloads = artifact_payloads(data)
    validations = validate_artifacts(data, payloads)
    result = AgentResult(
        agent="ObservabilityEngineerAgent",
        objective=f"Create golden-signal observability for {data['metadata']['name']}",
        mode="check" if check else "generate",
        risk="low",
        approval_required=False,
        evidence=[
            f"service owner: {data['metadata']['owner']}",
            f"cloud: {data['metadata']['cloud']}",
            f"availability target: {data['spec']['slo']['availability_target']}",
            "four required golden-signal queries supplied",
        ],
        artifacts=[str(output_dir / name) for name in sorted(payloads)],
        validations=validations,
        changes_applied=not check,
    )

    if check:
        for filename, expected in payloads.items():
            target = output_dir / filename
            actual = target.read_text(encoding="utf-8") if target.exists() else None
            result.validations.append(
                ValidationResult(
                    f"drift:{filename}",
                    actual == expected,
                    "generated artifact matches service specification" if actual == expected else "artifact missing or stale",
                )
            )
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in payloads.items():
            (output_dir / filename).write_text(content, encoding="utf-8")
        (output_dir / "agent-result.json").write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="fail when checked-in artifacts drift from the specification")
    parser.add_argument("--output", choices=("text", "json"), default="text")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = run_agent(args.spec, args.output_dir, check=args.check)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.output == "json":
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        state = "PASS" if result.successful else "FAIL"
        print(f"{state} {result.agent}: {result.objective}")
        for validation in result.validations:
            print(f"  {'PASS' if validation.passed else 'FAIL'} {validation.name}: {validation.details}")
    return 0 if result.successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
