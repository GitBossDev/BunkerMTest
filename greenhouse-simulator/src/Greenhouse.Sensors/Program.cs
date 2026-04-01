using Greenhouse.Shared.Configuration;
using Greenhouse.Shared.Helpers;
using MQTTnet.Protocol;
using System.Threading;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Diagnostics;
using System.IO;

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
    static int clients = 0;
    static int timeunit = 0;
    static int time = 0;
    static async Task Main(string[] args)
    {



        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] == "--host") host = args[++i];
            if (args[i] == "--user") user = args[++i];
            if (args[i] == "--pass") pass = args[++i];
            if (args[i] == "--clients") clients = int.Parse(args[++i]);
            if (args[i] == "--timeunit") timeunit = int.Parse(args[++i]);
            if (args[i] == "--time") time = int.Parse(args[++i]);
        }
        // Fallback a variables de entorno si CLI no se pasó
        host = string.IsNullOrEmpty(host) ? Environment.GetEnvironmentVariable("MQTT_HOST") : host;
        user = string.IsNullOrEmpty(user) ? Environment.GetEnvironmentVariable("MQTT_USER") : user;
        pass = string.IsNullOrEmpty(pass) ? Environment.GetEnvironmentVariable("MQTT_PASS") : pass;
        clients = clients == 0 ? int.Parse(Environment.GetEnvironmentVariable("CLIENTS") ?? "100") : clients;
        timeunit = timeunit == 0 ? int.Parse(Environment.GetEnvironmentVariable("TIMEUNIT") ?? "3") : timeunit;
        time = time == 0 ? int.Parse(Environment.GetEnvironmentVariable("TIME") ?? "1") : time;

        Console.WriteLine($"Conectando a {host} con {user}");

        Console.WriteLine("==============================================");
        Console.WriteLine("  GREENHOUSE MQTT - PUBLISHERS");
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
                time = time * 1000;
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
            await Task.Delay(500);

        }

        // Esperar a que todos los publishers terminen su ciclo de mensajes
        await Task.WhenAll(tasks);

        Console.WriteLine($"\nTodos los publishers han terminado. Total de errores: {cuenta_errores}");
    }

    static async Task MyFunctionAsync(int tiempo)
    {

        MqttClientHelper mqttHelper = await ComprobadorDeConexiones(); //Comprueba la conexion con la cuenta del cliente y espera que cada task termine


        //Intenta diversas opciones para el cliente.
        try
        {
            int messageCount = Random.Shared.Next(5, 20);
            int id_sensor = Random.Shared.Next(100000000, 999999999);

            //Manda cantidad aleatoria de mensajes entre 5 y 19.
            for (int i = 0; i < messageCount; i++)
            {
                var sensores_co2 = new List<Sensor_c02> { new Sensor_c02 { Id = id_sensor, Nivel_c02 = Random.Shared.Next(300, 1000) } };
                var sensores_humedad = new List<Sensor_humedad> { new Sensor_humedad { Id = id_sensor, Humedad = Random.Shared.Next(90, 100) } };
                var sensores_temp = new List<Sensor_Temp> { new Sensor_Temp { Id = id_sensor, Temperatura = Random.Shared.Next(15, 35) } };
                // Opciones para formatear el JSON
                var opciones = new JsonSerializerOptions { WriteIndented = true };

                //CASO 1: Cliente se subscribe. CASO 2: Cliente publica. CASO 3: Ambos casos
                switch (Random.Shared.Next(1, 3))
                {
                    case 1:

                        switch (Random.Shared.Next(1, 10)) // de 1 a 9
                        {
                            // QOS 0
                            case 1:
                                Console.WriteLine($"Subscriber {mqttHelper.ClientId} suscrito a: lab/device/{id_sensor}/");
                                await mqttHelper.SubscribeAsync(
                                    topic: $"lab/device/{id_sensor}/CO2",
                                    qos: MqttQualityOfServiceLevel.AtMostOnce
                                );
                                Console.WriteLine($"Mensaje: #{i}, Publisher: {mqttHelper.ClientId} en el topic con id: {id_sensor}");
                                break;
                            case 2:
                                Console.WriteLine($"Subscriber {mqttHelper.ClientId} suscrito a: lab/device/{id_sensor}/");
                                await mqttHelper.SubscribeAsync(
                                    topic: $"lab/device/{id_sensor}/Humedad",
                                    qos: MqttQualityOfServiceLevel.AtMostOnce
                                );
                                Console.WriteLine($"Mensaje: #{i}, Publisher: {mqttHelper.ClientId} en el topic con id: {id_sensor}");
                                break;
                            case 3:
                                Console.WriteLine($"Subscriber {mqttHelper.ClientId} suscrito a: lab/device/{id_sensor}/");
                                await mqttHelper.SubscribeAsync(
                                    topic: $"lab/device/{id_sensor}/Temperatura",
                                    qos: MqttQualityOfServiceLevel.AtMostOnce
                                );
                                Console.WriteLine($"Mensaje: #{i}, Publisher: {mqttHelper.ClientId} en el topic con id: {id_sensor}");
                                break;
                            // QOS 1
                            case 4:
                                Console.WriteLine($"Subscriber {mqttHelper.ClientId} suscrito a: lab/device/{id_sensor}/");
                                await mqttHelper.SubscribeAsync(
                                    topic: $"lab/device/{id_sensor}/CO2",
                                    qos: MqttQualityOfServiceLevel.AtLeastOnce
                                );
                                Console.WriteLine($"Mensaje: #{i}, Publisher: {mqttHelper.ClientId} en el topic con id: {id_sensor}");
                                break;
                            case 5:
                                Console.WriteLine($"Subscriber {mqttHelper.ClientId} suscrito a: lab/device/{id_sensor}/");
                                await mqttHelper.SubscribeAsync(
                                    topic: $"lab/device/{id_sensor}/Humedad",
                                    qos: MqttQualityOfServiceLevel.AtLeastOnce
                                );
                                Console.WriteLine($"Mensaje: #{i}, Publisher: {mqttHelper.ClientId} en el topic con id: {id_sensor}");
                                break;
                            case 6:
                                Console.WriteLine($"Subscriber {mqttHelper.ClientId} suscrito a: lab/device/{id_sensor}/");
                                await mqttHelper.SubscribeAsync(
                                    topic: $"lab/device/{id_sensor}/Temperatura",
                                    qos: MqttQualityOfServiceLevel.AtLeastOnce
                                );
                                Console.WriteLine($"Mensaje: #{i}, Publisher: {mqttHelper.ClientId} en el topic con id: {id_sensor}");
                                break;
                            // QOS 2
                            case 7:
                                Console.WriteLine($"Subscriber {mqttHelper.ClientId} suscrito a: lab/device/{id_sensor}/");
                                await mqttHelper.SubscribeAsync(
                                    topic: $"lab/device/{id_sensor}/CO2",
                                    qos: MqttQualityOfServiceLevel.ExactlyOnce
                                );
                                Console.WriteLine($"Mensaje: #{i}, Publisher: {mqttHelper.ClientId} en el topic con id: {id_sensor}");
                                break;
                            case 8:
                                Console.WriteLine($"Subscriber {mqttHelper.ClientId} suscrito a: lab/device/{id_sensor}/");
                                await mqttHelper.SubscribeAsync(
                                    topic: $"lab/device/{id_sensor}/Humedad",
                                    qos: MqttQualityOfServiceLevel.ExactlyOnce
                                );
                                Console.WriteLine($"Mensaje: #{i}, Publisher: {mqttHelper.ClientId} en el topic con id: {id_sensor}");
                                break;
                            case 9:
                                Console.WriteLine($"Subscriber {mqttHelper.ClientId} suscrito a: lab/device/{id_sensor}/");
                                await mqttHelper.SubscribeAsync(
                                    topic: $"lab/device/{id_sensor}/Temperatura",
                                    qos: MqttQualityOfServiceLevel.ExactlyOnce
                                );
                                Console.WriteLine($"Mensaje: #{i}, Publisher: {mqttHelper.ClientId} en el topic con id: {id_sensor}");
                                break;
                        }
                        break;
                    case 2:
                        Console.WriteLine($"Publisher {mqttHelper.ClientId} publicando {messageCount} mensajes cada {tiempo / 1000} segundos...");
                        switch (Random.Shared.Next(1, 10)) // de 1 a 9
                        {
                            // QOS 0
                            case 1:
                                await mqttHelper.PublishAsync(

                                    topic: $"lab/device/{id_sensor}/CO2",
                                    payload: JsonSerializer.Serialize(sensores_co2, opciones),
                                    qos: MqttQualityOfServiceLevel.AtMostOnce
                                );
                                Console.WriteLine($"Mensaje: #{i}, Publisher: {mqttHelper.ClientId} en el topic con id: {id_sensor}");
                                break;
                            case 2:
                                await mqttHelper.PublishAsync(

                                    topic: $"lab/device/{id_sensor}/Humedad",
                                    payload: JsonSerializer.Serialize(sensores_humedad, opciones),
                                    qos: MqttQualityOfServiceLevel.AtMostOnce
                                );
                                Console.WriteLine($"Mensaje: #{i}, Publisher: {mqttHelper.ClientId} en el topic con id: {id_sensor}");
                                break;
                            case 3:
                                await mqttHelper.PublishAsync(

                                    topic: $"lab/device/{id_sensor}/Temperatura",
                                    payload: JsonSerializer.Serialize(sensores_temp, opciones),
                                    qos: MqttQualityOfServiceLevel.AtMostOnce
                                );
                                Console.WriteLine($"Mensaje: #{i}, Publisher: {mqttHelper.ClientId} en el topic con id: {id_sensor}");
                                break;
                            // QOS 1
                            case 4:
                                await mqttHelper.PublishAsync(

                                    topic: $"lab/device/{id_sensor}/CO2",
                                    payload: JsonSerializer.Serialize(sensores_co2, opciones),
                                    qos: MqttQualityOfServiceLevel.AtLeastOnce
                                );
                                Console.WriteLine($"Mensaje: #{i}, Publisher: {mqttHelper.ClientId} en el topic con id: {id_sensor}");
                                break;
                            case 5:
                                await mqttHelper.PublishAsync(

                                    topic: $"lab/device/{id_sensor}/Humedad",
                                    payload: JsonSerializer.Serialize(sensores_humedad, opciones),
                                    qos: MqttQualityOfServiceLevel.AtLeastOnce
                                );
                                Console.WriteLine($"Mensaje: #{i}, Publisher: {mqttHelper.ClientId} en el topic con id: {id_sensor}");
                                break;
                            case 6:
                                await mqttHelper.PublishAsync(

                                    topic: $"lab/device/{id_sensor}/Temperatura",
                                    payload: JsonSerializer.Serialize(sensores_temp, opciones),
                                    qos: MqttQualityOfServiceLevel.AtLeastOnce
                                );
                                Console.WriteLine($"Mensaje: #{i}, Publisher: {mqttHelper.ClientId} en el topic con id: {id_sensor}");
                                break;
                            // QOS 2
                            case 7:
                                await mqttHelper.PublishAsync(

                                    topic: $"lab/device/{id_sensor}/CO2",
                                    payload: JsonSerializer.Serialize(sensores_co2, opciones),
                                    qos: MqttQualityOfServiceLevel.ExactlyOnce
                                );
                                Console.WriteLine($"Mensaje: #{i}, Publisher: {mqttHelper.ClientId} en el topic con id: {id_sensor}");
                                break;
                            case 8:
                                await mqttHelper.PublishAsync(

                                    topic: $"lab/device/{id_sensor}/Humedad",
                                    payload: JsonSerializer.Serialize(sensores_humedad, opciones),
                                    qos: MqttQualityOfServiceLevel.ExactlyOnce
                                );
                                Console.WriteLine($"Mensaje: #{i}, Publisher: {mqttHelper.ClientId} en el topic con id: {id_sensor}");
                                break;
                            case 9:
                                await mqttHelper.PublishAsync(

                                    topic: $"lab/device/{id_sensor}/Temperatura",
                                    payload: JsonSerializer.Serialize(sensores_temp, opciones),
                                    qos: MqttQualityOfServiceLevel.ExactlyOnce
                                );
                                Console.WriteLine($"Mensaje: #{i}, Publisher: {mqttHelper.ClientId} en el topic con id: {id_sensor}");
                                break;
                        }
                        break;
                }
                await Task.Delay(tiempo);
                // Evitar esperar después del último mensaje


            }
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
            // Importante: Siempre desconectar limpiamente antes de salir
            Console.WriteLine("\n\nDesconectando del broker...");
            await mqttHelper.DisconnectAsync();
            Console.WriteLine("Aplicación finalizada.");
        }

    }
    // ? para nullable
    static async Task<MqttClientHelper?> ComprobadorDeConexiones()
    {
        id_cliente = id_cliente + 1;
        // Configurar parámetros de conexión MQTT


        MqttSettings settings = new MqttSettings
        {
            BrokerHost = host,  // Mosquitto está corriendo en Docker en nuestra máquina
            BrokerPort = 1901,          // Puerto estándar MQTT
            ClientId = $"greenhouse-publisher-{id_cliente}",  // ID único para este cliente
            Username = id_cliente.ToString(),  // Usuario que acabamos de añadir a dynamic-security.json
            Password = "123456",  // Contraseña en texto plano
        };

        // Crear helper MQTT y conectar al broker
        MqttClientHelper mqttHelper = new(settings);
        await mqttHelper.ConnectAsync();

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