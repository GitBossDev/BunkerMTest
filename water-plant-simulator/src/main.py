#!/usr/bin/env python3
"""
Water Plant Simulator - Main Entry Point
Simulador completo de planta de tratamiento de aguas para testing con BunkerM.
"""

import sys
import signal
import time
import logging
import yaml
import os
from pathlib import Path
from typing import Dict, Any

# Importar componentes del simulador
from .mqtt_client import MQTTClientManager
from .devices.sensor import SensorDevice
from .devices.actuator import ActuatorDevice
from .devices.controller import PlantController
from .simulation.physics_model import PhysicsModel
from .simulation.anomaly_generator import AnomalyGenerator


class WaterPlantSimulator:
    """
    Simulador principal de la planta de tratamiento de aguas.
    Coordina sensores, actuadores, controlador y modelo físico.
    """
    
    def __init__(self, config_path: str = "config/plant_config.yaml"):
        """
        Inicializar simulador con configuración.
        
        Args:
            config_path: Ruta al archivo de configuración YAML
        """
        self.config = self._load_config(config_path)
        self.setup_logging()
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("Iniciando Water Plant Simulator...")
        
        # Componentes principales
        self.mqtt_client = None
        self.sensors = {}
        self.actuators = {}
        self.controller = None
        self.physics_model = None
        self.anomaly_generator = None
        
        # Control de ejecución
        self.running = False
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Cargar configuración desde archivo YAML."""
        config_file = Path(__file__).parent.parent / config_path
        
        if not config_file.exists():
            raise FileNotFoundError(f"Archivo de configuración no encontrado: {config_file}")
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # Sobrescribir configuración MQTT con variables de entorno si existen
        mqtt_broker = os.getenv('MQTT_BROKER')
        mqtt_port = os.getenv('MQTT_PORT')
        mqtt_username = os.getenv('MQTT_USERNAME')
        mqtt_password = os.getenv('MQTT_PASSWORD')
        
        if mqtt_broker:
            config['mqtt']['broker'] = mqtt_broker
        if mqtt_port:
            config['mqtt']['port'] = int(mqtt_port)
        if mqtt_username:
            config['mqtt']['username'] = mqtt_username
        if mqtt_password:
            config['mqtt']['password'] = mqtt_password
        
        return config
    
    def setup_logging(self):
        """Configurar sistema de logging."""
        log_config = self.config.get('logging', {})
        log_level = getattr(logging, log_config.get('level', 'INFO'))
        log_format = log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        logging.basicConfig(
            level=log_level,
            format=log_format,
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler('simulator.log')
            ]
        )
    
    def initialize(self):
        """Inicializar todos los componentes del simulador."""
        self.logger.info("Inicializando componentes...")
        
        # 1. Cliente MQTT
        mqtt_config = self.config['mqtt']
        self.mqtt_client = MQTTClientManager(mqtt_config)
        self.mqtt_client.connect()
        
        # 2. Crear sensores
        sensors_config = self.config['sensors']
        for sensor_name, sensor_cfg in sensors_config.items():
            if sensor_name == 'publish_interval':
                continue
                
            sensor = SensorDevice(
                name=sensor_name,
                config=sensor_cfg,
                mqtt_client=self.mqtt_client,
                publish_interval=sensors_config['publish_interval']
            )
            self.sensors[sensor_name] = sensor
            self.logger.info(f"Sensor creado: {sensor_name}")
        
        # 3. Crear actuadores
        actuators_config = self.config['actuators']
        for actuator_name, actuator_cfg in actuators_config.items():
            if actuator_name == 'status_publish_interval':
                continue
                
            actuator = ActuatorDevice(
                name=actuator_name,
                config=actuator_cfg,
                mqtt_client=self.mqtt_client,
                status_interval=actuators_config['status_publish_interval']
            )
            self.actuators[actuator_name] = actuator
            self.logger.info(f"Actuador creado: {actuator_name}")
        
        # 4. Modelo físico (opcional)
        if self.config['physics']['enabled']:
            self.physics_model = PhysicsModel(
                config=self.config['physics'],
                sensors=self.sensors,
                actuators=self.actuators
            )
            self.logger.info("Modelo físico habilitado")
        
        # 5. Controlador automático (opcional)
        if self.config['controller']['enabled']:
            self.controller = PlantController(
                config=self.config['controller'],
                sensors=self.sensors,
                actuators=self.actuators
            )
            self.logger.info("Controlador automático habilitado")
        
        # 6. Generador de anomalías (opcional)
        if self.config['anomalies']['enabled']:
            self.anomaly_generator = AnomalyGenerator(
                config=self.config['anomalies'],
                sensors=self.sensors
            )
            self.logger.info("Generador de anomalías habilitado")
        
        self.logger.info("Inicialización completada")
    
    def start(self):
        """Iniciar la simulación."""
        self.logger.info("===========================================")
        self.logger.info("   Water Plant Simulator - INICIADO")
        self.logger.info("===========================================")
        self.logger.info(f"Sensores activos: {len(self.sensors)}")
        self.logger.info(f"Actuadores activos: {len(self.actuators)}")
        
        self.running = True
        
        # Iniciar sensores
        for sensor in self.sensors.values():
            sensor.start()
        
        # Iniciar actuadores
        for actuator in self.actuators.values():
            actuator.start()
        
        # Iniciar controlador
        if self.controller:
            self.controller.start()
        
        # Iniciar modelo físico
        if self.physics_model:
            self.physics_model.start()
        
        # Iniciar generador de anomalías
        if self.anomaly_generator:
            self.anomaly_generator.start()
        
        self.logger.info("Todos los componentes iniciados. Simulador en ejecución...")
        
        # Loop principal
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Interrupción detectada (Ctrl+C)")
        finally:
            self.stop()
    
    def stop(self):
        """Detener la simulación de manera ordenada."""
        self.logger.info("Deteniendo simulador...")
        
        self.running = False
        
        # Detener componentes en orden inverso
        if self.anomaly_generator:
            self.anomaly_generator.stop()
        
        if self.physics_model:
            self.physics_model.stop()
        
        if self.controller:
            self.controller.stop()
        
        for actuator in self.actuators.values():
            actuator.stop()
        
        for sensor in self.sensors.values():
            sensor.stop()
        
        if self.mqtt_client:
            self.mqtt_client.disconnect()
        
        self.logger.info("Simulador detenido correctamente")
    
    def signal_handler(self, signum, frame):
        """Manejar señales del sistema operativo."""
        self.logger.info(f"Señal recibida: {signum}")
        self.stop()
        sys.exit(0)


def main():
    """Función principal."""
    print("===========================================")
    print("  Water Plant Simulator - BunkerM Extended")
    print("===========================================")
    print()
    
    # Crear simulador
    simulator = WaterPlantSimulator()
    
    # Registrar manejador de señales
    signal.signal(signal.SIGINT, simulator.signal_handler)
    signal.signal(signal.SIGTERM, simulator.signal_handler)
    
    try:
        # Inicializar y ejecutar
        simulator.initialize()
        simulator.start()
    except Exception as e:
        logging.error(f"Error fatal en el simulador: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
