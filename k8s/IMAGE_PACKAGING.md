# Empaquetado e Imagenes del Laboratorio Kubernetes

Este documento cierra el trabajo pendiente de Fase 8 sobre empaquetado del laboratorio `kind` y deja un lineamiento concreto para abandonar `latest` sin romper el baseline local. El baseline persistente actual ya no incluye el antiguo simulador de planta de agua.

## Estado actual

- las imagenes base del laboratorio `kind` son `bunkermtest-bunkerm` y `bunkermtest-mosquitto`
- el laboratorio `kind` ya no requiere editar manifests para cambiar de tag
- `deploy.ps1` y `k8s/scripts/bootstrap-kind.ps1` aceptan un tag explicito mediante `-ImageTag`
- `k8s/base/kustomization.yaml` fija los nombres de imagen y permite sobrescribir el tag con Kustomize antes de aplicar

## Uso recomendado en laboratorio

Baseline por defecto:

```powershell
./deploy.ps1 -Action build -Runtime kind
./deploy.ps1 -Action start -Runtime kind
```

Baseline con tag explicito de corte:

```powershell
./deploy.ps1 -Action build -Runtime kind -ImageTag phase8-lab
./deploy.ps1 -Action start -Runtime kind -ImageTag phase8-lab
```

Eso construye imagenes locales `bunkermtest-bunkerm:phase8-lab` y `bunkermtest-mosquitto:phase8-lab`, las carga en `kind` y aplica el laboratorio con manifests ya resueltos a `localhost/...:phase8-lab`.

## Convencion minima de tags

Mientras el laboratorio siga siendo local, el tag recomendado es uno de estos:

- `latest` para iteracion rapida local
- `phaseX-cutY` para hitos funcionales internos
- `dev-YYYYMMDD-SHORTSHA` para validaciones repetibles de un corte concreto

La regla importante no es el formato exacto, sino que el tag usado en build y start sea el mismo para que el runtime `kind` y la evidencia de pruebas apunten al mismo artefacto.

## Paso siguiente fuera del laboratorio

Cuando el despliegue deje de ser solo local, el siguiente corte debe ser:

1. publicar las mismas imagenes en un registry real
2. mantener tags inmutables por commit o release
3. reservar `latest` solo para desarrollo local
4. sustituir `imagePullPolicy: Never` por politica acorde al registry y al cluster objetivo

## Compatibilidad con la imagen del producto de transformacion

La coexistencia futura con la imagen del producto de transformacion de datos no debe reutilizar ni sobrescribir estas imagenes. El carril correcto sigue siendo:

- imagen separada
- `Deployment` o worker separado
- consumo por API, PostgreSQL o mensajeria futura

Eso evita mezclar ownership entre control-plane, broker-facing y transformacion de datos.