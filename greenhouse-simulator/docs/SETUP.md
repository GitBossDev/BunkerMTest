# Guía de Setup - Entorno de Desarrollo .NET

## Requisitos del Sistema

- **Sistema Operativo**: Windows 10/11, macOS, o Linux
- **RAM**: Mínimo 4GB (recomendado 8GB+)
- **Espacio en disco**: ~2GB para .NET SDK + herramientas

---

## 1. Instalación de .NET SDK 8

### Windows

**Opción A: Descarga directa**
1. Visitar: https://dotnet.microsoft.com/download/dotnet/8.0
2. Descargar "SDK x64" para Windows
3. Ejecutar el instalador (.exe)
4. Seguir el asistente de instalación

**Opción B: Usando winget (recomendado)**
```powershell
winget install Microsoft.DotNet.SDK.8
```

### Verificar instalación

Abrir una terminal nueva (PowerShell o CMD) y ejecutar:
```bash
dotnet --version
```

Debería mostrar algo como: `8.0.xxx`

Para ver información completa:
```bash
dotnet --info
```

---

## 2. Editor de Código

### Opción A: Visual Studio Code (Recomendado para este proyecto)

**Instalación:**
1. Descargar desde: https://code.visualstudio.com/
2. Instalar normalmente

**Extensiones requeridas:**

Abrir VS Code y presionar `Ctrl+Shift+X`, luego instalar:

1. **C# Dev Kit** (Microsoft)
   - ID: `ms-dotnettools.csdevkit`
   - Incluye IntelliSense, debugging, etc.

2. **C#** (Microsoft)
   - ID: `ms-dotnettools.csharp`
   - Soporte para C# y .NET

**Extensiones opcionales útiles:**
- **Docker** - Para trabajar con contenedores
- **GitLens** - Mejor integración con Git
- **Error Lens** - Muestra errores inline

### Opción B: Visual Studio 2022 Community (Más pesado pero completo)

**Solo si prefieres un IDE completo:**
1. Descargar desde: https://visualstudio.microsoft.com/vs/community/
2. Durante instalación, seleccionar workload: "ASP.NET and web development"

---

## 3. Docker Desktop

**Instalación:**
1. Descargar desde: https://www.docker.com/products/docker-desktop
2. Instalar y reiniciar el sistema
3. Verificar instalación:
   ```bash
   docker --version
   docker-compose --version
   ```

---

## Comparativa Java vs C#

### Similitudes Generales

Ambos son lenguajes orientados a objetos con sintaxis similar. Si sabes Java, C# te resultará familiar.

### Gestión de Dependencias

| Java | C# |
|------|-----|
| Maven (`pom.xml`) | NuGet (`.csproj`) |
| Gradle (`build.gradle`) | NuGet (`.csproj`) |
| `mvn install` | `dotnet restore` |
| `mvn clean package` | `dotnet build` |
| `mvn exec:java` | `dotnet run` |

**Ejemplo de archivo de proyecto:**

```xml
<!-- Archivo .csproj (similar a pom.xml) -->
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="MQTTnet" Version="4.3.3" />
  </ItemGroup>
</Project>
```

### Organización de Código

| Concepto | Java | C# |
|----------|------|-----|
| Agrupación | Package | Namespace |
| Declaración | `package com.example;` | `namespace Company.Example;` |
| Importación | `import java.util.List;` | `using System.Collections.Generic;` |
| Ubicación | Debe coincidir con carpetas | No necesita coincidir |

### Sintaxis Básica

#### Declaración de Clases

**Java:**
```java
package com.greenhouse.sensors;

public class TemperatureSensor {
    private String sensorId;
    private double currentValue;
    
    public TemperatureSensor(String sensorId) {
        this.sensorId = sensorId;
        this.currentValue = 20.0;
    }
    
    public String getSensorId() {
        return sensorId;
    }
    
    public void setSensorId(String sensorId) {
        this.sensorId = sensorId;
    }
}
```

**C#:**
```csharp
namespace Greenhouse.Sensors;

public class TemperatureSensor
{
    private string _sensorId;
    private double _currentValue;
    
    // Constructor
    public TemperatureSensor(string sensorId)
    {
        _sensorId = sensorId;
        _currentValue = 20.0;
    }
    
    // Properties (getters/setters automáticos)
    public string SensorId { get; set; }
    
    // Property con lógica personalizada
    public double CurrentValue
    {
        get => _currentValue;
        set => _currentValue = value;
    }
}
```

