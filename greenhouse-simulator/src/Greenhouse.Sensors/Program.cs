using Greenhouse.Shared.Configuration;
using Greenhouse.Shared.Helpers;
using MQTTnet.Protocol;
using System.Threading;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Diagnostics;
using System.IO;
using System.Numerics;

/**
    * GREENHOUSE SENSORS - PUBLISHER (FASE 1)
    * 
    * Este programa trata de actuar como generador de mensajes para MQTT,
    * con el objetivo de probar la capacidad del broker y la estabilidad de las conexiones.

    * Estructura del programa:
    * - Comprueba parámetros de entrada (host, user, pass, clients, timeunit, time), establece el tiempo entre mensajes.
    * - Empieza a lanzar tareas asíncronas en base al número de clientes deseados con un delay de 0.5 segundos 
    * - Cada tarea manda al método: MyFunctionAsync, que se encarga de crear un cliente MQTT, conectarse al broker, y publicar mensajes o suscribirse a topics de forma aleatoria.
    * - Lo primero que hace el método es comprobar la conexion con la cuenta del cliente mediante el método ComprobadorDeConexiones, que devuelve la conexión MQTT.
    * - Luego, un cliente realiza un número aleatorio de acciones entre 5 y 20 (este no incluido), con el tiempo de espera.
    * - Cada acción es aleatoria entre publicar o suscribirse a un topic, y el topic también se elige de forma aleatoria entre CO2, Humedad o Temperatura. Además, el QoS de cada mensaje también se elige de forma aleatoria entre 0, 1 y 2.
    */
class Programa
{
    static int id_cliente = 0;
    static int cuenta_errores = 0;

    static string host = "";
    static string user = "";
    static string pass = "";
    static int brokerPort = 1900;
    static int clients = 0;
    static int clients_t = 0;
    static int timeunit = 0;
    static int qos = 0;
    static int time = 0;
    static int msgs = 0;
    static int contadorEnvios = 0;
    static int contadorSuscripciones = 0;
    static int totalDatosEnviadosSubs = 0;
    static bool retain;

    static async Task Main(string[] args)
    {

        // Fallback a variables de entorno si CLI no se pasó
        host = string.IsNullOrEmpty(host) ? Environment.GetEnvironmentVariable("MQTT_HOST") : host;
        user = string.IsNullOrEmpty(user) ? Environment.GetEnvironmentVariable("MQTT_USER") : user;
        pass = string.IsNullOrEmpty(pass) ? Environment.GetEnvironmentVariable("MQTT_PASS") : pass;
        var envPort = Environment.GetEnvironmentVariable("MQTT_PORT");
        if (!string.IsNullOrWhiteSpace(envPort) && int.TryParse(envPort, out var parsedPort) && parsedPort > 0)
        {
            brokerPort = parsedPort;
        }
        clients = clients == 0 ? int.Parse(Environment.GetEnvironmentVariable("CLIENTS")) : clients;
        timeunit = timeunit == 0 ? int.Parse(Environment.GetEnvironmentVariable("TIMEUNIT")) : timeunit;
        time = time == 0 ? int.Parse(Environment.GetEnvironmentVariable("TIME")) : time;
        msgs = msgs == 0 ? int.Parse(Environment.GetEnvironmentVariable("MSGS")) : msgs;
        qos = qos == 0 ? int.Parse(Environment.GetEnvironmentVariable("QOS")) : qos;
        retain = bool.Parse(Environment.GetEnvironmentVariable("RETAIN"));

        clients_t = clients;

        Console.WriteLine($"Conectando a {host}:{brokerPort} con {user}");

        Console.WriteLine("==============================================");
        Console.WriteLine("  GREENHOUSE MQTT STRESSER - FASE 1");
        Console.WriteLine("==============================================\n");
        // Convertir el tiempo a milisegundos según la unidad seleccionada
        switch (timeunit)
        {
            case 1:
                time = time * 3600000;
                break;
            case 2:
                time = time * 60000;
                break;
            case 3:
                time = time * 1000;
                break;
            default:
                break;
        }

        Console.WriteLine("\n==============================================");
        Console.WriteLine("PUBLICACIÓN DE MENSAJES");
        Console.WriteLine("==============================================\n");


        var tasks = new List<Task>();

        // El número de clientes se lanza con un delay entre cada uno para evitar picos de conexión simultáneos
        while (clients > 0)
        {
            clients--;
            // Lanzar la función asíncrona en un task en lugar de usar Thread directamente
            tasks.Add(Task.Run(() => MyFunctionAsync(time)));

            // tiempo entre comienzo de la task de cada cliente
            await Task.Delay(10);

        }

        // Esperar a que todos los publishers terminen su ciclo de mensajes
        await Task.WhenAll(tasks);

        double porcentaje_subs = contadorSuscripciones / (double)totalDatosEnviadosSubs * 100;
        double porcentaje_pubs = contadorEnvios / (double)totalDatosEnviadosSubs * 100;

        Console.WriteLine($"\nTodos los publishers han terminado. Total de errores: {cuenta_errores}");

        Console.WriteLine($"\nTotal mensajes que se han intentado publicar: {contadorEnvios} ({porcentaje_pubs}%).\nTotal suscripciones que se han intentado realizar: {contadorSuscripciones} ({porcentaje_subs}%).");
        Console.WriteLine($"\nTotal de relaciones simuladas: {contadorEnvios + contadorSuscripciones}");
        Console.WriteLine($"\nErrores en alguna de las relaciones debido a la falta de autorización: {cuenta_errores}");
        int c = 0;
        while (c == 0)
        {

        }
    }

