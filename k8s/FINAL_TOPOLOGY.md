# Topologia Final Objetivo en Kubernetes

Este documento materializa el corte ejecutable de Fase 9 ya saneado: BHM deja de validarse solo como control-plane aislado y pasa a convivir en el laboratorio con sus workloads persistentes core, mientras que `greenhouse-simulator` queda como herramienta externa de carga MQTT fuera del baseline estable de `kind`.

## Workloads activos en el laboratorio final actual

| Dominio | Workload | Tipo Kubernetes | Ownership |
| --- | --- | --- | --- |
| Control-plane web | `bunkerm-platform` | `Deployment` | BHM |
| Broker MQTT | `mosquitto` | `StatefulSet` | broker-owned |
| Reconciliacion broker-facing | `reconciler` | sidecar en `StatefulSet/mosquitto` | broker-owned |
| Observabilidad broker-owned | `observability` | sidecar en `StatefulSet/mosquitto` | broker-owned |
| Persistencia control-plane | `postgres` | `StatefulSet` | BHM |
| Delivery de alertas | `bhm-alert-delivery` | `Deployment` | BHM |

## Contrato de integracion del simulador externo

- no comparte volumen con el broker
- no entra en el pod `mosquitto`
- no entra en el pod web `bunkerm-platform`
- se integra solo por MQTT y configuracion propia
- sus secretos y parametros de conexion se proyectan por `env` y `ConfigMap`, no por filesystem compartido con BHM

## Secretos, almacenamiento y red

### Secretos

- `bhm-env` sigue siendo el secreto transicional del laboratorio
- `greenhouse-simulator` reutiliza esas credenciales solo cuando se ejecuta como herramienta externa fuera de `kind`

### Almacenamiento

- el baseline persistente no añade `ConfigMap`, `PVC` ni `Deployment` para simuladores externos
- `greenhouse-simulator` se ejecuta fuera del baseline como stresser one-shot

### Red

- `greenhouse-simulator` se conecta al broker por `localhost:21900` desde Windows o por `bhm-lab-control-plane:31900` cuando corre en contenedor unido a la red `kind`
- no expone `Service` propio porque el flujo actual es publish/subscribe hacia el broker, no API entrante

## Reconciliacion del broker en el entorno final

La estrategia de reconciliacion no cambia de ownership por introducir el workload externo:

- el broker sigue owned por `StatefulSet/mosquitto`
- el reconciliador sigue broker-local y sidecar mientras dependa del filesystem del broker
- el producto externo no recibe permisos para escribir artefactos broker-facing

Eso confirma que la migracion a Kubernetes se hace sobre la arquitectura saneada de Fases 3 a 8, no como un parche sobre el modelo anterior de shared volumes.

## Estrategia de despliegue actual

- `k8s/base` como baseline de manifests
- `deploy.ps1 -Action build -Runtime kind -ImageTag <tag>` construye las imagenes locales del core del laboratorio
- `deploy.ps1 -Action start -Runtime kind -ImageTag <tag>` crea `kind`, carga imagenes y aplica la topologia

## Siguiente corte fuera de este baseline

1. separar por completo las credenciales del stresser externo de las credenciales admin del laboratorio
2. decidir si `greenhouse-simulator` debe seguir como herramienta externa o convertirse en workload formal del cluster
3. publicar la imagen del simulador en registry real si pasa a formar parte del baseline operativo
4. formalizar chart u overlay por entorno si el laboratorio deja de ser el unico cluster objetivo