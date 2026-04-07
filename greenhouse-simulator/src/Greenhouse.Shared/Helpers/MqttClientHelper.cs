using System;
using System.Security.Cryptography;
using MQTTnet;
using MQTTnet.Client;
using MQTTnet.Protocol;
using Greenhouse.Shared.Configuration;

namespace Greenhouse.Shared.Helpers;

/// <summary>
/// Clase helper para operaciones MQTT comunes
/// Centraliza la lógica de conexión, publicación y suscripción
/// Abstrae la complejidad de MQTTnet para facilitar el aprendizaje
/// </summary>
public class MqttClientHelper
{
    private int errores_mqttClient = 0;
    private readonly MqttSettings _settings;
    private IMqttClient? _mqttClient;

    public MqttClientHelper(MqttSettings settings)
    {
        _settings = settings;
    }

    /// <summary>
    /// Verifica si el cliente está conectado al broker
    /// </summary>
    public bool IsConnected => _mqttClient?.IsConnected ?? false;

    /// <summary>
    /// Identificador único de cliente MQTT configurado
    /// </summary>
    public string ClientId => _settings.ClientId;


    /**
    * Conecta al broker MQTT utilizando las opciones configuradas
    * MqttFactory es el punto de entrada de MQTTnet, nos permite crear clientes, servidores, etc.
    * Configura opciones de conexión como host, puerto, client ID, keep alive, timeout y credenciales
    * Se suscribe a eventos de desconexión para detectar pérdidas de conexión
    * Intenta conectar al broker y verifica el resultado para asegurar que la conexión fue exitosa
    * Si la conexión falla, se captura la excepción y se muestra un mensaje de error
    */
    public async Task<IMqttClient> ConnectAsync()
    {
        // MqttFactory es el punto de entrada de MQTTnet
        // Nos permite crear clientes, servidores, etc.
        var factory = new MqttFactory();

        // Crear instancia de cliente MQTT
        _mqttClient = factory.CreateMqttClient();

        // Configurar opciones de conexión
        var optionsBuilder = new MqttClientOptionsBuilder()
            .WithTcpServer(_settings.BrokerHost, _settings.BrokerPort) // Dirección del broker
            .WithClientId(_settings.ClientId)                          // ID único del cliente
            .WithKeepAlivePeriod(TimeSpan.FromSeconds(_settings.KeepAliveSeconds)) // Mantener conexión viva
            .WithTimeout(TimeSpan.FromSeconds(_settings.ConnectionTimeoutSeconds)); // Timeout de conexión

        if (!string.IsNullOrEmpty(_settings.Username))
        {
            optionsBuilder = optionsBuilder.WithCredentials(_settings.Username, _settings.Password ?? string.Empty);
        }

        var options = optionsBuilder.Build();

        // Suscribirse a eventos de desconexión
        // Esto nos permite detectar cuando perdemos la conexión con el broker
        _mqttClient.DisconnectedAsync += async e =>
        {
            Console.WriteLine($"[MQTT] Desconectado del broker. Razón: {e.Reason}");

            // En producción aquí implementaríamos reconexión automática
            // Por ahora solo informamos al usuario
            if (e.Exception != null)
            {
                Console.WriteLine($"[MQTT] Excepción: {e.Exception.Message}");
            }

            await Task.CompletedTask;
        };

        // Intentar conectar al broker
        try
        {
            var result = await _mqttClient.ConnectAsync(options);

            // Verificar si la conexión fue exitosa
            if (result.ResultCode == MqttClientConnectResultCode.Success)
            {
                Console.WriteLine($"[MQTT] Conectado exitosamente al broker {_settings.BrokerHost}:{_settings.BrokerPort}");
                Console.WriteLine($"[MQTT] Cliente ID: {_settings.ClientId}");
            }
            else
            {
                Console.WriteLine($"[MQTT] Error al conectar: {result.ResultCode}");
                Console.WriteLine($"[MQTT] Razón: {result.ReasonString}");
            }

            return _mqttClient;
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[MQTT] Excepción al conectar: {ex.Message}");
            throw;
        }
    }

