"""Tests de integración ligeros sobre la costura broker-facing del reconciliador."""

from __future__ import annotations

import json

import services.broker_reconciler as broker_reconciler
from services.broker_runtime import LocalBrokerRuntime
import services.dynsec_service as dynsec_svc


def test_broker_reconciler_applies_mosquitto_config_and_creates_backup(tmp_path, monkeypatch):
    """La aplicación efectiva de mosquitto.conf debe escribir el archivo y dejar backup."""
    conf_path = tmp_path / "mosquitto.conf"
    backup_dir = tmp_path / "backups"
    conf_path.write_text("listener 1900\nallow_anonymous false\n", encoding="utf-8")
    backup_dir.mkdir()

    reload_calls: list[str] = []

    runtime = LocalBrokerRuntime(
        mosquitto_conf_path=str(conf_path),
        mosquitto_conf_backup_dir=str(backup_dir),
        mosquitto_certs_dir=str(tmp_path / "certs"),
    )
    monkeypatch.setattr(runtime, "signal_mosquitto_reload", lambda: reload_calls.append("reload"))

    reconciler = broker_reconciler.BrokerReconciler(runtime=runtime)
    result = reconciler.apply_mosquitto_config("listener 1900\nallow_anonymous true\n")

    assert result["errors"] == []
    assert result["rollbackNote"] is None
    assert conf_path.read_text(encoding="utf-8") == "listener 1900\nallow_anonymous true\n"
    assert reload_calls == ["reload"]
    assert len(list(backup_dir.iterdir())) == 1


def test_broker_reconciler_applies_default_acl_to_dynsec_and_calls_broker(tmp_path, monkeypatch):
    """El reconciliador debe proyectar ACL por defecto al JSON y emitir comandos broker-facing."""
    dynsec_path = tmp_path / "dynamic-security.json"
    dynsec_path.write_text(
        json.dumps(
            {
                "defaultACLAccess": {
                    "publishClientSend": True,
                    "publishClientReceive": True,
                    "subscribe": True,
                    "unsubscribe": True,
                },
                "clients": [],
                "roles": [],
                "groups": [],
            }
        ),
        encoding="utf-8",
    )

    commands: list[list[str]] = []

    def fake_execute(subcommand):
        commands.append(subcommand)
        return {"success": True, "output": "", "error_output": ""}

    monkeypatch.setattr(dynsec_svc.settings, "dynsec_path", str(dynsec_path))
    monkeypatch.setattr(dynsec_svc, "execute_mosquitto_command", fake_execute)

    reconciler = broker_reconciler.BrokerReconciler(runtime=LocalBrokerRuntime())
    desired = {
        "publishClientSend": False,
        "publishClientReceive": True,
        "subscribe": False,
        "unsubscribe": True,
    }

    errors = reconciler.apply_default_acl(desired)
    stored = json.loads(dynsec_path.read_text(encoding="utf-8"))

    assert errors == []
    assert stored["defaultACLAccess"] == desired
    assert commands == [
        ["setDefaultACLAccess", "publishClientSend", "deny"],
        ["setDefaultACLAccess", "publishClientReceive", "allow"],
        ["setDefaultACLAccess", "subscribe", "deny"],
        ["setDefaultACLAccess", "unsubscribe", "allow"],
    ]


def test_broker_reconciler_updates_group_client_priority_via_remove_and_add(tmp_path, monkeypatch):
    """Cambiar prioridad de membership debe reconciliar remove/add y persistir el valor observado."""
    dynsec_path = tmp_path / "dynamic-security.json"
    dynsec_path.write_text(
        json.dumps(
            {
                "defaultACLAccess": {},
                "clients": [{"username": "sensor-01"}],
                "roles": [],
                "groups": [
                    {
                        "groupname": "plantas",
                        "roles": [],
                        "clients": [{"username": "sensor-01", "priority": 1}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    commands: list[list[str]] = []

    def fake_execute(subcommand):
        commands.append(subcommand)
        return {"success": True, "output": "", "error_output": ""}

    monkeypatch.setattr(dynsec_svc.settings, "dynsec_path", str(dynsec_path))
    monkeypatch.setattr(dynsec_svc, "execute_mosquitto_command", fake_execute)

    reconciler = broker_reconciler.BrokerReconciler(runtime=LocalBrokerRuntime())
    errors = reconciler.apply_group_projection(
        "plantas",
        {
            "groupname": "plantas",
            "roles": [],
            "clients": [{"username": "sensor-01", "priority": 3}],
            "deleted": False,
        },
    )
    stored = json.loads(dynsec_path.read_text(encoding="utf-8"))

    assert errors == []
    assert commands == [
        ["removeGroupClient", "plantas", "sensor-01"],
        ["addGroupClient", "plantas", "sensor-01", "--priority", "3"],
    ]
    assert stored["groups"][0]["clients"] == [{"username": "sensor-01", "priority": 3}]


def test_broker_reconciler_applies_dynsec_config_and_signals_dynsec_restart(tmp_path, monkeypatch):
    """La reconciliación completa de DynSec debe escribir el JSON y señalizar reinicio del broker."""
    dynsec_path = tmp_path / "dynamic-security.json"
    dynsec_path.write_text(
        json.dumps(
            {
                "defaultACLAccess": {
                    "publishClientSend": True,
                    "publishClientReceive": True,
                    "subscribe": True,
                    "unsubscribe": True,
                },
                "clients": [],
                "roles": [],
                "groups": [],
            }
        ),
        encoding="utf-8",
    )

    restart_calls: list[str] = []
    monkeypatch.setattr(dynsec_svc.settings, "dynsec_path", str(dynsec_path))

    runtime = LocalBrokerRuntime(
        mosquitto_conf_path=str(tmp_path / "mosquitto.conf"),
        mosquitto_conf_backup_dir=str(tmp_path / "backups"),
        mosquitto_certs_dir=str(tmp_path / "certs"),
    )
    monkeypatch.setattr(runtime, "signal_dynsec_reload", lambda: restart_calls.append("dynsec-restart"))

    reconciler = broker_reconciler.BrokerReconciler(runtime=runtime)
    result = reconciler.apply_dynsec_config(
        {
            "defaultACLAccess": {
                "publishClientSend": False,
                "publishClientReceive": True,
                "subscribe": False,
                "unsubscribe": True,
            },
            "clients": [{"username": "sensor-02", "roles": [], "groups": []}],
            "roles": [],
            "groups": [],
        }
    )

    stored = json.loads(dynsec_path.read_text(encoding="utf-8"))
    assert result["errors"] == []
    assert result["rollbackNote"] is None
    assert stored["defaultACLAccess"]["publishClientSend"] is False
    assert stored["clients"][0]["username"] == "sensor-02"
    assert restart_calls == ["dynsec-restart"]