**Nota importante:** C# usa **PascalCase** para métodos y propiedades públicas (muy diferente a Java que usa camelCase).

### Convenciones de Nombres

| Elemento | Java | C# |
|----------|------|-----|
| Clases | `PascalCase` | `PascalCase` |
| Métodos públicos | `camelCase` | `PascalCase` |
| Variables privadas | `camelCase` | `_camelCase` o `camelCase` |
| Constantes | `UPPER_CASE` | `PascalCase` o `UPPER_CASE` |
| Interfaces | `IPascalCase` | `IPascalCase` |
| Parámetros | `camelCase` | `camelCase` |

### Tipos de Datos

| Java | C# | Notas |
|------|-----|-------|
| `int` | `int` | Idéntico (32 bits) |
| `long` | `long` | Idéntico (64 bits) |
| `float` | `float` | Idéntico (32 bits) |
| `double` | `double` | Idéntico (64 bits) |
| `boolean` | `bool` | Diferente nombre |
| `String` | `string` | Keyword en C# (minúscula) |
| `Integer` | `int?` | Nullable en C# con `?` |
| `List<T>` | `List<T>` | Casi idéntico |
| `Map<K,V>` | `Dictionary<K,V>` | Equivalente |

### Null Safety

**Java (moderno):**
```java
Optional<String> optional = Optional.ofNullable(getName());
String name = optional.orElse("default");
```

**C#:**
```csharp
// Nullable reference types (C# 8+)
string? nullableString = GetName();
string name = nullableString ?? "default";

// Null-conditional operator
int? length = nullableString?.Length;
```

### Colecciones y LINQ vs Streams

**Java Streams:**
```java
List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5);
List<Integer> evenDoubled = numbers.stream()
    .filter(n -> n % 2 == 0)
    .map(n -> n * 2)
    .collect(Collectors.toList());
```

**C# LINQ:**
```csharp
List<int> numbers = new List<int> { 1, 2, 3, 4, 5 };
List<int> evenDoubled = numbers
    .Where(n => n % 2 == 0)
    .Select(n => n * 2)
    .ToList();

// Sintaxis alternativa (query syntax)
var evenDoubled2 = (from n in numbers
                    where n % 2 == 0
                    select n * 2).ToList();
```

### Programación Asíncrona

| Java | C# |
|------|-----|
| `CompletableFuture<T>` | `Task<T>` |
| `.thenApply()` | `await` |
| `.exceptionally()` | `try-catch` con async |

**Java:**
```java
public CompletableFuture<String> fetchDataAsync() {
    return CompletableFuture.supplyAsync(() -> {
        // Operación larga
        return "data";
    });
}

fetchDataAsync()
    .thenAccept(data -> System.out.println(data))
    .exceptionally(ex -> {
        ex.printStackTrace();
        return null;
    });
```

**C#:**
```csharp
public async Task<string> FetchDataAsync()
{
    // Operación larga
    await Task.Delay(1000);
    return "data";
}

// Uso
try
{
    string data = await FetchDataAsync();
    Console.WriteLine(data);
}
catch (Exception ex)
{
    Console.WriteLine(ex.Message);
}
```

**C# es mucho más limpio y legible para async/await.**

### Manejo de Excepciones

Es casi idéntico, solo cambian algunas clases:

**Java:**
```java
try {
    riskyOperation();
} catch (IOException e) {
    e.printStackTrace();
} finally {
    cleanup();
}
```

**C#:**
```csharp
try
{
    RiskyOperation();
}
catch (IOException ex)
{
    Console.WriteLine(ex.Message);
}
finally
{
    Cleanup();
}
```

### Interfaces

**Java:**
```java
public interface ISensor {
    double readValue();
    String getSensorType();
}

public class TemperatureSensor implements ISensor {
    @Override
    public double readValue() {
        return 22.5;
    }
    
    @Override
    public String getSensorType() {
        return "temperature";
    }
}
```

**C#:**
```csharp
public interface ISensor
{
    double ReadValue();
    string GetSensorType();
}

public class TemperatureSensor : ISensor
{
    public double ReadValue()
    {
        return 22.5;
    }
    
    public string GetSensorType()
    {
        return "temperature";
    }
}
```

### Properties vs Getters/Setters

Esta es una de las mayores diferencias:

