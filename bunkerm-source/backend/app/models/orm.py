"""
Modelos ORM SQLAlchemy para el backend unificado.
Reemplazan el almacenamiento JSON de data_storage.py (datos históricos)
y alert_config.json (configuración de alertas).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class HistoricalTick(Base):
    """
    Tick de 60 segundos para métricas de bytes y mensajes del broker.
    Reemplaza la estructura JSON en data/historical_data.txt.
    """
    __tablename__ = "historical_ticks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Timestamp UTC del tick
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    # Bytes acumulados desde el inicio del broker (valores absolutos del $SYS)
    bytes_received: Mapped[int] = mapped_column(Integer, default=0)
    bytes_sent: Mapped[int] = mapped_column(Integer, default=0)
    # Delta de mensajes en este intervalo de 60 s
    messages_received_delta: Mapped[int] = mapped_column(Integer, default=0)
    messages_sent_delta: Mapped[int] = mapped_column(Integer, default=0)


class AlertConfigEntry(Base):
    """
    Par clave-valor para almacenar la configuración de alertas del monitor.
    Reemplaza alert_config.json en /nextjs/data/.
    """
    __tablename__ = "alert_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)


class BrokerBaseline(Base):
    """
    Guarda los valores absolutos acumulados del broker en el arranque
    para poder calcular deltas en el primer tick.
    Solo hay una fila con id=1.
    """
    __tablename__ = "broker_baseline"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    msg_received_base: Mapped[int] = mapped_column(Integer, default=0)
    msg_sent_base: Mapped[int] = mapped_column(Integer, default=0)
    bytes_received_base: Mapped[int] = mapped_column(Integer, default=0)
    bytes_sent_base: Mapped[int] = mapped_column(Integer, default=0)
    load_1min: Mapped[float] = mapped_column(Float, default=0.0)
    load_5min: Mapped[float] = mapped_column(Float, default=0.0)
    load_15min: Mapped[float] = mapped_column(Float, default=0.0)
