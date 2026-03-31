namespace Greenhouse.Shared.Configuration;

/// <summary>
/// Configuración de conexión MQTT
/// Centraliza los parámetros de conexión al broker para que todos los clientes
/// usen la misma configuración
/// </summary>
public class MqttSettings
{
    /// <summary>
    /// Dirección del broker MQTT (servidor que gestiona los mensajes)
    /// "localhost" porque Mosquitto está en Docker en nuestra máquina
    /// En producción sería una IP o dominio específico
    /// </summary>
    public string BrokerHost { get; set; } = "localhost";

    /// <summary>
    /// Puerto estándar de MQTT sin encriptación
    /// 1883 es el puerto por defecto de MQTT
    /// 8883 se usa para MQTT con SSL/TLS (lo veremos en Fase 6)
    /// </summary>
    public int BrokerPort { get; set; } = 1883;

    /// <summary>
    /// Identificador único del cliente MQTT
    /// Cada cliente debe tener un ClientId único para que el broker los diferencie
    /// Si dos clientes usan el mismo ID, el broker desconectará al primero
    /// </summary>
    public string ClientId { get; set; } = string.Empty;

    /// <summary>
    /// Usuario para autenticación (opcional en Fase 1)
    /// En Fase 6 configuraremos autenticación en Mosquitto
    /// Por ahora allow_anonymous está en true en mosquitto.conf
    /// </summary>
    public string? Username { get; set; }

    /// <summary>
    /// Contraseña para autenticación (opcional en Fase 1)
    /// </summary>
    public string? Password { get; set; }

    /// <summary>
    /// Timeout de conexión en segundos
    /// Tiempo máximo que esperamos para establecer conexión con el broker
    /// </summary>
    public int ConnectionTimeoutSeconds { get; set; } = 10;

    /// <summary>
    /// Intervalo de Keep Alive en segundos
    /// El cliente enviará un "ping" al broker cada X segundos para mantener la conexión activa
    /// Si el broker no recibe nada durante KeepAlive * 1.5, considera la conexión muerta
    /// </summary>
    public int KeepAliveSeconds { get; set; } = 60;
}
