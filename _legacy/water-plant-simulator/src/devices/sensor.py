"""
Sensor Device - Dispositivos sensores que publican datos periódicamente
"""

import time
import threading
import random
from datetime import datetime, timezone
from typing import Dict, Any

from .base_device import BaseDevice


class SensorDevice(BaseDevice):
    """
    Dispositivo sensor que publica mediciones periódicamente.
    Simula valores realistas con ruido y deriva.
    """
    
    def __init__(self, name: str, config: Dict[str, Any], mqtt_client, publish_interval: int):
        """
        Inicializar sensor.
        
        Args:
            name: Nombre del sensor
            config: Configuración del sensor
            mqtt_client: Cliente MQTT para publicar
            publish_interval: Intervalo de publicación en segundos
        """
        super().__init__(name, config)
        self.mqtt_client = mqtt_client
        self.publish_interval = publish_interval
        
        # Parámetros del sensor
        self.topic = config['topic']
        self.unit = config['unit']
        self.min_value = config['min_value']
        self.max_value = config['max_value']
        self.noise_stddev = config.get('noise_stddev', 0.1)
        self.format = config.get('format', 'json')  # 'json', 'csv', 'plain'
        
        # Estado actual
        self.current_value = config.get('initial_value', (self.min_value + self.max_value) / 2)
        self.quality = "good"
        
        # Control de anomalías (manejado externamente)
        self.frozen = False
        self.frozen_value = None
        self.drift_rate = 0.0  # unidades por segundo
        
    def start(self):
        """Iniciar publicación periódica del sensor."""
        if self.running:
            self.logger.warning(f"Sensor {self.name} ya está en ejecución")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._publish_loop, daemon=True)
        self.thread.start()
        self.logger.info(f"Sensor {self.name} iniciado (publicando cada {self.publish_interval}s)")
    
    def stop(self):
        """Detener publicación del sensor."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self.logger.info(f"Sensor {self.name} detenido")
    
    def _publish_loop(self):
        """Loop principal de publicación."""
        while self.running:
            try:
                # Actualizar valor
                self._update_value()
                
                # Publicar medición
                self._publish_measurement()
                
                # Esperar siguiente ciclo
                time.sleep(self.publish_interval)
            except Exception as e:
                self.logger.error(f"[ERROR] Error en loop de publicación: {e}")
                time.sleep(1)
    
    def _update_value(self):
        """Actualizar el valor del sensor con ruido y deriva."""
        if self.frozen:
            # Sensor congelado (anomalía)
            self.current_value = self.frozen_value
            return
        
        # Aplicar deriva si existe
        if self.drift_rate != 0:
            self.current_value += self.drift_rate * self.publish_interval
        
        # Añadir ruido gaussiano
        noise = random.gauss(0, self.noise_stddev)
        self.current_value += noise
        
        # Limitar al rango válido
        self.current_value = max(self.min_value, min(self.max_value, self.current_value))
    
    def _publish_measurement(self):
        """Publicar medición en el topic MQTT."""
        local_now = datetime.now().astimezone()
        timestamp = local_now.strftime('%Y-%m-%dT%H:%M:%S%z')
        value = round(self.current_value, 2)

        if self.format == 'csv':
            # CSV: "<ISO8601>,<device_id>,<value>,<unit>"
            raw_payload = f"{timestamp},sensor_{self.name},{value},{self.unit}"
            success = self.mqtt_client.publish_raw(self.topic, raw_payload)
        elif self.format == 'plain':
            # Plain numeric string: "<value>"
            raw_payload = str(value)
            success = self.mqtt_client.publish_raw(self.topic, raw_payload)
        else:
            # Default JSON format
            payload = {
                "timestamp": local_now.isoformat(),
                "device_id": f"sensor_{self.name}",
                "value": value,
                "unit": self.unit,
                "quality": self.quality
            }
            success = self.mqtt_client.publish(self.topic, payload)

        if success:
            self.logger.debug(f"{self.name}: {value} {self.unit}")
    
    def get_state(self) -> Dict[str, Any]:
        """Obtener estado actual del sensor."""
        return {
            "name": self.name,
            "topic": self.topic,
            "value": self.current_value,
            "unit": self.unit,
            "quality": self.quality,
            "running": self.running,
            "frozen": self.frozen,
            "drift_rate": self.drift_rate
        }
    
    def set_value(self, value: float):
        """Establecer valor manual (para testing o modelo físico)."""
        self.current_value = max(self.min_value, min(self.max_value, value))
    
    def freeze(self, duration: int = None):
        """
        Congelar sensor (anomalía).
        
        Args:
            duration: Duración en segundos (None = indefinido)
        """
        self.frozen = True
        self.frozen_value = self.current_value
        self.quality = "frozen"
        self.logger.warning(f"[ANOMALY] Sensor {self.name} congelado en valor {self.frozen_value}")
        
        if duration:
            threading.Timer(duration, self.unfreeze).start()
    
    def unfreeze(self):
        """Descongelar sensor."""
        self.frozen = False
        self.frozen_value = None
        self.quality = "good"
        self.logger.info(f"Sensor {self.name} descongelado")
    
    def set_drift(self, rate: float):
        """
        Establecer deriva del sensor (anomalía).
        
        Args:
            rate: Tasa de deriva en unidades por segundo
        """
        self.drift_rate = rate
        if rate != 0:
            self.logger.warning(f"[ANOMALY] Sensor {self.name} con deriva de {rate} {self.unit}/s")
    
    def spike(self, multiplier: float):
        """
        Generar spike puntual (anomalía).
        
        Args:
            multiplier: Multiplicador del valor actual
        """
        original_value = self.current_value
        self.current_value *= multiplier
        self.logger.warning(f"[ANOMALY] Sensor {self.name} spike: {original_value} -> {self.current_value}")
