"""
Plant Controller - Control automático de la planta de tratamiento
"""

import logging
import threading
import time
from typing import Dict, Any, List


class PlantController:
    """
    Controlador automático de la planta.
    Monitorea sensores y controla actuadores según reglas definidas.
    """
    
    def __init__(self, config: Dict[str, Any], sensors: Dict, actuators: Dict):
        """
        Inicializar controlador.
        
        Args:
            config: Configuración de reglas de control
            sensors: Diccionario de sensores {nombre: SensorDevice}
            actuators: Diccionario de actuadores {nombre: ActuatorDevice}
        """
        self.config = config
        self.sensors = sensors
        self.actuators = actuators
        self.logger = logging.getLogger(__name__)
        
        # Estado
        self.running = False
        self.enabled = config.get('auto_control_enabled', True)
        self.thread = None
        
        # Control interval
        self.control_interval = config.get('control_interval', 10)
        
        # Reglas de control
        self.rules = config.get('rules', {})
        
    def start(self):
        """Iniciar controlador automático."""
        if self.running:
            self.logger.warning("Controlador ya está en ejecución")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._control_loop, daemon=True)
        self.thread.start()
        
        status = "HABILITADO" if self.enabled else "DESHABILITADO"
        self.logger.info(f"Controlador automático iniciado ({status}, intervalo={self.control_interval}s)")
    
    def stop(self):
        """Detener controlador."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self.logger.info("Controlador automático detenido")
    
    def _control_loop(self):
        """Loop principal de control."""
        while self.running:
            try:
                if self.enabled:
                    self._execute_control_logic()
                
                time.sleep(self.control_interval)
            except Exception as e:
                self.logger.error(f"[ERROR] Error en loop de control: {e}")
                time.sleep(1)
    
    def _execute_control_logic(self):
        """Ejecutar lógica de control basada en reglas."""
        # Control de nivel de tanque
        self._control_tank_level()
        
        # Control de pH
        self._control_ph()
        
        # Control de turbidez
        self._control_turbidity()
        
        # Protección de bombas
        self._protect_pumps()
    
    def _control_tank_level(self):
        """Controlar nivel del tanque 1."""
        if 'tank1_level' not in self.sensors:
            return
        
        level = self.sensors['tank1_level'].current_value
        rules = self.rules.get('tank_level', {})
        
        min_level = rules.get('min', 20)
        max_level = rules.get('max', 90)
        
        # Si nivel bajo, activar bomba de entrada (pump1)
        if level < min_level:
            if 'pump1' in self.actuators:
                actuator = self.actuators['pump1']
                if actuator.mode == 'auto' and actuator.state != 'on':
                    actuator.set_state('on', 80)  # 80% velocidad
                    self.logger.info(f"[CONTROL] Nivel bajo ({level}%) -> Pump1 ON")
        
        # Si nivel alto, desactivar bomba de entrada
        elif level > max_level:
            if 'pump1' in self.actuators:
                actuator = self.actuators['pump1']
                if actuator.mode == 'auto' and actuator.state != 'off':
                    actuator.set_state('off', 0)
                    self.logger.info(f"[CONTROL] Nivel alto ({level}%) -> Pump1 OFF")
    
    def _control_ph(self):
        """Controlar pH del tanque 1."""
        if 'tank1_ph' not in self.sensors:
            return
        
        ph = self.sensors['tank1_ph'].current_value
        rules = self.rules.get('ph', {})
        
        min_ph = rules.get('min', 6.5)
        max_ph = rules.get('max', 8.0)
        
        # Abrir válvula de dosificación si pH fuera de rango
        if ph < min_ph or ph > max_ph:
            if 'valve1' in self.actuators:
                actuator = self.actuators['valve1']
                if actuator.mode == 'auto':
                    # Ajustar apertura según desviación
                    deviation = abs(ph - 7.0)
                    opening = min(100, deviation * 20)  # 20% por unidad de pH
                    
                    if actuator.value != opening:
                        actuator.set_value(opening)
                        self.logger.info(f"[CONTROL] pH={ph:.2f} fuera de rango -> Valve1={opening:.0f}%")
        else:
            # pH correcto, cerrar válvula
            if 'valve1' in self.actuators:
                actuator = self.actuators['valve1']
                if actuator.mode == 'auto' and actuator.value > 0:
                    actuator.set_value(0)
                    self.logger.info(f"[CONTROL] pH={ph:.2f} OK -> Valve1=0%")
    
    def _control_turbidity(self):
        """Controlar turbidez del tanque 1."""
        if 'tank1_turbidity' not in self.sensors:
            return
        
        turbidity = self.sensors['tank1_turbidity'].current_value
        rules = self.rules.get('turbidity', {})
        
        max_turbidity = rules.get('max', 5)
        
        # Activar bomba 2 (salida) si turbidez alta
        if turbidity > max_turbidity:
            if 'pump2' in self.actuators:
                actuator = self.actuators['pump2']
                if actuator.mode == 'auto' and actuator.state != 'on':
                    actuator.set_state('on', 60)  # 60% velocidad
                    self.logger.info(f"[CONTROL] Turbidez alta ({turbidity:.1f} NTU) -> Pump2 ON")
        else:
            # Turbidez OK, detener bomba 2
            if 'pump2' in self.actuators:
                actuator = self.actuators['pump2']
                if actuator.mode == 'auto' and actuator.state == 'on':
                    actuator.set_state('off', 0)
                    self.logger.info(f"[CONTROL] Turbidez OK ({turbidity:.1f} NTU) -> Pump2 OFF")
    
    def _protect_pumps(self):
        """Protecciones de seguridad para bombas."""
        # Protección presión alta pump1
        if 'pump1_pressure' in self.sensors and 'pump1' in self.actuators:
            pressure = self.sensors['pump1_pressure'].current_value
            
            if pressure > 8.0:  # > 8 bar = peligro
                actuator = self.actuators['pump1']
                if actuator.state == 'on':
                    actuator.set_state('off', 0)
                    actuator.set_error("Presión excesiva")
                    self.logger.error(f"[PROTECCION] Pump1 detenida por presión alta ({pressure:.1f} bar)")
        
        # Protección presión alta pump2
        if 'pump2_pressure' in self.sensors and 'pump2' in self.actuators:
            pressure = self.sensors['pump2_pressure'].current_value
            
            if pressure > 7.0:  # > 7 bar = peligro
                actuator = self.actuators['pump2']
                if actuator.state == 'on':
                    actuator.set_state('off', 0)
                    actuator.set_error("Presión excesiva")
                    self.logger.error(f"[PROTECCION] Pump2 detenida por presión alta ({pressure:.1f} bar)")
    
    def enable(self):
        """Habilitar control automático."""
        self.enabled = True
        self.logger.info("Control automático HABILITADO")
    
    def disable(self):
        """Deshabilitar control automático."""
        self.enabled = False
        self.logger.info("Control automático DESHABILITADO")
    
    def get_state(self) -> Dict[str, Any]:
        """Obtener estado del controlador."""
        return {
            "running": self.running,
            "enabled": self.enabled,
            "control_interval": self.control_interval,
            "rules": self.rules
        }
