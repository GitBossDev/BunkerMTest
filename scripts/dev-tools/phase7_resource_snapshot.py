from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def parse_kubectl_top_output(raw_output: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in raw_output.splitlines() if line.strip()]
    if len(lines) <= 1:
        return []

    rows: list[dict[str, Any]] = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 3:
            continue
        rows.append(
            {
                "pod": parts[0],
                "cpu": parts[1],
                "memory": parts[2],
            }
        )
    return rows


def parse_podman_stats_output(raw_output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in raw_output.splitlines():
        normalized_line = line.strip()
        if not normalized_line:
            continue
        payload = json.loads(normalized_line)
        rows.append(payload)
    return rows


def parse_crictl_stats_output(raw_output: str, namespace: str) -> list[dict[str, Any]]:
    payload = json.loads(raw_output)
    aggregated: dict[str, dict[str, Any]] = {}

    for item in payload.get("stats", []):
        labels = item.get("attributes", {}).get("labels", {})
        if labels.get("io.kubernetes.pod.namespace") != namespace:
            continue

        pod_name = labels.get("io.kubernetes.pod.name")
        if not pod_name:
            continue

        entry = aggregated.setdefault(
            pod_name,
            {
                "pod": pod_name,
                "cpuNanoCores": 0,
                "memoryWorkingSetBytes": 0,
                "containers": [],
                "source": "crictl",
            },
        )
        entry["cpuNanoCores"] += int(item.get("cpu", {}).get("usageNanoCores", {}).get("value", "0"))
        entry["memoryWorkingSetBytes"] += int(item.get("memory", {}).get("workingSetBytes", {}).get("value", "0"))

        container_name = item.get("attributes", {}).get("metadata", {}).get("name")
        if container_name:
            entry["containers"].append(container_name)

    rows = []
    for pod_name in sorted(aggregated):
        entry = aggregated[pod_name]
        rows.append(
            {
                **entry,
                "cpuMilliCores": round(entry["cpuNanoCores"] / 1_000_000, 2),
                "memoryMiB": round(entry["memoryWorkingSetBytes"] / (1024 * 1024), 2),
            }
        )
    return rows


def _read_podman_container_names() -> list[str]:
    result = _run_command(["podman", "ps", "--format", "{{.Names}}"])
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _resolve_kind_node_names(explicit_node_name: str | None, cluster_name: str) -> list[str]:
    if explicit_node_name:
        return [explicit_node_name]

    container_names = _read_podman_container_names()
    return [name for name in container_names if name.startswith(f"{cluster_name}-")]


def _merge_crictl_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aggregated: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = aggregated.setdefault(
            row["pod"],
            {
                "pod": row["pod"],
                "cpuNanoCores": 0,
                "memoryWorkingSetBytes": 0,
                "containers": [],
                "source": "crictl",
            },
        )
        entry["cpuNanoCores"] += row["cpuNanoCores"]
        entry["memoryWorkingSetBytes"] += row["memoryWorkingSetBytes"]
        entry["containers"].extend(row.get("containers", []))

    merged_rows = []
    for pod_name in sorted(aggregated):
        entry = aggregated[pod_name]
        merged_rows.append(
            {
                **entry,
                "containers": sorted(set(entry["containers"])),
                "cpuMilliCores": round(entry["cpuNanoCores"] / 1_000_000, 2),
                "memoryMiB": round(entry["memoryWorkingSetBytes"] / (1024 * 1024), 2),
            }
        )
    return merged_rows


def _collect_kind_snapshot(namespace: str, container_engine: str, cluster_name: str, kind_node_name: str | None) -> dict[str, Any]:
    if shutil.which("kubectl") is None:
        return {"status": "skipped", "reason": "kubectl not available"}

    top_result = _run_command(["kubectl", "top", "pods", "-n", namespace, "--no-headers=false"])
    pvc_result = _run_command(["kubectl", "get", "pvc", "-n", namespace, "-o", "json"])

    status = "ok"
    errors: list[str] = []
    warnings: list[str] = []
    pod_usage: list[dict[str, Any]] = []
    storage: list[dict[str, Any]] = []
    pod_usage_source = "kubectl-top"

    if top_result.returncode == 0:
        pod_usage = parse_kubectl_top_output(top_result.stdout)
    else:
        fallback_error = (top_result.stderr or top_result.stdout).strip()
        warnings.append(fallback_error)
        resolved_node_names = _resolve_kind_node_names(kind_node_name, cluster_name)
        if shutil.which(container_engine) is not None and resolved_node_names:
            fallback_rows: list[dict[str, Any]] = []
            fallback_failures: list[str] = []
            for node_name in resolved_node_names:
                fallback_result = _run_command([container_engine, "exec", node_name, "crictl", "stats", "--output", "json"])
                if fallback_result.returncode == 0:
                    fallback_rows.extend(parse_crictl_stats_output(fallback_result.stdout, namespace))
                else:
                    fallback_failures.append((fallback_result.stderr or fallback_result.stdout).strip())

            if fallback_rows:
                pod_usage = _merge_crictl_rows(fallback_rows)
                pod_usage_source = "crictl"
            else:
                status = "degraded"
                errors.append(fallback_error)
                errors.extend(fallback_failures[:4])
        else:
            status = "degraded"
            errors.append(fallback_error)

    if pvc_result.returncode == 0:
        pvc_payload = json.loads(pvc_result.stdout)
        for item in pvc_payload.get("items", []):
            storage.append(
                {
                    "name": item["metadata"]["name"],
                    "status": item["status"].get("phase"),
                    "capacity": item["status"].get("capacity", {}).get("storage"),
                    "storageClass": item["spec"].get("storageClassName"),
                }
            )
    else:
        status = "degraded"
        errors.append((pvc_result.stderr or pvc_result.stdout).strip())

    if not pod_usage:
        status = "degraded"

    return {
        "status": status,
        "runtime": "kind",
        "namespace": namespace,
        "podUsage": pod_usage,
        "podUsageSource": pod_usage_source,
        "storage": storage,
        "errors": [error for error in errors if error][:5],
        "warnings": [warning for warning in warnings if warning][:5],
    }


def _collect_compose_snapshot(container_engine: str) -> dict[str, Any]:
    if shutil.which(container_engine) is None:
        return {"status": "skipped", "reason": f"{container_engine} not available"}

    stats_result = _run_command([container_engine, "stats", "--no-stream", "--format", "json"])
    if stats_result.returncode != 0:
        return {
            "status": "degraded",
            "runtime": "compose",
            "errors": [((stats_result.stderr or stats_result.stdout).strip())],
            "containers": [],
        }

    return {
        "status": "ok",
        "runtime": "compose",
        "containers": parse_podman_stats_output(stats_result.stdout),
        "errors": [],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Captura snapshot inicial de recursos para Fase 7.")
    parser.add_argument("--runtime", choices=["kind", "compose"], default="kind")
    parser.add_argument("--namespace", default="bhm-lab")
    parser.add_argument("--container-engine", default="podman")
    parser.add_argument("--kind-cluster-name", default="bhm-lab")
    parser.add_argument("--kind-node-name")
    parser.add_argument("--output")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.runtime == "kind":
        snapshot = _collect_kind_snapshot(args.namespace, args.container_engine, args.kind_cluster_name, args.kind_node_name)
    else:
        snapshot = _collect_compose_snapshot(args.container_engine)

    payload = {
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        **snapshot,
    }
    serialized = json.dumps(payload, ensure_ascii=True, indent=2)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized + "\n", encoding="utf-8")

    print(serialized)
    return 0 if payload.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())