**Java (verbose):**
```java
public class Sensor {
    private String id;
    private double value;
    
    public String getId() {
        return id;
    }
    
    public void setId(String id) {
        this.id = id;
    }
    
    public double getValue() {
        return value;
    }
    
    public void setValue(double value) {
        this.value = value;
    }
}
```

**C# (conciso):**
```csharp
public class Sensor
{
    // Auto-implemented properties
    public string Id { get; set; }
    public double Value { get; set; }
    
    // Property de solo lectura
    public string Type { get; }
    
    // Property con lógica
    private double _temperature;
    public double Temperature
    {
        get => _temperature;
        set
        {
            // Validación al asignar
            if (value < -50 || value > 50)
                throw new ArgumentException("Temperatura fuera de rango");
            _temperature = value;
        }
    }
}

// Uso
var sensor = new Sensor
{
    Id = "temp-01",     // Usa el setter
    Value = 22.5
};
Console.WriteLine(sensor.Id);  // Usa el getter
```

### Annotations vs Attributes

**Java:**
```java
@Override
@Deprecated
public void oldMethod() { }
```

**C#:**
```csharp
[Obsolete]
public override void OldMethod() { }
```

---

## Comandos Esenciales de .NET CLI

### Gestión de Soluciones

```bash
# Crear una solución (equivalente a proyecto Maven multi-módulo)
dotnet new sln -n InvernaderoMQTT

# Agregar proyecto a solución
dotnet sln add src/Greenhouse.Sensors/Greenhouse.Sensors.csproj

# Listar proyectos en solución
dotnet sln list
```

### Crear Proyectos

```bash
# Proyecto de consola
dotnet new console -n MiProyecto -o src/MiProyecto

# Proyecto de librería de clases
dotnet new classlib -n MiLibreria -o src/MiLibreria

# Proyecto web API
dotnet new webapi -n MiApi -o src/MiApi

# Proyecto Blazor Server
dotnet new blazorserver -n MiDashboard -o src/MiDashboard

# Ver todas las plantillas disponibles
dotnet new list
```

### Gestión de Dependencias

```bash
# Instalar paquete NuGet
dotnet add package MQTTnet

# Instalar versión específica
dotnet add package MQTTnet --version 4.3.3

# Listar paquetes instalados
dotnet list package

# Actualizar paquetes
dotnet restore
```

### Referencias entre Proyectos

```bash
# Agregar referencia de un proyecto a otro
dotnet add src/Greenhouse.Sensors reference src/Greenhouse.Shared

# Remover referencia
dotnet remove src/Greenhouse.Sensors reference src/Greenhouse.Shared
```

### Compilación y Ejecución

```bash
# Restaurar dependencias
dotnet restore

# Compilar (debug)
dotnet build

# Compilar (release)
dotnet build -c Release

# Ejecutar proyecto
dotnet run --project src/Greenhouse.Sensors

# Ejecutar con argumentos
dotnet run --project src/Greenhouse.Sensors -- arg1 arg2

# Limpiar compilaciones
dotnet clean
```

### Publicación

```bash
# Publicar para distribución
dotnet publish -c Release -o ./publish

# Publicar como ejecutable único (self-contained)
dotnet publish -c Release -r win-x64 --self-contained true
```

---

## Estructura de un Proyecto .NET

```
MiProyecto/
├── MiProyecto.csproj          # Archivo de proyecto (como pom.xml)
├── Program.cs                  # Punto de entrada
├── Models/                     # Clases de modelo
│   └── Sensor.cs
├── Services/                   # Lógica de negocio
│   └── SensorService.cs
├── bin/                        # Compilados (como target/)
│   └── Debug/
│       └── net8.0/
└── obj/                        # Archivos temporales
```

**Importante:** `bin/` y `obj/` deben estar en `.gitignore` (equivalente a `target/` en Java).

---

## Atajos de Teclado Útiles en VS Code

| Acción | Windows | macOS |
|--------|---------|-------|
| Paleta de comandos | `Ctrl+Shift+P` | `Cmd+Shift+P` |
| Terminal integrada | `Ctrl+´` | `Ctrl+´` |
| Quick Fix | `Ctrl+.` | `Cmd+.` |
| Ir a definición | `F12` | `F12` |
| Renombrar símbolo | `F2` | `F2` |
| Buscar en archivos | `Ctrl+Shift+F` | `Cmd+Shift+F` |
| Comentar línea | `Ctrl+/` | `Cmd+/` |

