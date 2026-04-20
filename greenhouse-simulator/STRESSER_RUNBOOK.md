# Guía de ejecución del MQTT Stresser

Este documento resume cómo ejecutar `Greenhouse.Sensors` según el entorno donde corra el proceso.

## Resumen rápido

- Si ejecutas el binario desde Windows, puedes usar `MQTT_HOST=localhost` y `MQTT_PORT=21900`.
- Si ejecutas el stresser dentro de un contenedor Podman, `localhost` ya no apunta al host de Windows.
- Para `podman run` contra el laboratorio `kind`, la ruta validada es `--network kind` con `MQTT_HOST=bhm-lab-control-plane` y `MQTT_PORT=31900`.
- El modo recomendado del stresser es `MQTT_AUTH_MODE=per-client`: cada dispositivo usa su usuario DynSec (`1..N`) con la contraseña común definida en `MQTT_CLIENT_PASSWORD`.
- `MQTT_AUTH_MODE=shared` queda solo como modo alternativo para pruebas puntuales con un único usuario MQTT.

## Prerrequisitos

1. El laboratorio `kind` debe estar arriba y sano.
2. El servicio `mosquitto` debe seguir expuesto en el `NodePort` `31900`.
3. Las credenciales MQTT activas del laboratorio deben ser válidas para el stresser.

Comprobaciones útiles desde la raíz del workspace:

```powershell
./deploy.ps1 -Action status -Runtime kind
kubectl --context kind-bhm-lab -n bhm-lab get svc mosquitto -o jsonpath='{range .spec.ports[*]}{.name}:{.port}->{.nodePort} {end}'
```

La salida esperada para MQTT TCP es `mqtt:1900->31900`.

## Opción 1: ejecutar desde Windows

Usa esta opción si quieres aprovechar el `kubectl port-forward` ya publicado en el host.

Archivo de entorno recomendado: `mqtt-stresser.env`

Valores esperados:

```env
MQTT_HOST=localhost
MQTT_PORT=21900
MQTT_AUTH_MODE=per-client
MQTT_CLIENT_PASSWORD=123456
```

Pasos:

```powershell
Set-Location greenhouse-simulator/src/Greenhouse.Sensors

dotnet publish -c Release -o publish

dotnet .\publish\Greenhouse.Sensors.dll
```

## Opción 2: ejecutar en contenedor Podman contra `kind`

Usa esta opción si quieres correr el stresser como contenedor.

Archivo de entorno recomendado: `mqtt-stresser.kind.env`

Valores validados:

```env
MQTT_HOST=bhm-lab-control-plane
MQTT_PORT=31900
MQTT_AUTH_MODE=per-client
MQTT_CLIENT_PASSWORD=123456
```

Pasos:

```powershell
Set-Location greenhouse-simulator/src/Greenhouse.Sensors

dotnet publish -c Release -o publish

podman build -t mqtt-stresser .

podman run --rm --network kind --env-file mqtt-stresser.kind.env mqtt-stresser
```

## Requisito de credenciales DynSec por cliente

En el flujo actual del simulador, los clientes MQTT usan los usuarios DynSec `1..N` y la contraseña común `123456` salvo que fuerces `MQTT_AUTH_MODE=shared`.

Si el broker responde `NotAuthorized`, la validación correcta ya no es revisar `bunker/bunker`, sino confirmar que:

1. Existen en DynSec los usuarios `1..N` que vas a simular.
2. Esos usuarios siguen teniendo como contraseña `123456`.
3. Los roles ACL permiten `publish/subscribe` sobre `lab/device/#`.

## Modo alternativo con usuario compartido

Si necesitas volver temporalmente a un único usuario MQTT compartido, puedes activar el modo explícito `shared`:

```powershell
podman run --rm --network kind --env-file mqtt-stresser.kind.env `
	-e MQTT_AUTH_MODE=shared `
	-e MQTT_USER=admin `
	-e MQTT_PASS='=O6gWpGgyAu7YCCEB8k8' `
	mqtt-stresser
```

Ese modo ya no es el baseline recomendado para las pruebas del simulador.

