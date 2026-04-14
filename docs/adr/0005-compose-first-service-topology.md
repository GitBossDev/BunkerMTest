# ADR-0005 - Topologia de servicios objetivo para Compose-first

- Estado: Aceptado
- Fecha: 2026-04-14

## Contexto

La Fase 1 requiere aterrizar la arquitectura objetivo a una topologia ejecutable en Docker/Podman Compose sin perder el rumbo hacia Kubernetes. El sistema actual aun funciona con una plataforma consolidada en `bunkerm-platform`, un broker separado y PostgreSQL como herramienta opcional.

Sin una topologia objetivo explicitada, la Fase 2 correria el riesgo de introducir servicios nuevos sin ownership claro o de perpetuar el monolito actual como solucion final.

## Decision

- La topologia objetivo de BHM en Compose-first se define con los siguientes servicios logicos:
  - `bhm-web`
  - `bhm-api`
  - `bhm-reconciler`
  - `bhm-postgres`
  - `bunkerm-mosquitto`
  - `bhm-observability-collector` como servicio opcional posterior
- `bhm-web` y `bhm-api` pueden permanecer temporalmente consolidados si mantienen contratos API y no asumen ownership impropio.
- `bhm-reconciler` debe separarse del API como responsabilidad operacional diferenciada.
- PostgreSQL deja de considerarse herramienta opcional en la arquitectura objetivo, aunque su adopcion tecnica se ejecute por fases.
- El broker mantiene ciclo de vida separado respecto a BHM.

## Consecuencias

- La Fase 2 puede orientarse a una topologia Compose concreta sin rediscutir limites de responsabilidad.
- Los cambios a `docker-compose.dev.yml` deberan medirse contra esta topologia objetivo.
- Se habilita una migracion incremental desde el runtime actual hacia una forma de despliegue mas cercana a la arquitectura deseada.