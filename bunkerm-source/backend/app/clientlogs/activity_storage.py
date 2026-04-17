from __future__ import annotations

import threading
import time

from core.config import settings
from core.database_url import ensure_postgres_url, get_sync_database_url
from clientlogs.sqlalchemy_activity_storage import SQLAlchemyClientActivityStorage


def create_client_activity_storage() -> SQLAlchemyClientActivityStorage:
    database_url = settings.resolved_history_database_url
    ensure_postgres_url(database_url, "HISTORY_DATABASE_URL")
    return SQLAlchemyClientActivityStorage(get_sync_database_url(database_url))


class _LazyClientActivityStorage:
    def __init__(self) -> None:
        self._storage: SQLAlchemyClientActivityStorage | None = None
        self._reconcile_lock = threading.Lock()
        self._last_dynsec_reconcile_at = 0.0

    def _get_storage(self) -> SQLAlchemyClientActivityStorage:
        if self._storage is None:
            self._storage = create_client_activity_storage()
        return self._storage

    def reconcile_dynsec_clients_throttled(self, clients, ttl_seconds: float = 30.0) -> None:
        now = time.monotonic()
        with self._reconcile_lock:
            if now - self._last_dynsec_reconcile_at < max(ttl_seconds, 0.0):
                return
            self._last_dynsec_reconcile_at = now
        self.reconcile_dynsec_clients(clients)

    def __getattr__(self, name: str):
        return getattr(self._get_storage(), name)


client_activity_storage = _LazyClientActivityStorage()