"""
Configuración centralizada de la aplicación con pydantic-settings.
Todas las variables de entorno usadas por los microservicios anteriores
están definidas aquí como un único punto de verdad.
"""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Autenticación ---
    api_key: str = "default_api_key_replace_in_production"
    jwt_secret: str = "default_jwt_secret_replace_in_production"
    auth_secret: str = "default_auth_secret_replace_in_production"

    # --- CORS / Hosts ---
    allowed_origins: str = "http://localhost:3000,http://localhost"
    allowed_hosts: str = "localhost,127.0.0.1"
    frontend_url: str = "http://localhost:3000"

    # --- MQTT ---
    mqtt_broker: str = "127.0.0.1"
    mqtt_port: int = 1900
    mqtt_username: str = ""
    mqtt_password: str = ""

    # --- Paths de archivos (visión desde dentro del contenedor) ---
    dynsec_path: str = "/var/lib/mosquitto/dynamic-security.json"
    mosquitto_conf_path: str = "/etc/mosquitto/mosquitto.conf"
    mosquitto_passwd_path: str = "/var/lib/mosquitto/mosquitto_passwd"
    mosquitto_certs_dir: str = "/etc/mosquitto/certs"
    mosquitto_conf_backup_dir: str = "/nextjs/data/backups"
    broker_log_path: str = "/var/log/mosquitto/mosquitto.log"
    broker_resource_stats_path: str = "/var/log/mosquitto/broker-resource-stats.json"
    broker_log_tail_enabled: bool = True
    broker_publish_monitor_enabled: bool = True
    broker_log_read_enabled: bool = True
    broker_resource_stats_file_enabled: bool = True
    broker_observability_enabled: bool = True
    broker_observability_url: str = "http://bhm-broker-observability:9102"
    broker_observability_timeout_seconds: float = 2.0
    broker_observability_log_poll_interval_seconds: float = 2.0
    broker_observability_log_snapshot_lines: int = 5000
    api_log_file: str = "/nextjs/data/api.log"
    broker_reconcile_mode: str = "inline"
    broker_reconcile_wait_timeout_seconds: float = 10.0
    broker_reconcile_poll_interval_seconds: float = 0.2
    broker_reconcile_secret_dir: str = "/nextjs/data/reconcile-secrets"
    broker_reconcile_secret_ttl_seconds: float = 120.0

    # --- Base de datos ---
    database_url: str = "postgresql://bunkerm:bunkerm@postgres:5432/bunkerm_db"
    control_plane_database_url: Optional[str] = None
    history_database_url: Optional[str] = None
    reporting_database_url: Optional[str] = None

    # --- Umbrales de alertas (monitor) ---
    alert_cpu_warning: float = 70.0
    alert_cpu_critical: float = 90.0
    alert_memory_warning: float = 70.0
    alert_memory_critical: float = 90.0
    alert_connections_warning: int = 80
    alert_connections_critical: int = 100
    alert_msg_rate_warning: float = 1000.0
    alert_msg_rate_critical: float = 5000.0

    # --- Smart-anomaly ---
    smart_anomaly_enabled: bool = True
    smart_anomaly_db_url: str = "sqlite+aiosqlite:////nextjs/data/smart_anomaly.db"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def resolved_control_plane_database_url(self) -> str:
        return self.control_plane_database_url or self.database_url

    @property
    def resolved_history_database_url(self) -> str:
        return self.history_database_url or self.database_url

    @property
    def resolved_reporting_database_url(self) -> str:
        return self.reporting_database_url or self.resolved_history_database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Instancia pública para importar directamente
settings: Settings = get_settings()
