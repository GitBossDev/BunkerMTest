from __future__ import annotations

import importlib.util
import pathlib
import sys


def _load_phase7_resource_snapshot_module():
    script_path = pathlib.Path(__file__).parents[4] / "scripts" / "dev-tools" / "phase7_resource_snapshot.py"
    spec = importlib.util.spec_from_file_location("phase7_resource_snapshot", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


phase7_resource_snapshot = _load_phase7_resource_snapshot_module()


def test_parse_kubectl_top_output_reads_pod_rows():
    payload = "NAME CPU(cores) MEMORY(bytes)\nbunkerm-platform-abc 12m 186Mi\nmosquitto-0 5m 91Mi\n"

    rows = phase7_resource_snapshot.parse_kubectl_top_output(payload)

    assert rows == [
        {"pod": "bunkerm-platform-abc", "cpu": "12m", "memory": "186Mi"},
        {"pod": "mosquitto-0", "cpu": "5m", "memory": "91Mi"},
    ]


def test_parse_podman_stats_output_reads_json_lines():
    payload = '{"Name":"bunkerm-platform","CPUPerc":"1.2%"}\n{"Name":"bunkerm-mosquitto","CPUPerc":"0.3%"}\n'

    rows = phase7_resource_snapshot.parse_podman_stats_output(payload)

    assert rows == [
        {"Name": "bunkerm-platform", "CPUPerc": "1.2%"},
        {"Name": "bunkerm-mosquitto", "CPUPerc": "0.3%"},
    ]


def test_parse_crictl_stats_output_aggregates_by_pod_and_namespace():
        payload = """{
            \"stats\": [
                {
                    \"attributes\": {
                        \"metadata\": {\"name\": \"platform\"},
                        \"labels\": {
                            \"io.kubernetes.pod.namespace\": \"bhm-lab\",
                            \"io.kubernetes.pod.name\": \"bunkerm-platform-abc\"
                        }
                    },
                    \"cpu\": {\"usageNanoCores\": {\"value\": \"2000000\"}},
                    \"memory\": {\"workingSetBytes\": {\"value\": \"10485760\"}}
                },
                {
                    \"attributes\": {
                        \"metadata\": {\"name\": \"sidecar\"},
                        \"labels\": {
                            \"io.kubernetes.pod.namespace\": \"bhm-lab\",
                            \"io.kubernetes.pod.name\": \"bunkerm-platform-abc\"
                        }
                    },
                    \"cpu\": {\"usageNanoCores\": {\"value\": \"3000000\"}},
                    \"memory\": {\"workingSetBytes\": {\"value\": \"5242880\"}}
                },
                {
                    \"attributes\": {
                        \"metadata\": {\"name\": \"ignored\"},
                        \"labels\": {
                            \"io.kubernetes.pod.namespace\": \"kube-system\",
                            \"io.kubernetes.pod.name\": \"coredns\"
                        }
                    },
                    \"cpu\": {\"usageNanoCores\": {\"value\": \"999\"}},
                    \"memory\": {\"workingSetBytes\": {\"value\": \"999\"}}
                }
            ]
        }"""

        rows = phase7_resource_snapshot.parse_crictl_stats_output(payload, "bhm-lab")

        assert rows == [
                {
                        "pod": "bunkerm-platform-abc",
                        "cpuNanoCores": 5000000,
                        "memoryWorkingSetBytes": 15728640,
                        "containers": ["platform", "sidecar"],
                        "source": "crictl",
                        "cpuMilliCores": 5.0,
                        "memoryMiB": 15.0,
                }
        ]