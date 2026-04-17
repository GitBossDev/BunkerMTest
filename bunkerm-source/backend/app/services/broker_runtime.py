"""Adaptadores de runtime broker-facing para el control-plane transicional."""
from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Protocol

from config.mosquitto_config import _signal_mosquitto_reload, _signal_mosquitto_restart
from core.config import settings
from services import dynsec_service


def _signal_dynsec_reload() -> None:
    marker_path = os.path.join(os.path.dirname(settings.dynsec_path), ".dynsec-reload")
    with open(marker_path, "w", encoding="utf-8") as handle:
        handle.write("")


class BrokerRuntimePort(Protocol):
    mosquitto_conf_path: str
    mosquitto_conf_backup_dir: str
    mosquitto_passwd_path: str
    mosquitto_certs_dir: str

    @contextmanager
    def locked_dynsec(self) -> Iterator[None]:
        ...

    def read_dynsec(self) -> Dict[str, Any]:
        ...

    def write_dynsec(self, data: Dict[str, Any]) -> None:
        ...

    def execute_dynsec_command(self, subcommand: List[str]) -> Dict[str, Any]:
        ...

    def signal_mosquitto_reload(self) -> None:
        ...

    def signal_mosquitto_restart(self) -> None:
        ...

    def signal_dynsec_reload(self) -> None:
        ...


@dataclass
class LocalBrokerRuntime:
    """Implementación local in-process del runtime broker-facing."""

    mosquitto_conf_path: str = settings.mosquitto_conf_path
    mosquitto_conf_backup_dir: str = settings.mosquitto_conf_backup_dir
    mosquitto_passwd_path: str = settings.mosquitto_passwd_path
    mosquitto_certs_dir: str = settings.mosquitto_certs_dir

    @contextmanager
    def locked_dynsec(self) -> Iterator[None]:
        with dynsec_service._dynsec_lock:
            yield

    def read_dynsec(self) -> Dict[str, Any]:
        return dynsec_service.read_dynsec()

    def write_dynsec(self, data: Dict[str, Any]) -> None:
        dynsec_service.write_dynsec(data)

    def execute_dynsec_command(self, subcommand: List[str]) -> Dict[str, Any]:
        return dynsec_service.execute_mosquitto_command(subcommand)

    def signal_mosquitto_reload(self) -> None:
        _signal_mosquitto_reload()

    def signal_mosquitto_restart(self) -> None:
        _signal_mosquitto_restart()

    def signal_dynsec_reload(self) -> None:
        _signal_dynsec_reload()


def get_local_broker_runtime() -> LocalBrokerRuntime:
    return LocalBrokerRuntime()