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

## Reglas de uso

- Cada ADR nuevo debe describir contexto, decision, consecuencias y estado.
- Los ADRs se redactan en espanol.
- El codigo que derive de estas decisiones se escribe en ingles.
- Si una decision queda obsoleta, no se borra el ADR: se reemplaza con uno nuevo que lo supere.