    /**
        * Publica un mensaje en un topic específico
        * PUBLISHER: Esta es la operación fundamental de un "publicador" en MQTT
        * Al publicar en un topic, el broker se encargará de distribuir ese mensaje a todos
        * los suscriptores que estén suscritos a ese topic (o subtopics si se usan comodines)
        * El argumento qos define la calidad de servicio deseada para la publicación (0, 1, o 2)
        * El argumento retain indica si el mensaje debe ser retenido por el broker para futuros suscriptores
        * El resultado de la publicación se verifica para asegurarnos de que el broker aceptó el mensaje
        * Si la publicación falla, se incrementa el contador de errores para su posterior análisis
        */
    public async Task PublishAsync(string topic, string payload, MqttQualityOfServiceLevel qos = MqttQualityOfServiceLevel.AtMostOnce, bool retain = false)
    {
        if (_mqttClient == null || !_mqttClient.IsConnected)
        {
            throw new InvalidOperationException("Cliente MQTT no está conectado. Llama a ConnectAsync() primero.");
        }

        // Construir el mensaje MQTT
        var message = new MqttApplicationMessageBuilder()
            .WithTopic(topic)                    // A qué topic/canal enviar
            .WithPayload(payload)                // Contenido del mensaje
            .WithQualityOfServiceLevel(qos)      // Nivel de QoS (0, 1, o 2)
            .WithRetainFlag(retain)              // Si debe guardarse en el broker
            .Build();

        // Enviar mensaje al broker
        var result = await _mqttClient.PublishAsync(message);


        // QoS 0: No hay confirmación, el mensaje "se lanza y se olvida"
        // QoS 1: El broker confirma que recibió el mensaje
        // QoS 2: Confirmación de dos pasos, garantiza entrega única

        if (result.ReasonCode == MqttClientPublishReasonCode.NoMatchingSubscribers)
        {
            Console.WriteLine("[MQTT] Error: Sin permisos para publicar en este topic (ACL).");
        }
        else if (qos > MqttQualityOfServiceLevel.AtMostOnce)
        {
            // Solo para QoS 1 y 2 tenemos confirmación del broker
            Console.WriteLine($"[MQTT] Mensaje publicado en '{topic}' | QoS: {qos} | Retain: {retain} | Resultado: {result.ReasonCode}");
        }
        else if (qos == MqttQualityOfServiceLevel.AtMostOnce)
        {
            Console.WriteLine($"[MQTT] Error al publicar en '{topic}'. ReasonCode: {result.ReasonCode} (sin confirmación en QoS 0)");
            errores_mqttClient = errores_mqttClient + 1;
        }

    }

    /**
        * Suscribe a un topic específico para recibir mensajes
        * SUBSCRIBER: Esta es la operación fundamental de un "suscriptor" en MQTT
        * Al suscribirse a un topic, el broker enviará todos los mensajes publicados en ese topic (y subtopics si se usan comodines)
        * El argumento qos define la calidad de servicio deseada para la suscripción (0, 1, o 2)
        * El resultado de la suscripción se verifica para asegurarnos de que el broker aceptó la suscripción y con qué QoS se concedió
        * Si la suscripción falla, se incrementa el contador de errores para su posterior análisis
        */

