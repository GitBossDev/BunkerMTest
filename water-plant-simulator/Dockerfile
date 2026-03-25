# Dockerfile para el simulador de planta de tratamiento
# Build: docker build -t water-plant-simulator .

FROM python:3.11-slim

# Metadatos
LABEL maintainer="BunkerM Test"
LABEL description="Water Plant IoT Simulator for BunkerM Testing"

# Variables de entorno
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Directorio de trabajo
WORKDIR /app

# Copiar requirements
COPY requirements.txt .

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY src/ ./src/
COPY config/ ./config/

# Crear directorio para logs
RUN mkdir -p /app/logs

# Usuario no privilegiado (seguridad)
RUN useradd -m -u 1000 simulator && \
    chown -R simulator:simulator /app

USER simulator

# Comando de inicio
CMD ["python", "-m", "src.main"]
