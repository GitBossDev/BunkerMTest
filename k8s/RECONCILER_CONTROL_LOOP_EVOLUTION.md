# Evolucion del Reconciliador hacia Control Loop u Operador

Este documento verifica si el reconciliador actual puede evolucionar a un patron mas nativo de Kubernetes sin forzar una migracion prematura que rompa el ownership broker-local.

## Estado actual verificado

- el reconciliador ya no vive en el pod web; corre como sidecar broker-owned dentro de `StatefulSet/mosquitto`
- el trabajo pendiente se obtiene desde PostgreSQL a traves de `broker_desired_state`
- el daemon ya es idempotente y orientado a loop: `python -m services.broker_reconcile_daemon --interval N`
- el mismo proceso ya soporta ejecucion one-shot con `--once`, lo que deja abierta una traduccion futura a `Job` o reconciliacion invocada por controlador
- el pod web ya no necesita acceso de escritura al filesystem del broker

## Lo que todavia impide un operador remoto puro

- la aplicacion real sigue necesitando `/var/lib/mosquitto` y `/etc/mosquitto`
- la semantica de rollback sigue apoyandose en backups broker-locales
- el settlement final de DynSec y `mosquitto_passwd` aun termina en artefactos del pod broker-owned

Por eso, hoy el reconciliador si puede evolucionar a un control loop mas formal, pero no conviene separarlo todavia como `Deployment` remoto ni como operador que escriba PVCs compartidos de forma artificial.

## Ruta de evolucion recomendada

### Etapa 1: sidecar control loop broker-owned

Mantener el reconciliador donde esta mientras siga existiendo coupling al filesystem local del broker. Esta etapa ya esta implementada y validada.

### Etapa 2: control loop con frontera broker-local explicita

Extraer la mutacion broker-local a una interfaz minima broker-owned. Las opciones razonables son:

- comando broker-local invocable desde `exec`
- endpoint interno expuesto solo dentro del pod broker-owned
- helper dedicado que tome payload reconciliado y devuelva resultado auditable

El objetivo de esta etapa es que el loop de decision deje de depender directamente de rutas locales, aunque la aplicacion final siga ocurriendo en el pod broker-owned.

### Etapa 3: controlador o Job coordinado por Kubernetes

Una vez desaparezca la escritura directa del loop sobre el filesystem broker-local, el reconciliador puede salir del sidecar y tomar una de estas formas:

- `Deployment` controlador con polling a PostgreSQL
- `Job` one-shot para reparacion o replay de scopes concretos
- operador posterior si el dominio del broker merece CRDs propios

## Criterio tecnico para considerar viable la evolucion

La evolucion se considera viable porque ya existen estas piezas:

- fuente durable y auditable de desired state
- loop periodico desacoplado del router HTTP
- ejecucion por scope
- modo `--once` para una reconciliacion puntual
- pod web sin ownership de escritura broker-facing

La evolucion no se considera lista para separacion remota total mientras falten estas piezas:

- writer broker-local encapsulado detras de una frontera mas estable
- rotacion nativa de secretos broker-facing sin seed inicial
- reduccion adicional del coupling a archivos locales del broker

## Verificacion operativa recomendada en el laboratorio

La comprobacion minima para Fase 8 es ejecutar el daemon actual en modo `--once` dentro del contenedor `reconciler` del laboratorio y confirmar que el ciclo termina sin errores. Eso valida que el loop actual ya tiene semantica util tanto para sidecar continuo como para reconciliacion one-shot.