"""
Configuración centralizada de la aplicación con pydantic-settings.
Todas las variables de entorno usadas por los microservicios anteriores
están definidas aquí como un único punto de verdad.
"""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


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
    api_log_file: str = "/nextjs/data/api.log"

    # --- Base de datos ---
    database_url: str = "sqlite+aiosqlite:////nextjs/data/bunkerm.db"

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Instancia pública para importar directamente
settings: Settings = get_settings()
