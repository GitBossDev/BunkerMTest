# Topologia Final Objetivo en Kubernetes

Este documento materializa el primer corte ejecutable de Fase 9: BHM deja de validarse solo como control-plane aislado y pasa a convivir en el laboratorio con un workload externo desacoplado, `water-plant-simulator`, que representa el producto o consumidor de datos que vive fuera del ownership broker-facing de BHM.

## Workloads activos en el laboratorio final actual

| Dominio | Workload | Tipo Kubernetes | Ownership |
| --- | --- | --- | --- |
| Control-plane web | `bunkerm-platform` | `Deployment` | BHM |
| Broker MQTT | `mosquitto` | `StatefulSet` | broker-owned |
| Reconciliacion broker-facing | `reconciler` | sidecar en `StatefulSet/mosquitto` | broker-owned |
| Observabilidad broker-owned | `observability` | sidecar en `StatefulSet/mosquitto` | broker-owned |
| Persistencia control-plane | `postgres` | `StatefulSet` | BHM |
| Delivery de alertas | `bhm-alert-delivery` | `Deployment` | BHM |
| Producto externo/simulador | `water-plant-simulator` | `Deployment` | externo a BHM |

## Contrato de integracion del workload externo

- no comparte volumen con el broker
- no entra en el pod `mosquitto`
- no entra en el pod web `bunkerm-platform`
- se integra solo por MQTT y configuracion propia
- sus secretos y parametros de conexion se proyectan por `env` y `ConfigMap`, no por filesystem compartido con BHM

## Secretos, almacenamiento y red

### Secretos

- `bhm-env` sigue siendo el secreto transicional del laboratorio
- `water-plant-simulator` consume `MQTT_USERNAME` y `MQTT_PASSWORD` desde ese secreto para no duplicar credenciales durante el corte actual

### Almacenamiento

- `water-plant-simulator` usa `ConfigMap` para `plant_config.yaml`
- logs y estado de healthcheck viven en `emptyDir`
- no se añade PVC nuevo porque el simulador no es un source-of-truth durable del sistema

### Red

- `water-plant-simulator` resuelve el broker por `Service` interno `mosquitto:1900`
- no expone `Service` propio porque el flujo actual es publish/subscribe hacia el broker, no API entrante

## Reconciliacion del broker en el entorno final

La estrategia de reconciliacion no cambia de ownership por introducir el workload externo:

- el broker sigue owned por `StatefulSet/mosquitto`
- el reconciliador sigue broker-local y sidecar mientras dependa del filesystem del broker
- el producto externo no recibe permisos para escribir artefactos broker-facing

Eso confirma que la migracion a Kubernetes se hace sobre la arquitectura saneada de Fases 3 a 8, no como un parche sobre el modelo anterior de shared volumes.

## Estrategia de despliegue actual

- `k8s/base` como baseline de manifests
- `deploy.ps1 -Action build -Runtime kind -ImageTag <tag>` construye las tres imagenes locales del laboratorio
- `deploy.ps1 -Action start -Runtime kind -ImageTag <tag>` crea `kind`, carga imagenes y aplica la topologia

## Siguiente corte fuera de este baseline

1. separar credenciales del simulador de las credenciales admin del laboratorio
2. mover el workload externo a imagen publicada en registry real
3. decidir si el producto de transformacion definitivo reemplaza o acompaña a `water-plant-simulator`
4. formalizar chart u overlay por entorno si el laboratorio deja de ser el unico cluster objetivo