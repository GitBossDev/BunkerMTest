"""
Base Device - Clase base para todos los dispositivos IoT simulados
"""

import logging
import threading
from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseDevice(ABC):
    """
    Clase base abstracta para dispositivos IoT.
    Define la interfaz común para sensores y actuadores.
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Inicializar dispositivo base.
        
        Args:
            name: Nombre único del dispositivo
            config: Configuración específica del dispositivo
        """
        self.name = name
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{name}")
        
        # Estado
        self.running = False
        self.thread = None
        
    @abstractmethod
    def start(self):
        """Iniciar el dispositivo (debe ser implementado por subclases)."""
        pass
    
    @abstractmethod
    def stop(self):
        """Detener el dispositivo (debe ser implementado por subclases)."""
        pass
    
    @abstractmethod
    def get_state(self) -> Dict[str, Any]:
        """
        Obtener el estado actual del dispositivo.
        
        Returns:
            Diccionario con el estado del dispositivo
        """
        pass
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"
