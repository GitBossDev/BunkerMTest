# ADR-0004 - PostgreSQL separado por bounded context para BHM

- Estado: Aceptado
- Fecha: 2026-04-14

## Contexto

La solucion actual utiliza SQLite para estado operativo local, lo cual simplifico etapas anteriores pero no es suficiente para la arquitectura objetivo. Ademas, existe la necesidad de integrarse con otro producto sin caer en una base de datos compartida entre dominios.

La persistencia de BHM debe volverse mas robusta y portable, pero manteniendo limites claros de ownership de datos.

## Decision

- BHM migrara progresivamente su persistencia operativa a PostgreSQL.
- PostgreSQL sera propio del bounded context de BHM.
- No se compartiran tablas de dominio con el producto externo de reporting o transformacion de datos.
- La migracion desde SQLite sera incremental, evitando un big bang siempre que sea posible.
- Se priorizara la migracion de:
  - broker history
  - topic history
  - client activity
  - reporting tecnico propio
  - estado deseado y auditoria del broker

## Consecuencias

- La capa de persistencia debera desacoplarse del backend SQLite actual.
- El modelo de datos tendra que soportar auditoria, reconciliacion y consultas operativas mas ricas.
- La integracion con otros productos se resolvera por APIs o eventos, no por acceso directo a esta base de datos.
- La evolucion a multiples replicas del backend de gestion sera mas factible al mover el estado durable a PostgreSQL.