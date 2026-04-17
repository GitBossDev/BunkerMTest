using Greenhouse.Shared.Configuration;
using Greenhouse.Shared.Helpers;
using MQTTnet.Protocol;
using System.Text;

/*
 * GREENHOUSE CONTROLLER - SUBSCRIBER (FASE 1)
 * 
 * Este programa actúa como SUBSCRIBER (Suscriptor) en MQTT
 * Su trabajo es RECIBIR mensajes del broker que fueron publicados en topics específicos
 * 
 * CONCEPTOS CLAVE:
 * - Subscriber: Cliente que SE SUSCRIBE a topics para RECIBIR mensajes
 * - Subscribe: Registrarse en el broker para recibir mensajes de un topic
 * - Message Handler: Función que se ejecuta cada vez que llega un mensaje
 * - Wildcards: + y # permiten suscribirse a múltiples topics a la vez
 *   + : Un nivel de jerarquía (ej: "sensor/+/temp" recibe "sensor/1/temp", "sensor/2/temp")
 *   # : Múltiples niveles (ej: "sensor/#" recibe todo bajo "sensor/")
 */

Console.WriteLine("==============================================");
Console.WriteLine("  GREENHOUSE MQTT - SUBSCRIBER (Fase 1)");
Console.WriteLine("==============================================\n");

var brokerHost = Environment.GetEnvironmentVariable("MQTT_HOST") ?? "localhost";
var brokerUser = Environment.GetEnvironmentVariable("MQTT_USER") ?? "bunker";
var brokerPass = Environment.GetEnvironmentVariable("MQTT_PASS") ?? "bunker";
var brokerPort = 21900;
var brokerPortRaw = Environment.GetEnvironmentVariable("MQTT_PORT");
if (!string.IsNullOrWhiteSpace(brokerPortRaw) && int.TryParse(brokerPortRaw, out var parsedBrokerPort) && parsedBrokerPort > 0)
{
    brokerPort = parsedBrokerPort;
}

// Configurar parámetros de conexión MQTT
var settings = new MqttSettings
{
    BrokerHost = brokerHost,
    BrokerPort = brokerPort,
    ClientId = "greenhouse-subscriber-01",  // Diferente al publisher
    Username = brokerUser,
    Password = brokerPass
};

Console.WriteLine($"Configuración:");
Console.WriteLine($"  Broker: {settings.BrokerHost}:{settings.BrokerPort}");
Console.WriteLine($"  Client ID: {settings.ClientId}");
Console.WriteLine($"  Username: {settings.Username}\n");

// Crear helper MQTT
var mqttHelper = new MqttClientHelper(settings);

try
{
    Console.WriteLine("Conectando al broker MQTT...");
    var client = await mqttHelper.ConnectAsync(1);

    if (!mqttHelper.IsConnected)
    {
        Console.WriteLine("\n[ERROR] No se pudo conectar al broker.");
        Console.WriteLine("Asegúrate de que Docker Desktop está corriendo");
        Console.WriteLine("y ejecuta: docker-compose up -d");
        return;
    }

    // Configurar el manejador de mensajes
    // Este callback se ejecuta cada vez que llega un mensaje a un topic suscrito
    mqttHelper.SetMessageHandler(async e =>
    {
        // Extraer información del mensaje recibido
        var topic = e.ApplicationMessage.Topic;
        var payload = Encoding.UTF8.GetString(e.ApplicationMessage.PayloadSegment);
        var qos = e.ApplicationMessage.QualityOfServiceLevel;
        var timestamp = DateTime.Now;

        // Mostrar el mensaje recibido con formato legible
        Console.WriteLine($"\n┌─ MENSAJE RECIBIDO ─────────────────────────────");
        Console.WriteLine($"│ Timestamp: {timestamp:HH:mm:ss.fff}");
        Console.WriteLine($"│ Topic:     {topic}");
        Console.WriteLine($"│ QoS:       {qos}");
        Console.WriteLine($"│ Payload:   {payload}");
        Console.WriteLine($"└────────────────────────────────────────────────\n");

        await Task.CompletedTask;
    });

    Console.WriteLine("\n==============================================");
    Console.WriteLine("  SUSCRIPCIONES ACTIVAS");
    Console.WriteLine("==============================================\n");

    // Suscripción general para cada tópico, así probamos que los mensajes se publican correctamente.
    await mqttHelper.SubscribeAsync(
        topic: "lab/device/#",
        qos: MqttQualityOfServiceLevel.AtMostOnce
    );

    // Mantener la aplicación corriendo para escuchar mensajes
    // En aplicaciones reales, aquí también procesarías la lógica de negocio
    while (true)
    {
        await Task.Delay(1000);
    }
}
catch (Exception ex)
{
    Console.WriteLine($"\n[ERROR] {ex.Message}");
    if (ex.InnerException != null)
    {
        Console.WriteLine($"[ERROR INTERNO] {ex.InnerException.Message}");
    }
}
finally
{
    Console.WriteLine("\n\nDesconectando del broker...");
    await mqttHelper.DisconnectAsync();
    Console.WriteLine("Aplicación finalizada.");
}
