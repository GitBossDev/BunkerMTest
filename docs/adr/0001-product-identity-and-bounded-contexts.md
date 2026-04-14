# ADR-0001 - Identidad del producto y bounded contexts

- Estado: Aceptado
- Fecha: 2026-04-14

## Contexto

El repositorio nacio como una extension de BunkerM, pero el producto actual ya no debe presentarse como una simple evolucion interna del panel original. La plataforma pasa a tener una identidad propia enfocada en la gestion tecnica del broker y debe integrarse con otro producto orientado a reporting de negocio y transformacion de datos.

Ademas, el repositorio contiene documentacion y nombres historicos mezclados, lo que incrementa la ambiguedad sobre ownership de datos, alcance funcional y limites arquitectonicos.

## Decision

- El nombre activo del producto pasa a ser BHM, siglas de Broker Health Manager.
- BHM se define como el producto responsable de la gestion tecnica del broker MQTT.
- El bounded context de BHM incluye:
  - configuracion del broker
  - clientes MQTT, DynSec, roles, grupos y ACLs
  - estado operativo y salud del broker
  - auditoria tecnica
  - reporting tecnico y operativo de la propia plataforma
- El producto externo de reporting o transformacion de datos tendra su propio bounded context, su propia persistencia y sus propios contratos.
- La integracion entre productos se hara mediante APIs y, mas adelante si aplica, eventos tecnicos o de dominio.
- El producto externo no accedera directamente a la base de datos interna de BHM.

## Consecuencias

- La documentacion nueva debe usar BHM como nombre principal.
- La documentacion historica se ira alineando progresivamente cuando sea pertinente.
- Las futuras decisiones tecnicas deben respetar estos limites de ownership y evitar mezclar reporting tecnico con reporting de negocio.
- Los nombres tecnicos existentes en runtime, imagenes o directorios como `bunkerm-*` pueden mantenerse temporalmente mientras no exista una fase de renombre controlada.