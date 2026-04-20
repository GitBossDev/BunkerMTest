"""
Actuator Device - Dispositivos actuadores que reciben comandos y publican estado
"""

import time
import threading
from datetime import datetime, timezone
from typing import Dict, Any

from .base_device import BaseDevice


class ActuatorDevice(BaseDevice):
    """
    Dispositivo actuador controlable mediante comandos MQTT.
    Publica su estado periódicamente.
    """
    
    # Estados válidos
    STATE_OFF = "off"
    STATE_ON = "on"
    STATE_ERROR = "error"
    STATE_MANUAL = "manual"
    STATE_AUTO = "auto"
    
    def __init__(self, name: str, config: Dict[str, Any], mqtt_client, status_interval: int):
        """
        Inicializar actuador.
        
        Args:
            name: Nombre del actuador
            config: Configuración del actuador
            mqtt_client: Cliente MQTT
            status_interval: Intervalo de publicación de estado (segundos)
        """
        super().__init__(name, config)
        self.mqtt_client = mqtt_client
        self.status_interval = status_interval
        
        # Topics
        self.status_topic = config['status_topic']
        self.command_topic = config['command_topic']
        
        # Estado del actuador
        self.state = self.STATE_OFF
        self.mode = self.STATE_MANUAL  # manual o auto
        self.value = 0.0  # 0-100% para válvulas/bombas
        self.health = "ok"
        
        # Callback para comandos
        self.command_callback = None
        
    def start(self):
        """Iniciar actuador (suscribirse a comandos y publicar estado)."""
        if self.running:
            self.logger.warning(f"Actuador {self.name} ya está en ejecución")
            return
        
        self.running = True
        
        # Suscribirse a topic de comandos
        self.mqtt_client.subscribe(self.command_topic, self._handle_command)
        
        # Iniciar thread de publicación de estado
        self.thread = threading.Thread(target=self._status_loop, daemon=True)
        self.thread.start()
        
        self.logger.info(f"Actuador {self.name} iniciado (publicando estado cada {self.status_interval}s)")
    
    def stop(self):
        """Detener actuador."""
        self.running = False
        
        # Desuscribirse de comandos
        self.mqtt_client.unsubscribe(self.command_topic)
        
        if self.thread:
            self.thread.join(timeout=5)
        
        self.logger.info(f"Actuador {self.name} detenido")
    
    def _status_loop(self):
        """Loop de publicación de estado."""
        while self.running:
            try:
                self._publish_status()
                time.sleep(self.status_interval)
            except Exception as e:
                self.logger.error(f"[ERROR] Error en loop de estado: {e}")
                time.sleep(1)
    
    def _publish_status(self):
        """Publicar estado actual del actuador."""
        timestamp = datetime.now().astimezone().isoformat()
        
        payload = {
            "timestamp": timestamp,
            "device_id": f"actuator_{self.name}",
            "state": self.state,
            "mode": self.mode,
            "value": round(self.value, 1),
            "health": self.health
        }
        
        success = self.mqtt_client.publish(self.status_topic, payload)
        
        if success:
            self.logger.debug(f"{self.name}: state={self.state}, value={self.value}%")
    
    def _handle_command(self, topic: str, payload: Dict[str, Any]):
        """
        Procesar comando recibido.
        
        Args:
            topic: Topic del comando
            payload: Diccionario con el comando
        """
        try:
            command = payload.get('command', '').lower()
            value = payload.get('value', 0)
            mode = payload.get('mode', self.mode)
            
            self.logger.info(f"Comando recibido: {command} (value={value}, mode={mode})")
            
            # Procesar comando
            if command == 'on':
                self.set_state(self.STATE_ON, value)
            elif command == 'off':
                self.set_state(self.STATE_OFF, 0)
            elif command == 'set_value':
                self.set_value(value)
            elif command == 'set_mode':
                self.set_mode(mode)
            else:
                self.logger.warning(f"[WARNING] Comando desconocido: {command}")
                return
            
            # Publicar estado inmediatamente después del comando
            self._publish_status()
            
            # Callback externo (para integración con modelo físico)
            if self.command_callback:
                self.command_callback(self, command, payload)
                
        except Exception as e:
            self.logger.error(f"[ERROR] Error procesando comando: {e}")
    
    def set_state(self, state: str, value: float = None):
        """
        Establecer estado del actuador.
        
        Args:
            state: Nuevo estado (on/off/error)
            value: Valor opcional (0-100)
        """
        if state in [self.STATE_OFF, self.STATE_ON, self.STATE_ERROR]:
            self.state = state
            
            if value is not None:
                self.value = max(0, min(100, value))
            
            self.logger.info(f"{self.name} -> {self.state} ({self.value}%)")
    
    def set_value(self, value: float):
        """
        Establecer valor del actuador (0-100).
        
        Args:
            value: Porcentaje 0-100
        """
        self.value = max(0, min(100, value))
        
        if self.value > 0:
            self.state = self.STATE_ON
        else:
            self.state = self.STATE_OFF
    
    def set_mode(self, mode: str):
        """
        Establecer modo de operación.
        
        Args:
            mode: manual o auto
        """
        if mode in [self.STATE_MANUAL, self.STATE_AUTO]:
            self.mode = mode
            self.logger.info(f"{self.name} modo cambiado a: {self.mode}")
    
    def get_state(self) -> Dict[str, Any]:
        """Obtener estado actual del actuador."""
        return {
            "name": self.name,
            "status_topic": self.status_topic,
            "command_topic": self.command_topic,
            "state": self.state,
            "mode": self.mode,
            "value": self.value,
            "health": self.health,
            "running": self.running
        }
    
    def set_command_callback(self, callback):
        """
        Registrar callback para comandos (para modelo físico).
        
        Args:
            callback: Función callback(actuator, command, payload)
        """
        self.command_callback = callback
    
    def set_error(self, error_msg: str = ""):
        """Establecer estado de error."""
        self.state = self.STATE_ERROR
        self.health = f"error: {error_msg}" if error_msg else "error"
        self.logger.error(f"[ERROR] {self.name} en estado de error: {error_msg}")
    
    def clear_error(self):
        """Limpiar estado de error."""
        self.health = "ok"
        self.state = self.STATE_OFF
        self.value = 0
        self.logger.info(f"{self.name} error limpiado")
