"""Tests unitarios de las utilidades de snapshots de logs en ClientLogs."""
from collections import deque

import services.broker_observability_service as broker_observability_svc
import services.clientlogs_service as clientlogs_svc


def test_process_log_snapshot_deduplicates_replayed_lines(monkeypatch):
    """El snapshot HTTP no debe reprocesar líneas ya vistas en polls posteriores."""
    processed: list[tuple[str, bool]] = []

    def fake_process_line(line: str, replay: bool = False):
        processed.append((line, replay))

    monkeypatch.setattr(clientlogs_svc.mqtt_monitor, "process_line", fake_process_line)

    recent_signatures: deque[str] = deque(maxlen=10)
    recent_signature_set: set[str] = set()

    first = clientlogs_svc._process_log_snapshot(
        [
            "2026-04-15T12:00:00: New client connected from 10.0.0.1:1883 as sensor-01 (p5, c1, k60)",
            "2026-04-15T12:00:01: sensor-01 0 greenhouse/temp",
        ],
        replay=True,
        recent_signatures=recent_signatures,
        recent_signature_set=recent_signature_set,
    )
    second = clientlogs_svc._process_log_snapshot(
        [
            "2026-04-15T12:00:00: New client connected from 10.0.0.1:1883 as sensor-01 (p5, c1, k60)",
            "2026-04-15T12:00:01: sensor-01 0 greenhouse/temp",
            "2026-04-15T12:00:05: Client sensor-01 closed its connection",
        ],
        replay=False,
        recent_signatures=recent_signatures,
        recent_signature_set=recent_signature_set,
    )

    assert first == 2
    assert second == 1
    assert processed == [
        ("2026-04-15T12:00:00: New client connected from 10.0.0.1:1883 as sensor-01 (p5, c1, k60)", True),
        ("2026-04-15T12:00:01: sensor-01 0 greenhouse/temp", True),
        ("2026-04-15T12:00:05: Client sensor-01 closed its connection", False),
    ]


def test_read_broker_logs_supports_incremental_offsets(monkeypatch, tmp_path):
    """La lectura broker-owned debe poder continuar desde un offset sin perder líneas."""
    log_path = tmp_path / "mosquitto.log"
    log_path.write_text("line-1\nline-2\nline-3\n", encoding="utf-8")

    monkeypatch.setattr(broker_observability_svc.settings, "broker_log_path", str(log_path))
    monkeypatch.setattr(broker_observability_svc.settings, "broker_log_read_enabled", True)

    initial = broker_observability_svc.read_broker_logs(limit=2)
    assert initial["logs"] == ["line-2", "line-3"]
    assert initial["rewound"] is False
    assert initial["next_offset"] == log_path.stat().st_size

    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("line-4\nline-5\n")

    incremental = broker_observability_svc.read_broker_logs(limit=10, offset=initial["next_offset"])
    assert incremental["logs"] == ["line-4", "line-5"]
    assert incremental["offset"] == initial["next_offset"]
    assert incremental["rewound"] is False

    rewound = broker_observability_svc.read_broker_logs(limit=10, offset=999999)
    assert rewound["logs"] == ["line-1", "line-2", "line-3", "line-4", "line-5"]
    assert rewound["rewound"] is True


def test_platform_internal_monitor_is_visible_as_admin_connection():
    """La conexion unica interna de BHM debe seguir visible como evidencia de que admin esta conectado al broker."""
    monitor = clientlogs_svc.MQTTMonitor()

    event = monitor.parse_connection_log(
        "2026-04-21T10:00:00: New client connected from 127.0.0.1:1883 as bunkerm-mqtt-monitor (p5, c1, k60, u'admin')"
    )

    assert event is not None
    assert monitor.connected_clients["bunkerm-mqtt-monitor"].username == "admin"