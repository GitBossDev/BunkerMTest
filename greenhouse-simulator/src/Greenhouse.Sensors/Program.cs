using Greenhouse.Shared.Configuration;
using Greenhouse.Shared.Helpers;
using MQTTnet.Protocol;
using System.Threading;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Diagnostics;
using System.IO;

class Programa
{
    static int id_cliente = 0;
    static int cuenta_errores= 0;
    static int elige=2;

    static async Task Main()
    {

        Console.WriteLine("==============================================");
        Console.WriteLine("  GREENHOUSE MQTT - PUBLISHERS");
        Console.WriteLine("==============================================\n");


        Console.WriteLine("¿En que unidad de tiempo quieres enviar los mensajes? (horas:1, minutos:2, segundos:3)");
        int tiempo = int.Parse(Console.ReadLine());
        switch ((int)tiempo)
        {
            case 1:
                Console.WriteLine("¿Cada cuantas horas quieres enviar el mensaje?");
                tiempo = int.Parse(Console.ReadLine()) * 3600000;
                break;
            case 2:
                Console.WriteLine("¿Cada cuantos minutos quieres enviar el mensaje?");
                tiempo = int.Parse(Console.ReadLine()) * 60000;
                break;
            case 3:
                Console.WriteLine("¿Cada cuantos segundos quieres enviar el mensaje?");
                tiempo = int.Parse(Console.ReadLine()) * 1000;
                break;
            default:
                Console.WriteLine("Por defecto, ¿Cada cuantos segundos quieres enviar el mensaje?");
                tiempo = int.Parse(Console.ReadLine()) * 1000;
                break;
        }

        Console.WriteLine("\n==============================================");
        Console.WriteLine("PUBLICACIÓN DE MENSAJES");
        Console.WriteLine("==============================================\n");

        Console.WriteLine("Dime el número de clientes que publicarán mensajes:");
        int numClientes = int.Parse(Console.ReadLine());

        var tasks = new List<Task>();

        while (numClientes > 0)
        {
            numClientes--;
            // Lanzar la función asíncrona en un task en lugar de usar Thread directamente
            tasks.Add(Task.Run(() => MyFunctionAsync(tiempo)));

            // tiempo entre comienzo de la task de cada cliente
            await Task.Delay(500);
            
        }

        // Esperar a que todos los publishers terminen su ciclo de mensajes
        await Task.WhenAll(tasks);

        Console.WriteLine($"\nTodos los publishers han terminado. Total de errores: {cuenta_errores}");
    }

