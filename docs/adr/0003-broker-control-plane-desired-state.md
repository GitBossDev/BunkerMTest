# ADR-0003 - Control-plane del broker basado en estado deseado y reconciliacion

- Estado: Aceptado
- Fecha: 2026-04-14

## Contexto

La arquitectura actual permite que el backend de gestion escriba directamente sobre archivos internos del broker, como `mosquitto.conf` y `dynamic-security.json`, usando volumes compartidos. Ese enfoque funciona en Compose, pero introduce un acoplamiento fuerte entre contenedores y contradice el modelo deseado para una arquitectura mas stateless y portable.

Tambien dificulta la auditoria, el rollback, la deteccion de drift y la futura migracion a Kubernetes.

## Decision

- El backend de gestion no aplicara cambios al broker escribiendo directamente sus archivos como mecanismo primario.
- BHM pasara a trabajar con un modelo de estado deseado.
- Un componente de reconciliacion sera responsable de transformar ese estado deseado en estado aplicado sobre el broker.
- Se separaran los conceptos de:
  - estado deseado
  - configuracion generada
  - estado aplicado
  - estado observado
  - drift
- La gestion de clientes, DynSec, ACLs, bridges y certificados debe converger en ese mismo modelo.
- La solucion concreta en Compose puede ser un worker o reconciliador dedicado, pero su semantica debe poder evolucionar despues a un patron operador en Kubernetes.

## Consecuencias

- Los endpoints de gestion deberan dejar de escribir archivos directamente y pasar a registrar solicitudes de cambio.
- Se necesitara persistencia explicita del estado deseado y del historial de cambios.
- Se habilita una mejor trazabilidad, validacion previa, rollback y comparacion entre lo solicitado y lo realmente aplicado.
- La fase de migracion del broker deja de ser una simple refactorizacion tecnica y pasa a ser un cambio de modelo operacional.