    static async Task MyFunctionAsync(int tiempo)
    {
        MqttClientHelper mqttHelper = await ComprobadorDeConexiones(); //Comprueba la conexion con la cuenta del cliente y espera que cada task termine

        string[] id_partes = mqttHelper.ClientId.Split('-');
        int id_sensor = int.Parse(id_partes[^1]) + 100000000;


        await mqttHelper.PublishAsync(
        topic: $"lab/device/{id_sensor}/Estatus_conexion",
        payload: "Conectado",
        qos: MqttQualityOfServiceLevel.AtLeastOnce,
        retain: retain
        );

        //Intenta diversas opciones para el cliente.
        try
        {
            int messageCount = msgs;

            var sensores = new[] { "CO2", "Humedad", "Temperatura" };
            var estados = new[] { "", "/status" };
            var qosLevels = new[]
            {
                    MqttQualityOfServiceLevel.AtMostOnce,
                    MqttQualityOfServiceLevel.AtLeastOnce,
                    MqttQualityOfServiceLevel.ExactlyOnce
            };

            for (int i = 0; i < messageCount; i++)
            {
                id_partes = mqttHelper.ClientId.Split('-');
                id_sensor = int.Parse(id_partes[^1]) + 100000000;

                Interlocked.Increment(ref totalDatosEnviadosSubs); //Interlocked para evitar problemas de concurrencia al actualizar el contador desde múltiples tareas
                var sensores_co2 = new List<Sensor_c02> { new Sensor_c02 { Id = id_sensor, Nivel_c02 = Random.Shared.Next(300, 1000) } };
                var sensores_humedad = new List<Sensor_humedad> { new Sensor_humedad { Id = id_sensor, Humedad = Random.Shared.Next(90, 100) } };
                var sensores_temp = new List<Sensor_Temp> { new Sensor_Temp { Id = id_sensor, Temperatura = Random.Shared.Next(15, 35) } };
                // Opciones para formatear el JSON
                var opciones = new JsonSerializerOptions { WriteIndented = true };


                //CASO 1: Cliente se subscribe. CASO 2: Cliente publica.
                int tipo = Random.Shared.Next(1, 3); //Random entre 1 y 2

                string sensor = sensores[Random.Shared.Next(sensores.Length)];
                string estado = estados[Random.Shared.Next(estados.Length)];

                string topic = $"lab/device/{id_sensor}/{sensor}{estado}";

                // Si el tipo es 1, el cliente se suscribe al topic. Si es 2, publica un mensaje en el topic.
                if (tipo == 1)
                {
                    Console.WriteLine($"Subscriber {mqttHelper.ClientId} suscrito a: {topic}");

                    await mqttHelper.SubscribeAsync(
                        topic: topic,
                        qos: qosLevels[qos]
                    );

                    Interlocked.Increment(ref contadorSuscripciones);
                }
                else
                {
                    string payload = "";

                    if (estado == "/status")
                    {
                        payload = Random.Shared.Next(2) == 0 ? "True" : "False";
                    }
                    else
                    {
                        switch (sensor)
                        {
                            case "CO2":
                                payload = JsonSerializer.Serialize(sensores_co2, opciones);
                                break;
                            case "Humedad":
                                payload = JsonSerializer.Serialize(sensores_humedad, opciones);
                                break;
                            case "Temperatura":
                                payload = JsonSerializer.Serialize(sensores_temp, opciones);
                                break;
                        }
                        ;
                    }

                    await mqttHelper.PublishAsync(
                        topic: topic,
                        payload: payload,
                        qos: qosLevels[qos],
                        retain: retain
                    );

                    Interlocked.Increment(ref contadorEnvios);
                }

                Console.WriteLine($"Mensaje: #{i + 1}, Publisher: {mqttHelper.ClientId} en el topic con id: {id_sensor}");

                int cuenta_tiempo = msgs * clients_t;

                double subs_act = contadorSuscripciones / (double)cuenta_tiempo * 100;
                double pubs_act = contadorEnvios / (double)cuenta_tiempo * 100;
                double total_act = (contadorSuscripciones + contadorEnvios) / (double)cuenta_tiempo * 100;
                Console.WriteLine($"\nPublicaciones actuales: {contadorEnvios} ({pubs_act}%).\nSuscripciones actuales: {contadorSuscripciones} ({subs_act}%).\nTotal de relaciones simuladas actuales: {contadorEnvios + contadorSuscripciones} ({total_act}%).\n");

                await Task.Delay(tiempo);
                // Evitar esperar después del último mensaje

            }
            cuenta_errores = cuenta_errores + await mqttHelper.CompruebaFin();
        }
        catch (Exception ex)
        {
            cuenta_errores++;
            Console.WriteLine($"\n[ERROR] {ex.Message}");
            if (ex.InnerException != null)
            {
                Console.WriteLine($"[ERROR INTERNO] {ex.InnerException.Message}");
            }
        }
        finally
        {
            // DESCONEXIÓN LIMPIA:
            //await mqttHelper.DisconnectAsync();
        }

    }
    /**
    * Función para comprobar la conexión al broker MQTT con las credenciales del cliente.
    * Devuelve un helper MQTT conectado o null si la conexión falla.
    */
    static async Task<MqttClientHelper?> ComprobadorDeConexiones()
    {
        id_cliente = id_cliente + 1;
        // Configurar parámetros de conexión MQTT

        MqttSettings settings = new MqttSettings
        {
            BrokerHost = host,
            BrokerPort = brokerPort,
            ClientId = $"greenhouse-publisher-{id_cliente}",
            Username = id_cliente.ToString(),
            Password = "123456",
            KeepAliveSeconds = 3,
        };

        // Crear helper MQTT y conectar al broker
        MqttClientHelper mqttHelper = new(settings);
        await mqttHelper.ConnectAsync(id_cliente);

        if (!mqttHelper.IsConnected)
        {
            Console.WriteLine("\n[ERROR] No se pudo conectar al broker.");
            return null;
        }
        return mqttHelper;
    }

    /**
    * Función para añadir o actualizar un cliente en el dynamic-security.json de Mosquitto
    * con roles seleccionados aleatoriamente (publish-only o subscribe-only)
    */


    internal class Sensor_c02
    {
        public int Id { get; set; }
        public int Nivel_c02 { get; set; }
    }

    internal class Sensor_Temp
    {
        public int Id { get; set; }
        public int Temperatura { get; set; }
    }
    internal class Sensor_humedad
    {
        public int Id { get; set; }
        public int Humedad { get; set; }
    }
}