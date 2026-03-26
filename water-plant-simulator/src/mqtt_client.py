"""
MQTT Client Manager - Gestión de conexión MQTT para el simulador
"""

import logging
import paho.mqtt.client as mqtt
import json
from typing import Dict, Any, Callable, Optional


class MQTTClientManager:
    """
    Gestor de cliente MQTT con reconexión automática.
    Proporciona métodos simplificados para publicar y suscribirse.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Inicializar cliente MQTT.
        
        Args:
            config: Diccionario con configuración MQTT
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Crear cliente MQTT
        client_id = f"{config['client_id_prefix']}_{id(self)}"
        self.client = mqtt.Client(client_id=client_id)
        
        # Configurar callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        
        # Autenticación
        if config.get('username') and config.get('password'):
            self.client.username_pw_set(config['username'], config['password'])        
        # Estado
        self.connected = False
        self.subscriptions = {}  # topic -> callback
        
    def _on_connect(self, client, userdata, flags, rc):
        """Callback cuando se conecta al broker."""
        if rc == 0:
            self.logger.info(f"[OK] Conectado al broker MQTT: {self.config['broker']}:{self.config['port']}")
            self.connected = True
            
            # Resuscribirse a topics si hay
            for topic in self.subscriptions.keys():
                self.client.subscribe(topic, qos=self.config.get('qos', 1))
                self.logger.info(f"Resuscrito a topic: {topic}")
        else:
            self.logger.error(f"[ERROR] Falló conexión MQTT. Código: {rc}")
            self.connected = False
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback cuando se desconecta del broker."""
        self.connected = False
        if rc != 0:
            self.logger.warning(f"[WARNING] Desconexión inesperada del broker MQTT. Código: {rc}")
        else:
            self.logger.info("Desconectado del broker MQTT")
    
    def _on_message(self, client, userdata, msg):
        """Callback cuando se recibe un mensaje."""
        topic = msg.topic
        
        if topic in self.subscriptions:
            try:
                payload = json.loads(msg.payload.decode())
                callback = self.subscriptions[topic]
                callback(topic, payload)
            except json.JSONDecodeError:
                self.logger.error(f"[ERROR] Payload JSON inválido en topic {topic}")
            except Exception as e:
                self.logger.error(f"[ERROR] Error procesando mensaje de {topic}: {e}")
    
    def connect(self):
        """Conectar al broker MQTT."""
        try:
            self.logger.info(f"Conectando a broker MQTT: {self.config['broker']}:{self.config['port']}...")
            self.client.connect(
                self.config['broker'],
                self.config['port'],
                self.config.get('keepalive', 60)
            )
            self.client.loop_start()
        except Exception as e:
            self.logger.error(f"[ERROR] No se pudo conectar al broker MQTT: {e}")
            raise
    
    def disconnect(self):
        """Desconectar del broker MQTT."""
        try:
            self.client.loop_stop()
            self.client.disconnect()
            self.logger.info("Cliente MQTT desconectado")
        except Exception as e:
            self.logger.error(f"[ERROR] Error al desconectar: {e}")
    
    def publish(self, topic: str, payload: Dict[str, Any], qos: Optional[int] = None) -> bool:
        """
        Publicar mensaje en un topic.
        
        Args:
            topic: Topic MQTT
            payload: Diccionario con datos (se convierte a JSON)
            qos: Quality of Service (0, 1, 2). Si es None, usa config.
            
        Returns:
            True si se publicó correctamente, False en caso contrario
        """
        if not self.connected:
            self.logger.warning(f"[WARNING] No conectado. No se pudo publicar en {topic}")
            return False
        
        try:
            qos_level = qos if qos is not None else self.config.get('qos', 1)
            payload_json = json.dumps(payload)
            
            result = self.client.publish(topic, payload_json, qos=qos_level)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                return True
            else:
                self.logger.error(f"[ERROR] Fallo al publicar en {topic}. Código: {result.rc}")
                return False
        except Exception as e:
            self.logger.error(f"[ERROR] Excepción al publicar en {topic}: {e}")
            return False

    def publish_raw(self, topic: str, payload: str, qos: Optional[int] = None) -> bool:
        """
        Publicar un string literal (no JSON) en un topic.

        Args:
            topic: Topic MQTT
            payload: String a publicar directamente (CSV, plain value, etc.)
            qos: Quality of Service (0, 1, 2). Si es None, usa config.

        Returns:
            True si se publicó correctamente, False en caso contrario
        """
        if not self.connected:
            self.logger.warning(f"[WARNING] No conectado. No se pudo publicar en {topic}")
            return False

        try:
            qos_level = qos if qos is not None else self.config.get('qos', 1)
            result = self.client.publish(topic, payload, qos=qos_level)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                return True
            else:
                self.logger.error(f"[ERROR] Fallo al publicar en {topic}. Código: {result.rc}")
                return False
        except Exception as e:
            self.logger.error(f"[ERROR] Excepción al publicar en {topic}: {e}")
            return False
    
    def subscribe(self, topic: str, callback: Callable[[str, Dict], None], qos: Optional[int] = None):
        """
        Suscribirse a un topic.
        
        Args:
            topic: Topic MQTT
            callback: Función callback(topic, payload_dict)
            qos: Quality of Service (0, 1, 2). Si es None, usa config.
        """
        qos_level = qos if qos is not None else self.config.get('qos', 1)
        
        self.subscriptions[topic] = callback
        
        if self.connected:
            self.client.subscribe(topic, qos=qos_level)
            self.logger.info(f"Suscrito a topic: {topic}")
        else:
            self.logger.info(f"Suscripción registrada (pendiente de conexión): {topic}")
    
    def unsubscribe(self, topic: str):
        """Desuscribirse de un topic."""
        if topic in self.subscriptions:
            del self.subscriptions[topic]
            
            if self.connected:
                self.client.unsubscribe(topic)
                self.logger.info(f"Desuscrito de topic: {topic}")