    public async Task SubscribeAsync(string topic, MqttQualityOfServiceLevel qos = MqttQualityOfServiceLevel.AtMostOnce)
    {
        if (_mqttClient == null || !_mqttClient.IsConnected)
        {
            throw new InvalidOperationException("Cliente MQTT no está conectado. Llama a ConnectAsync() primero.");
        }

        // Construir opciones de suscripción
        var subscribeOptions = new MqttClientSubscribeOptionsBuilder()
            .WithTopicFilter(f =>
            {
                f.WithTopic(topic);              // Topic al cual suscribirse
                f.WithQualityOfServiceLevel(qos); // QoS deseado
            })
            .Build();

        // Enviar suscripción al broker
        var result = await _mqttClient.SubscribeAsync(subscribeOptions);

        // Verificar resultado
        foreach (var subscription in result.Items)
        {
            if (subscription.ResultCode == MqttClientSubscribeResultCode.GrantedQoS0 ||
                subscription.ResultCode == MqttClientSubscribeResultCode.GrantedQoS1 ||
                subscription.ResultCode == MqttClientSubscribeResultCode.GrantedQoS2)
            {
                Console.WriteLine($"[MQTT] Suscrito exitosamente a '{topic}' | QoS: {subscription.ResultCode}");
            }
            else
            {
                Console.WriteLine($"[MQTT] Error al suscribirse a '{topic}': {subscription.ResultCode}");
                errores_mqttClient = errores_mqttClient + 1;
            }
        }
    }
    public async Task<int> CompruebaFin()
    {
        return errores_mqttClient;
    }

    /**
    * Establece un manejador para recibir mensajes entrantes
    * Este método permite al usuario definir cómo procesar los mensajes recibidos
    * El handler se ejecutará cada vez que llegue un mensaje a cualquier topic al que estemos suscritos
    * El argumento MqttApplicationMessageReceivedEventArgs contiene toda la información del mensaje (topic, payload, QoS, etc.)
    */
    public void SetMessageHandler(Func<MqttApplicationMessageReceivedEventArgs, Task> handler)
    {
        if (_mqttClient == null)
        {
            throw new InvalidOperationException("Cliente MQTT no ha sido creado. Llama a ConnectAsync() primero.");
        }

        // ApplicationMessageReceivedAsync es el evento que se dispara cuando llega un mensaje
        _mqttClient.ApplicationMessageReceivedAsync += handler;
    }

    /// <summary>
    /// Desconecta limpiamente del broker MQTT
    /// Importante: Siempre desconectar apropiadamente antes de cerrar la aplicación
    /// </summary>
    public async Task DisconnectAsync()
    {
        if (_mqttClient != null && _mqttClient.IsConnected)
        {
            await _mqttClient.DisconnectAsync();
            Console.WriteLine("[MQTT] Desconectado del broker correctamente");
        }

        _mqttClient?.Dispose();
    }

    /// <summary>
    /// Genera un hash de contraseña compatible con DynSec (PBKDF2-SHA256) y salt aleatorio.
    /// Devuelve los valores codificados en Base64 y las iteraciones.
    /// </summary>
    /// <param name="password">Contraseña en texto plano.</param>
    /// <param name="iterations">Iteraciones PBKDF2 (por defecto 101, igual que el dynsec de Mosquitto).</param>
    /// <returns>Objeto con password (hash), salt e iterations.</returns>
    public static (string PasswordBase64, string SaltBase64, int Iterations) CreateDynSecPasswordHash(string password, int iterations = 101)
    {
        if (string.IsNullOrEmpty(password))
            throw new ArgumentException("La contraseña no puede estar vacía.", nameof(password));

        const int saltBytes = 16;
        const int hashBytes = 32;

        byte[] salt = new byte[saltBytes];
        using (var rng = RandomNumberGenerator.Create())
        {
            rng.GetBytes(salt);
        }

        byte[] hash;
        using (var pbkdf2 = new Rfc2898DeriveBytes(password, salt, iterations, HashAlgorithmName.SHA256))
        {
            hash = pbkdf2.GetBytes(hashBytes);
        }

        // El valor Base64 no debería contener backslashes, pero por seguridad eliminamos los escapes no deseados.
        string passwordBase64 = Convert.ToBase64String(hash).Replace("\\", string.Empty);
        string saltBase64 = Convert.ToBase64String(salt).Replace("\\", string.Empty);

        return (
            PasswordBase64: passwordBase64,
            SaltBase64: saltBase64,
            Iterations: iterations
        );
    }
}
