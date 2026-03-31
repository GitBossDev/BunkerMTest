namespace Greenhouse.Shared.Models;

/// <summary>
/// Modelo básico para mensajes MQTT en Fase 1
/// Representa un mensaje simple con timestamp para pruebas iniciales
/// En fases posteriores crearemos modelos más específicos (SensorReading, ActuatorCommand, etc.)
/// </summary>
public class MqttMessage
{
    /// <summary>
    /// Contenido del mensaje
    /// Puede ser texto simple, JSON serializado, o cualquier otro formato
    /// </summary>
    public string Content { get; set; } = string.Empty;

    /// <summary>
    /// Momento exacto en que se creó el mensaje
    /// Útil para debugging y entender el flujo de mensajes
    /// Usamos DateTime.UtcNow para evitar problemas de zonas horarias
    /// </summary>
    public DateTime Timestamp { get; set; } = DateTime.UtcNow;

    /// <summary>
    /// Topic donde se publicó o del cual se recibió el mensaje
    /// Los topics son como "direcciones" o "canales" en MQTT
    /// Ejemplo: "greenhouse/test/hello"
    /// </summary>
    public string Topic { get; set; } = string.Empty;

    /// <summary>
    /// Convierte el mensaje a formato legible para lectura humana
    /// </summary>
    public override string ToString()
    {
        return $"[{Timestamp:HH:mm:ss}] Topic: {Topic} | Content: {Content}";
    }
}
