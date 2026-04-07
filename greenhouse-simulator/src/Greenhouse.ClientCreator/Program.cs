using Greenhouse.Shared.Configuration;
using Greenhouse.Shared.Helpers;
using MQTTnet.Protocol;
using System.Threading;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Diagnostics;
using System.IO;
using System.Numerics;


class Programa
{
    static int id_cliente = 0;
    static async Task Main(string[] args)
    {
        id_cliente = int.Parse(args[0]);
        for (int i = 1; i <= id_cliente; i++)
        {
            var userCreds = MqttClientHelper.CreateDynSecPasswordHash("123456");
            AddOrUpdateDynSecClient(i.ToString(), "Usuario de ejemplo", userCreds);
        }

        Console.WriteLine($"\nSe ha acabado el proceso de creación de {id_cliente} clientes en dynamic-security.json. Presiona Enter para salir.");
        Console.ReadLine();
        static void AddOrUpdateDynSecClient(string username, string textname, (string PasswordBase64, string SaltBase64, int Iterations) creds)
        {
            // AppContext.BaseDirectory apunta al directorio bin (por ejemplo ...\bin\Debug\net10.0\).
            // Subimos hasta la raíz del repositorio y accedemos a mosquitto/dynsec.
            string dynsecPath = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "mosquitto", "dynsec", "dynamic-security.json"));

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


            if (root["groups"] == null || root["groups"] is not JsonArray)
            {
                root["groups"] = new JsonArray();
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

            // Seleccionar aleatoriamente entre publish-only y subscribe-only
            string[] availableRoles = { "publish-only", "subscribe-only", "subscribe-and-publish" };
            string selectedRole = availableRoles[Random.Shared.Next(availableRoles.Length)];
            Console.WriteLine($"Rol seleccionado para cliente '{username}': {selectedRole}");

            if (existing == null)
            {
                var newClient = new JsonObject
                {
                    ["username"] = username,
                    ["textname"] = textname,
                    ["roles"] = new JsonArray(new JsonObject { ["rolename"] = selectedRole }),
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

            var rolesArray_root = root["roles"]!.AsArray();

            // Crear roles publish-only y subscribe-only si no existen
            CreateRoleIfNotExists(rolesArray_root, "publish-only", GetPublishOnlyAcls());
            CreateRoleIfNotExists(rolesArray_root, "subscribe-only", GetSubscribeOnlyAcls());
            CreateRoleIfNotExists(rolesArray_root, "subscribe-and-publish", GetSubscribeAndPublishAcls());

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

            Console.WriteLine($"dynamic-security.json actualizado con usuario cliente: {username} (rol: {selectedRole})");
        }

        /**
        * Crea un rol en la estructura de roles si no existe
        */
        static void CreateRoleIfNotExists(JsonArray rolesArray, string roleName, JsonArray acls)
        {
            bool roleExists = false;
            foreach (var roleItem in rolesArray)
            {
                if (roleItem is JsonObject roleObj && string.Equals(roleObj["rolename"]?.GetValue<string>(), roleName, StringComparison.OrdinalIgnoreCase))
                {
                    roleExists = true;
                    break;
                }
            }

            if (!roleExists)
            {
                rolesArray.Add(new JsonObject
                {
                    ["rolename"] = roleName,
                    ["acls"] = acls
                });
            }
        }

        /**
        * Retorna los ACLs para un cliente que solo puede publicar
        */
        static JsonArray GetSubscribeAndPublishAcls()
        {
            return new JsonArray
        {
            new JsonObject { ["acltype"] = "publishClientSend", ["topic"] = "lab/device/#", ["priority"] = 0, ["allow"] = true },
            new JsonObject { ["acltype"] = "unsubscribePattern", ["topic"] = "#", ["priority"] = 0, ["allow"] = true },
            new JsonObject { ["acltype"] = "subscribePattern", ["topic"] = "lab/device/#", ["priority"] = 0, ["allow"] = true },
        };
        }
        static JsonArray GetPublishOnlyAcls()
        {
            return new JsonArray
        {
            new JsonObject { ["acltype"] = "publishClientSend", ["topic"] = "lab/device/#", ["priority"] = 0, ["allow"] = true },
            new JsonObject { ["acltype"] = "unsubscribePattern", ["topic"] = "#", ["priority"] = 0, ["allow"] = true },
            new JsonObject { ["acltype"] = "subscribePattern", ["topic"] = "lab/device/#", ["priority"] = 0, ["allow"] = false },
        };
        }

        /**
        * Retorna los ACLs para un cliente que solo puede suscribirse
        */
        static JsonArray GetSubscribeOnlyAcls()
        {
            return new JsonArray
        {
            new JsonObject { ["acltype"] = "publishClientSend", ["topic"] = "lab/device/#", ["priority"] = 0, ["allow"] = false },
            new JsonObject { ["acltype"] = "subscribePattern", ["topic"] = "lab/device/#", ["priority"] = 0, ["allow"] = true },
        };
        }
    }
}