---

## Configuración Recomendada para VS Code

Crear o editar `.vscode/settings.json` en el proyecto:

```json
{
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": true
  },
  "[csharp]": {
    "editor.defaultFormatter": "ms-dotnettools.csharp"
  },
  "dotnet.defaultSolution": "InvernaderoMQTT.sln"
}
```

---

## Conceptos Importantes de C#

### 1. var vs tipo explícito

```csharp
// Explícito (como Java)
string name = "sensor-01";
List<int> numbers = new List<int>();

// Inferido (tipo determinado en compile-time)
var name = "sensor-01";              // string
var numbers = new List<int>();       // List<int>
var sensor = new TemperatureSensor(); // TemperatureSensor
```

### 2. String Interpolation

```csharp
// Java
String message = "Sensor " + sensorId + " value: " + value;

// C# (mucho más limpio)
string message = $"Sensor {sensorId} value: {value}";
string formatted = $"Temperature: {temperature:F2}°C";  // Formato
```

### 3. Expresiones Lambda

Son muy similares a Java:

```csharp
// Java
list.stream().filter(x -> x > 0)

// C#
list.Where(x => x > 0)
```

### 4. Pattern Matching (C# es más potente)

```csharp
object obj = GetSomeObject();

// Switch expression (C# 8+)
string result = obj switch
{
    int i => $"Integer: {i}",
    string s => $"String: {s}",
    null => "Null value",
    _ => "Unknown type"
};
```

### 5. Records (C# 9+)

Para clases de datos inmutables:

```csharp
// Declaración super concisa
public record SensorReading(string SensorId, double Value, DateTime Timestamp);

// Uso
var reading = new SensorReading("temp-01", 22.5, DateTime.Now);
Console.WriteLine(reading.SensorId);  // temp-01

// Inmutabilidad con 'with'
var newReading = reading with { Value = 23.0 };
```

---

## Debugging

### En VS Code:

1. Colocar breakpoint: Click en el margen izquierdo (aparece punto rojo)
2. Presionar `F5` para iniciar debugging
3. Controles:
   - `F5`: Continue
   - `F10`: Step Over
   - `F11`: Step Into
   - `Shift+F11`: Step Out
   - `Shift+F5`: Stop

### Logging básico:

```csharp
// Simple (para desarrollo)
Console.WriteLine($"Sensor {sensorId} connected");

// Con colores
Console.ForegroundColor = ConsoleColor.Green;
Console.WriteLine("Success!");
Console.ResetColor();
```

---

## Git Ignore para .NET

Crear `.gitignore`:

```gitignore
# Build results
[Bb]in/
[Oo]bj/
[Ll]og/
[Ll]ogs/

# Visual Studio
.vs/
*.suo
*.user
*.userosscache
*.sln.docstates

# VS Code
.vscode/*
!.vscode/settings.json
!.vscode/tasks.json
!.vscode/launch.json

# Rider
.idea/

# User-specific files
*.rsuser
*.suo
*.user

# Build results
[Dd]ebug/
[Rr]elease/
x64/
x86/
[Aa][Rr][Mm]/
[Aa][Rr][Mm]64/
```

---

## Próximos Pasos

Una vez completada esta configuración:

1. Verificar que `dotnet --version` funciona
2. Verificar que `docker --version` funciona
3. Abrir VS Code en la carpeta del proyecto
4. Proceder a crear la estructura de proyectos

---

## Recursos Adicionales

- **Documentación oficial .NET**: https://docs.microsoft.com/dotnet/
- **C# Programming Guide**: https://docs.microsoft.com/dotnet/csharp/
- **MQTTnet Documentation**: https://github.com/dotnet/MQTTnet
- **Learn C# (para desarrolladores Java)**: https://docs.microsoft.com/shows/csharp-101/

---

## Troubleshooting Común

### "dotnet command not found"
- Reiniciar terminal después de instalar .NET
- Verificar que .NET esté en PATH
- En Windows: Cerrar y abrir terminal como administrador

### Error de SSL/HTTPS en desarrollo
```bash
dotnet dev-certs https --trust
```

### Restauración de paquetes falla
```bash
dotnet nuget locals all --clear
dotnet restore --force
```

### VS Code no detecta .NET
- Instalar extensión "C# Dev Kit"
- Recargar ventana: `Ctrl+Shift+P` → "Reload Window"