## Provisionar el usuario `bunker` en el laboratorio actual

Si quieres mantener una vía rápida de conectividad con usuario compartido, puedes crear `bunker`, pero ya no es requisito para la carga principal del simulador.

Comandos validados desde la raíz del workspace:

```powershell
$apiKey = (Get-Content .env.dev | Select-String '^API_KEY=' | Select-Object -First 1).ToString() -replace '^API_KEY=',''

$headers = @{
	'X-API-Key' = $apiKey
	'Content-Type' = 'application/json'
}

Invoke-RestMethod -Uri 'http://localhost:22000/api/dynsec/clients' `
	-Headers $headers `
	-Method Post `
	-Body '{"username":"bunker","password":"bunker"}'

Invoke-RestMethod -Uri 'http://localhost:22000/api/dynsec/clients/bunker/roles' `
	-Headers $headers `
	-Method Post `
	-Body '{"role_name":"subscribe-and-publish","priority":1}'
```

Comprobación opcional:

```powershell
Invoke-RestMethod -Uri 'http://localhost:22000/api/dynsec/clients/bunker/status' -Headers @{ 'X-API-Key' = $apiKey }
```

El estado esperado es `status=applied`, `driftDetected=false` y el role `subscribe-and-publish` presente en `desired/applied/observed`.

## Alternativa rápida con credenciales MQTT ya activas

Si no quieres usar los usuarios DynSec `1..N`, puedes reutilizar las credenciales MQTT del entorno activo en `MQTT_AUTH_MODE=shared`:

```powershell
podman run --rm --network kind --env-file mqtt-stresser.kind.env `
	-e MQTT_AUTH_MODE=shared `
	-e MQTT_USER=admin `
	-e MQTT_PASS='=O6gWpGgyAu7YCCEB8k8' `
	mqtt-stresser
```

Esta opción es útil para validar conectividad, pero para la simulación real de múltiples dispositivos conviene mantener `MQTT_AUTH_MODE=per-client`.

## Por qué `localhost:21900` falla dentro del contenedor

Cuando ejecutas `podman run`, `localhost` apunta al propio contenedor, no al host de Windows.

En este entorno:

- `localhost:21900` funciona desde Windows porque ahí vive el `kubectl port-forward`.
- Un contenedor Podman externo no entra por ese `port-forward` del host.
- Un contenedor unido a `--network kind` sí puede llegar al `NodePort` del nodo `kind`, por eso funciona `bhm-lab-control-plane:31900`.

## Prueba de conectividad desde contenedor

Si quieres validar la red antes de lanzar el stresser:

```powershell
podman run --rm --network kind docker.io/library/busybox sh -c "nc -zvw3 bhm-lab-control-plane 31900"
```

Si responde correctamente, la ruta de red del contenedor al broker está bien.

## Diagnóstico rápido si vuelve a fallar

1. Confirma que el laboratorio sigue arriba con `./deploy.ps1 -Action status -Runtime kind`.
2. Confirma el `NodePort` real de `mosquitto` con `kubectl ... get svc mosquitto ...`.
3. Si ejecutas en contenedor, no uses `MQTT_HOST=localhost`.
4. Si ejecutas desde Windows, no uses `MQTT_PORT=31900`; usa `21900`.
5. Si el error cambia de conectividad a autorización, revisa primero si el contenedor está en `MQTT_AUTH_MODE=per-client` o `shared`.
6. En `per-client`, verifica provisioning DynSec de `1..N` y contraseña `123456`.
7. En `shared`, verifica `MQTT_USER` y `MQTT_PASS`.

## Notas del programa

- El stresser usa `MQTT_AUTH_MODE=per-client` por defecto y solo toma `MQTT_USER/MQTT_PASS` cuando `MQTT_AUTH_MODE=shared`.
- La contraseña de los usuarios DynSec `1..N` se controla con `MQTT_CLIENT_PASSWORD`.
- El proceso ya no queda en un loop infinito al terminar; sale cuando completa la carga.
- Si arrancas el contenedor con `MQTT_HOST=localhost`, el programa mostrará una advertencia explícita.
