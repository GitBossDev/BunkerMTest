"""Tests unitarios de las utilidades de snapshots de logs en ClientLogs."""
from collections import deque

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