    static async Task MyFunctionAsync(int tiempo)
    {

        MqttClientHelper mqttHelper = await ComprobadorDeConexiones();


        try
        {
            int messageCount = Random.Shared.Next(5, 10);
            int id_sensor = Random.Shared.Next(100000000, 999999999);

            for (int i = 0; i < messageCount; i++)
            {
                var sensores_co2 = new List<Sensor_c02> { new Sensor_c02 { Id = id_sensor, Nivel_c02 = Random.Shared.Next(300, 1000) } };
                var sensores_humedad = new List<Sensor_humedad> { new Sensor_humedad { Id = id_sensor, Humedad = Random.Shared.Next(90, 100) } };
                var sensores_temp = new List<Sensor_Temp> { new Sensor_Temp { Id = id_sensor, Temperatura = Random.Shared.Next(15, 35) } };
                // Opciones para formatear el JSON
                var opciones = new JsonSerializerOptions { WriteIndented = true };

                switch (Random.Shared.Next(1, 4))
                {
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
                }

                if (messageCount % 2 == 0)
                {
                    await Task.Delay(tiempo);
                } // Evitar esperar después del último mensaje


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
        
        //var userCreds = MqttClientHelper.CreateDynSecPasswordHash("123456");
        //AddOrUpdateDynSecClient(id_cliente.ToString(), "Usuario de ejemplo", "admin", userCreds);

        MqttSettings settings = new MqttSettings
        {
            BrokerHost = "localhost",  // Mosquitto está corriendo en Docker en nuestra máquina
            BrokerPort = 1901,          // Puerto estándar MQTT
            ClientId = $"greenhouse-publisher-{id_cliente}",  // ID único para este cliente
            Username = "bunker",  // Usuario que acabamos de añadir a dynamic-security.json
            Password = "bunker"
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
*/
    static void AddOrUpdateDynSecClient(string username, string textname, string role, (string PasswordBase64, string SaltBase64, int Iterations) creds)
    {
        // AppContext.BaseDirectory apunta al directorio bin (por ejemplo ...\bin\Debug\net10.0\).
        // Subimos hasta la raíz del repositorio y accedemos a backend/mosquitto/dynsec.
        string dynsecPath = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "..", "backend", "mosquitto", "dynsec", "dynamic-security.json"));

        Console.WriteLine($"Usando dynamic-security.json: {dynsecPath}");

        string dynsecDir = Path.GetDirectoryName(dynsecPath)!;
        if (!Directory.Exists(dynsecDir))
        {
            Directory.CreateDirectory(dynsecDir);
        }

        JsonNode root;

        if (File.Exists(dynsecPath))
        {
            string json = File.ReadAllText(dynsecPath);
            root = JsonNode.Parse(json) ?? new JsonObject();
        }
        else
        {
            root = new JsonObject();
        }

        if (root["clients"] == null)
        {
            root["clients"] = new JsonArray();
        }

        var clients = root["clients"]!.AsArray();

        JsonObject? existing = null;
        foreach (var item in clients)
        {
            if (item is JsonObject obj && string.Equals(obj["username"]?.GetValue<string>(), username, StringComparison.OrdinalIgnoreCase))
            {
                existing = obj;
                break;
            }
        }

        if (existing != null)
        {
            existing["textname"] = textname;
            existing["password"] = creds.PasswordBase64;
            existing["salt"] = creds.SaltBase64;
            existing["iterations"] = creds.Iterations;

            if (existing["roles"] == null)
            {
                existing["roles"] = new JsonArray();
            }
            var rolesArray = existing["roles"]!.AsArray();
            bool hasRole = false;
            foreach (var roleItem in rolesArray)
            {
                if (roleItem is JsonObject roleObj && string.Equals(roleObj["rolename"]?.GetValue<string>(), role, StringComparison.OrdinalIgnoreCase))
                {
                    hasRole = true;
                    break;
                }
            }
            if (!hasRole)
            {
                rolesArray.Add(new JsonObject { ["rolename"] = role });
            }
        }
        else
        {
            var newClient = new JsonObject
            {
                ["username"] = username,
                ["textname"] = textname,
                ["roles"] = new JsonArray(new JsonObject { ["rolename"] = role }),
                ["password"] = "whKZVT0mN53xaOppC4UTu7rZjny8qnAHXvllD2/O1HZB4aAgQaavucQU0l7kpzBbADv7bakea3yKndZbxHhlUA==",
                ["salt"] = "Q6wkX9DTyPc6Y8Nf",
                ["iterations"] = creds.Iterations
            };
            clients.Add(newClient);
        }

        if (root["roles"] == null)
        {
            root["roles"] = new JsonArray();
        }

        bool adminRoleExists = false;
        foreach (var roleItem in root["roles"]!.AsArray())
        {
            if (roleItem is JsonObject roleObj && string.Equals(roleObj["rolename"]?.GetValue<string>(), role, StringComparison.OrdinalIgnoreCase))
            {
                adminRoleExists = true;
                break;
            }
        }

        if (!adminRoleExists)
        {
            root["roles"]!.AsArray().Add(new JsonObject
            {
                ["rolename"] = role,
                ["acls"] = new JsonArray
                {
                    new JsonObject { ["acltype"] = "publishClientSend", ["topic"] = "$CONTROL/dynamic-security/#", ["priority"] = 0, ["allow"] = true },
                    new JsonObject { ["acltype"] = "publishClientReceive", ["topic"] = "$CONTROL/dynamic-security/#", ["priority"] = 0, ["allow"] = true },
                    new JsonObject { ["acltype"] = "publishClientReceive", ["topic"] = "$SYS/#", ["priority"] = 0, ["allow"] = true },
                    new JsonObject { ["acltype"] = "publishClientReceive", ["topic"] = "#", ["priority"] = 0, ["allow"] = true },
                    new JsonObject { ["acltype"] = "subscribePattern", ["topic"] = "#", ["priority"] = 0, ["allow"] = true },
                    new JsonObject { ["acltype"] = "subscribePattern", ["topic"] = "$CONTROL/dynamic-security/#", ["priority"] = 0, ["allow"] = true },
                    new JsonObject { ["acltype"] = "subscribePattern", ["topic"] = "$SYS/#", ["priority"] = 0, ["allow"] = true },
                    new JsonObject { ["acltype"] = "unsubscribePattern", ["topic"] = "#", ["priority"] = 0, ["allow"] = true }
                }
            });
        }

        if (root["defaultACLAccess"] == null)
        {
            root["defaultACLAccess"] = new JsonObject
            {
                ["publishClientSend"] = true,
                ["publishClientReceive"] = true,
                ["subscribe"] = true,
                ["unsubscribe"] = true
            };
        }

        var options = new JsonSerializerOptions { WriteIndented = true };
        File.WriteAllText(dynsecPath, root.ToJsonString(options));

        Console.WriteLine("dynamic-security.json actualizado con usuario cliente: "+id_cliente);
    }
}

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


//clase sensor genérica para tene run json que recoger
