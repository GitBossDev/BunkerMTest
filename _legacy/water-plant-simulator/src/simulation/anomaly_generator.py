"""
Anomaly Generator - Generador de anomalías para testing
"""

import logging
import random
import threading
import time
from typing import Dict, Any, List


class AnomalyGenerator:
    """
    Generador de anomalías en sensores y actuadores.
    Simula fallos, spikes, derivas, y desconexiones.
    """
    
    ANOMALY_TYPES = ['freeze', 'spike', 'drift', 'disconnect']
    
    def __init__(self, config: Dict[str, Any], sensors: Dict, actuators: Dict):
        """
        Inicializar generador de anomalías.
        
        Args:
            config: Configuración de anomalías
            sensors: Diccionario de sensores {nombre: SensorDevice}
            actuators: Diccionario de actuadores {nombre: ActuatorDevice}
        """
        self.config = config
        self.sensors = sensors
        self.actuators = actuators
        self.logger = logging.getLogger(__name__)
        
        # Estado
        self.running = False
        self.enabled = config.get('enabled', False)
        self.thread = None
        
        # Parámetros
        self.check_interval = config.get('check_interval', 60)  # segundos
        self.probability = config.get('probability', 0.1)  # 10% por intervalo
        
        # Registro de anomalías activas
        self.active_anomalies = []
    
    def start(self):
        """Iniciar generador de anomalías."""
        if self.running:
            self.logger.warning("Generador de anomalías ya está en ejecución")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._anomaly_loop, daemon=True)
        self.thread.start()
        
        status = "HABILITADO" if self.enabled else "DESHABILITADO"
        self.logger.info(f"Generador de anomalías iniciado ({status}, intervalo={self.check_interval}s)")
    
    def stop(self):
        """Detener generador de anomalías."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self.logger.info("Generador de anomalías detenido")
    
    def _anomaly_loop(self):
        """Loop principal de generación de anomalías."""
        while self.running:
            try:
                if self.enabled:
                    # Decidir si generar anomalía
                    if random.random() < self.probability:
                        self._generate_random_anomaly()
                
                # Limpiar anomalías expiradas
                self._clean_expired_anomalies()
                
                time.sleep(self.check_interval)
            except Exception as e:
                self.logger.error(f"[ERROR] Error en loop de anomalías: {e}")
                time.sleep(1)
    
    def _generate_random_anomaly(self):
        """Generar una anomalía aleatoria."""
        if not self.sensors:
            return
        
        # Seleccionar sensor aleatorio
        sensor_name = random.choice(list(self.sensors.keys()))
        sensor = self.sensors[sensor_name]
        
        # Seleccionar tipo de anomalía
        anomaly_type = random.choice(self.ANOMALY_TYPES)
        
        # Generar anomalía
        if anomaly_type == 'freeze':
            self._generate_freeze(sensor)
        elif anomaly_type == 'spike':
            self._generate_spike(sensor)
        elif anomaly_type == 'drift':
            self._generate_drift(sensor)
        elif anomaly_type == 'disconnect':
            self._generate_disconnect(sensor)
    
    def _generate_freeze(self, sensor):
        """
        Generar anomalía de congelación.
        El sensor se queda en un valor fijo.
        
        Args:
            sensor: SensorDevice a afectar
        """
        duration = random.randint(30, 180)  # 30-180 segundos
        sensor.freeze(duration)
        
        anomaly = {
            'type': 'freeze',
            'sensor': sensor.name,
            'start_time': time.time(),
            'duration': duration
        }
        self.active_anomalies.append(anomaly)
        
        self.logger.warning(f"[ANOMALY] Freeze generado en {sensor.name} por {duration}s")
    
    def _generate_spike(self, sensor):
        """
        Generar anomalía de spike.
        El sensor muestra un valor anormalmente alto/bajo.
        
        Args:
            sensor: SensorDevice a afectar
        """
        multiplier = random.choice([0.1, 0.2, 3.0, 5.0])  # Bajo o alto
        sensor.spike(multiplier)
        
        anomaly = {
            'type': 'spike',
            'sensor': sensor.name,
            'start_time': time.time(),
            'duration': 0,  # Instantáneo
            'multiplier': multiplier
        }
        self.active_anomalies.append(anomaly)
        
        self.logger.warning(f"[ANOMALY] Spike generado en {sensor.name} (x{multiplier})")
    
    def _generate_drift(self, sensor):
        """
        Generar anomalía de deriva.
        El sensor deriva gradualmente fuera del rango.
        
        Args:
            sensor: SensorDevice a afectar
        """
        duration = random.randint(60, 300)  # 60-300 segundos
        
        # Calcular tasa de deriva
        sensor_range = sensor.max_value - sensor.min_value
        drift_rate = random.choice([-1, 1]) * (sensor_range / duration) * 0.5  # 50% del rango en la duración
        
        sensor.set_drift(drift_rate)
        
        # Programar limpieza
        threading.Timer(duration, lambda: sensor.set_drift(0)).start()
        
        anomaly = {
            'type': 'drift',
            'sensor': sensor.name,
            'start_time': time.time(),
            'duration': duration,
            'drift_rate': drift_rate
        }
        self.active_anomalies.append(anomaly)
        
        self.logger.warning(f"[ANOMALY] Drift generado en {sensor.name} ({drift_rate:.2f} {sensor.unit}/s por {duration}s)")
    
    def _generate_disconnect(self, sensor):
        """
        Generar anomalía de desconexión.
        El sensor deja de publicar temporalmente.
        
        Args:
            sensor: SensorDevice a afectar
        """
        duration = random.randint(20, 120)  # 20-120 segundos
        
        # Detener sensor
        sensor.stop()
        
        # Programar reinicio
        threading.Timer(duration, sensor.start).start()
        
        anomaly = {
            'type': 'disconnect',
            'sensor': sensor.name,
            'start_time': time.time(),
            'duration': duration
        }
        self.active_anomalies.append(anomaly)
        
        self.logger.warning(f"[ANOMALY] Disconnect generado en {sensor.name} por {duration}s")
    
    def _clean_expired_anomalies(self):
        """Limpiar anomalías expiradas del registro."""
        current_time = time.time()
        
        self.active_anomalies = [
            a for a in self.active_anomalies
            if (current_time - a['start_time']) < (a['duration'] + 10)  # +10s margen
        ]
    
    def enable(self):
        """Habilitar generación de anomalías."""
        self.enabled = True
        self.logger.info("Generación de anomalías HABILITADA")
    
    def disable(self):
        """Deshabilitar generación de anomalías."""
        self.enabled = False
        self.logger.info("Generación de anomalías DESHABILITADA")
    
    def trigger_specific_anomaly(self, sensor_name: str, anomaly_type: str, **kwargs):
        """
        Generar una anomalía específica.
        
        Args:
            sensor_name: Nombre del sensor a afectar
            anomaly_type: Tipo de anomalía (freeze, spike, drift, disconnect)
            **kwargs: Parámetros adicionales (duration, multiplier, drift_rate, etc.)
        """
        if sensor_name not in self.sensors:
            self.logger.error(f"[ERROR] Sensor {sensor_name} no encontrado")
            return
        
        sensor = self.sensors[sensor_name]
        
        if anomaly_type == 'freeze':
            duration = kwargs.get('duration', 60)
            sensor.freeze(duration)
            self.logger.info(f"Anomalía manual: Freeze en {sensor_name} por {duration}s")
        
        elif anomaly_type == 'spike':
            multiplier = kwargs.get('multiplier', 3.0)
            sensor.spike(multiplier)
            self.logger.info(f"Anomalía manual: Spike en {sensor_name} (x{multiplier})")
        
        elif anomaly_type == 'drift':
            drift_rate = kwargs.get('drift_rate')
            duration = kwargs.get('duration', 120)
            
            if drift_rate is None:
                sensor_range = sensor.max_value - sensor.min_value
                drift_rate = (sensor_range / duration) * 0.3
            
            sensor.set_drift(drift_rate)
            threading.Timer(duration, lambda: sensor.set_drift(0)).start()
            self.logger.info(f"Anomalía manual: Drift en {sensor_name} ({drift_rate:.2f}/s por {duration}s)")
        
        elif anomaly_type == 'disconnect':
            duration = kwargs.get('duration', 60)
            sensor.stop()
            threading.Timer(duration, sensor.start).start()
            self.logger.info(f"Anomalía manual: Disconnect en {sensor_name} por {duration}s")
        
        else:
            self.logger.error(f"[ERROR] Tipo de anomalía desconocido: {anomaly_type}")
    
    def get_active_anomalies(self) -> List[Dict[str, Any]]:
        """Obtener lista de anomalías activas."""
        return self.active_anomalies.copy()
    
    def get_state(self) -> Dict[str, Any]:
        """Obtener estado del generador."""
        return {
            "running": self.running,
            "enabled": self.enabled,
            "check_interval": self.check_interval,
            "probability": self.probability,
            "active_anomalies_count": len(self.active_anomalies)
        }
