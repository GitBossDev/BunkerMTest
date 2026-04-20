# ADR - Architecture Decision Records

Este directorio contiene los Architecture Decision Records de BHM (Broker Health Manager).

Su objetivo es dejar registradas las decisiones estructurales del proyecto para evitar ambiguedades, reversiones accidentales y cambios contradictorios durante la migracion a microservicios.

## ADRs activos

- [ADR-0001](./0001-product-identity-and-bounded-contexts.md) - Identidad del producto y bounded contexts.
- [ADR-0002](./0002-compose-first-kubernetes-ready.md) - Compose-first con portabilidad a Kubernetes.
- [ADR-0003](./0003-broker-control-plane-desired-state.md) - Control-plane del broker basado en estado deseado y reconciliacion.
- [ADR-0004](./0004-postgresql-per-bounded-context.md) - PostgreSQL separado por bounded context para BHM.
- [ADR-0005](./0005-compose-first-service-topology.md) - Topologia de servicios objetivo para Compose-first.
- [ADR-0006](./0006-local-kubernetes-lab-strategy.md) - Laboratorio local de Kubernetes como validacion opcional.
- [ADR-0007](./0007-phase5-observability-pipeline.md) - Pipeline de observabilidad tecnica para Fase 5.
- [ADR-0008](./0008-phase6-identity-and-secrets.md) - Modelo de identidades y secretos para Fase 6.
- [ADR-0009](./0009-phase6-ip-whitelist-ownership.md) - Ownership y modelo final de whitelist por IP para Fase 6.

## Reglas de uso

- Cada ADR nuevo debe describir contexto, decision, consecuencias y estado.
- Los ADRs se redactan en espanol.
- El codigo que derive de estas decisiones se escribe en ingles.
- Si una decision queda obsoleta, no se borra el ADR: se reemplaza con uno nuevo que lo supere.