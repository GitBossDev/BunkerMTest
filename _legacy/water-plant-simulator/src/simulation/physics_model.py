"""
Physics Model - Modelo físico de la planta de tratamiento de agua
"""

import logging
import threading
import time
from typing import Dict, Any


class PhysicsModel:
    """
    Modelo físico que simula la dinámica de la planta.
    Calcula niveles de tanques, flujos, presiones, etc.
    """
    
    def __init__(self, config: Dict[str, Any], sensors: Dict, actuators: Dict):
        """
        Inicializar modelo físico.
        
        Args:
            config: Configuración del modelo físico
            sensors: Diccionario de sensores {nombre: SensorDevice}
            actuators: Diccionario de actuadores {nombre: ActuatorDevice}
        """
        self.config = config
        self.sensors = sensors
        self.actuators = actuators
        self.logger = logging.getLogger(__name__)
        
        # Estado
        self.running = False
        self.thread = None
        
        # Parámetros del modelo
        self.update_dt = config.get('update_dt', 1.0)  # segundos
        
        # Capacidades y constantes
        self.tank_capacity = config.get('tank_capacity', 10000)  # litros
        self.pump_flow_rate = config.get('pump_flow_rate', 100)  # L/min al 100%
        self.valve_flow_rate = config.get('valve_flow_rate', 50)  # L/min al 100%
        self.evaporation_rate = config.get('evaporation_rate', 0.1)  # L/min
        
        # Estado físico
        self.tank1_volume = self.tank_capacity * 0.5  # Iniciar a 50%
        
        # Registrar callbacks en actuadores para responder a comandos
        self._register_actuator_callbacks()
    
    def _register_actuator_callbacks(self):
        """Registrar callbacks para actualizaciones de actuadores."""
        for name, actuator in self.actuators.items():
            actuator.set_command_callback(self._on_actuator_command)
    
    def _on_actuator_command(self, actuator, command: str, payload: Dict[str, Any]):
        """
        Callback cuando un actuador recibe un comando.
        
        Args:
            actuator: Actuador que recibió el comando
            command: Comando ejecutado
            payload: Payload del comando
        """
        self.logger.debug(f"Modelo físico notificado: {actuator.name} ejecutó {command}")
    
    def start(self):
        """Iniciar simulación física."""
        if self.running:
            self.logger.warning("Modelo físico ya está en ejecución")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._physics_loop, daemon=True)
        self.thread.start()
        
        self.logger.info(f"Modelo físico iniciado (dt={self.update_dt}s)")
    
    def stop(self):
        """Detener simulación física."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self.logger.info("Modelo físico detenido")
    
    def _physics_loop(self):
        """Loop principal de simulación física."""
        while self.running:
            try:
                # Actualizar física
                self._update_tank_dynamics()
                self._update_flows()
                self._update_pressures()
                self._update_ph_turbidity()
                self._update_temperature()
                
                # Actualizar sensores con valores calculados
                self._update_sensors()
                
                # Esperar siguiente actualización
                time.sleep(self.update_dt)
            except Exception as e:
                self.logger.error(f"[ERROR] Error en loop de física: {e}")
                time.sleep(1)
    
    def _update_tank_dynamics(self):
        """Actualizar nivel del tanque según flujos."""
        # Flujo de entrada (pump1)
        flow_in = 0
        if 'pump1' in self.actuators:
            pump = self.actuators['pump1']
            if pump.state == 'on':
                flow_in = (pump.value / 100.0) * self.pump_flow_rate  # L/min
        
        # Flujo de salida (pump2)
        flow_out = 0
        if 'pump2' in self.actuators:
            pump = self.actuators['pump2']
            if pump.state == 'on':
                flow_out = (pump.value / 100.0) * self.pump_flow_rate  # L/min
        
        # Evaporación
        evap = self.evaporation_rate
        
        # Calcular cambio de volumen
        delta_volume = (flow_in - flow_out - evap) * (self.update_dt / 60.0)  # dt en minutos
        
        # Actualizar volumen
        self.tank1_volume += delta_volume
        
        # Limitar al rango válido
        self.tank1_volume = max(0, min(self.tank_capacity, self.tank1_volume))
        
        # Log cambios significativos
        if abs(delta_volume) > 1:
            self.logger.debug(f"Tanque1: {self.tank1_volume:.0f}L ({self._get_tank_level():.1f}%) " +
                            f"[in={flow_in:.1f}, out={flow_out:.1f}, evap={evap:.1f} L/min]")
    
    def _get_tank_level(self) -> float:
        """Obtener nivel del tanque en porcentaje."""
        return (self.tank1_volume / self.tank_capacity) * 100.0
    
    def _update_flows(self):
        """Actualizar flujos de entrada/salida."""
        # Flujo de entrada
        flow_inlet = 0
        if 'pump1' in self.actuators:
            pump = self.actuators['pump1']
            if pump.state == 'on':
                flow_inlet = (pump.value / 100.0) * self.pump_flow_rate
        
        # Flujo de salida
        flow_outlet = 0
        if 'pump2' in self.actuators:
            pump = self.actuators['pump2']
            if pump.state == 'on':
                flow_outlet = (pump.value / 100.0) * self.pump_flow_rate
        
        # Actualizar sensores de flujo
        if 'flow_inlet' in self.sensors:
            self.sensors['flow_inlet'].set_value(flow_inlet)
        
        if 'flow_outlet' in self.sensors:
            self.sensors['flow_outlet'].set_value(flow_outlet)
    
    def _update_pressures(self):
        """Actualizar presiones de las bombas."""
        # Presión pump1 (depende de velocidad y nivel)
        if 'pump1' in self.actuators and 'pump1_pressure' in self.sensors:
            pump = self.actuators['pump1']
            
            if pump.state == 'on':
                # Presión proporcional a velocidad + carga por nivel
                base_pressure = (pump.value / 100.0) * 5.0  # 0-5 bar
                level_factor = 1.0 + (self._get_tank_level() / 100.0) * 0.3  # +30% máx
                pressure = base_pressure * level_factor
            else:
                pressure = 0.2  # Presión residual
            
            self.sensors['pump1_pressure'].set_value(pressure)
        
        # Presión pump2
        if 'pump2' in self.actuators and 'pump2_pressure' in self.sensors:
            pump = self.actuators['pump2']
            
            if pump.state == 'on':
                base_pressure = (pump.value / 100.0) * 4.5  # 0-4.5 bar
                level_factor = 0.7 + (self._get_tank_level() / 100.0) * 0.6  # Menos nivel = más presión
                pressure = base_pressure * level_factor
            else:
                pressure = 0.1
            
            self.sensors['pump2_pressure'].set_value(pressure)
    
    def _update_ph_turbidity(self):
        """Actualizar pH y turbidez basado en válvulas de dosificación."""
        # pH: tender hacia 7.0, válvula 1 corrige
        if 'tank1_ph' in self.sensors:
            current_ph = self.sensors['tank1_ph'].current_value
            
            # Deriva natural hacia pH neutro
            target_ph = 7.0
            drift = (target_ph - current_ph) * 0.05  # 5% por actualización
            
            # Corrección por válvula de dosificación
            if 'valve1' in self.actuators:
                valve = self.actuators['valve1']
                if valve.state == 'on':
                    correction = (valve.value / 100.0) * 0.2  # Ajuste más rápido
                    drift += correction if current_ph < 7.0 else -correction
            
            new_ph = current_ph + drift * (self.update_dt / 10.0)  # Normalizar por dt
            self.sensors['tank1_ph'].set_value(new_ph)
        
        # Turbidez: aumenta con tiempo, disminuye con flujo
        if 'tank1_turbidity' in self.sensors:
            current_turb = self.sensors['tank1_turbidity'].current_value
            
            # Aumento gradual (sedimentación)
            increase = 0.05 * (self.update_dt / 60.0)
            
            # Reducción por flujo de salida
            if 'flow_outlet' in self.sensors:
                flow_out = self.sensors['flow_outlet'].current_value
                reduction = (flow_out / self.pump_flow_rate) * 0.3
                increase -= reduction
            
            new_turb = max(0.5, current_turb + increase)  # Mínimo 0.5 NTU
            self.sensors['tank1_turbidity'].set_value(new_turb)
    
    def _update_temperature(self):
        """Actualizar temperatura ambiente (variación lenta)."""
        if 'ambient_temperature' in self.sensors:
            # Variación sinusoidal lenta
            import math
            current_time = time.time()
            
            # Ciclo de 24 horas (86400 segundos)
            base_temp = 20.0
            amplitude = 5.0
            temp = base_temp + amplitude * math.sin(2 * math.pi * current_time / 86400)
            
            self.sensors['ambient_temperature'].set_value(temp)
    
    def _update_sensors(self):
        """Actualizar sensores con valores del modelo físico."""
        # Nivel del tanque
        if 'tank1_level' in self.sensors:
            level = self._get_tank_level()
            self.sensors['tank1_level'].set_value(level)
    
    def get_state(self) -> Dict[str, Any]:
        """Obtener estado del modelo físico."""
        return {
            "running": self.running,
            "tank1_volume": round(self.tank1_volume, 1),
            "tank1_level_pct": round(self._get_tank_level(), 2),
            "tank_capacity": self.tank_capacity,
            "update_dt": self.update_dt
        }
