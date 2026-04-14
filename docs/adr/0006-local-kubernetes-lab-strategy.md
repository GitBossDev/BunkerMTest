# ADR-0006 - Laboratorio local de Kubernetes como validacion opcional

- Estado: Aceptado
- Fecha: 2026-04-14

## Contexto

Durante el arranque de la Fase 3 surgio la posibilidad de "simular" un cluster de Kubernetes sobre Docker o Podman para adelantar validaciones antes de la migracion formal de plataforma.

La idea es tecnicamente posible: existen opciones como `kind` y `minikube` para correr clusters locales usando contenedores o maquinas locales. Sin embargo, en BHM el objetivo inmediato de la Fase 3 no es validar manifests ni networking de Kubernetes, sino eliminar la escritura cruzada sobre el broker y establecer un control-plane basado en estado deseado y reconciliacion.

Ademas, el entorno actual de trabajo usa Podman remoto sobre Windows/WSL2. Eso agrega complejidad operativa adicional para cualquier cluster local y no resuelve por si mismo la deuda arquitectonica actual.

## Decision

- No introducir un cluster local de Kubernetes como baseline obligatorio de desarrollo en Fase 3.
- Mantener Compose-first como entorno principal hasta que exista al menos un primer corte funcional de `bhm-reconciler` y del modelo de estado deseado.
- Considerar un laboratorio local de Kubernetes solo como carril secundario de validacion temprana, no como prerequisito para avanzar.
- Si se habilita ese carril, la opcion preferida sera `kind` antes que `minikube` para pruebas tempranas de portabilidad, porque su uso como cluster efimero de validacion es mas directo y su ajuste conceptual encaja mejor con una verificacion ligera de manifests y semantica operativa.
- `minikube` no se adopta como opcion prioritaria para este proyecto mientras el runtime principal siga siendo Podman, porque su driver de Podman sigue documentado como experimental y agrega variabilidad innecesaria.

## Consecuencias

- La Fase 3 sigue concentrada en el desacople correcto del control-plane y no se distrae con problemas de laboratorio local que todavia no prueban el valor principal.
- La compatibilidad futura con Kubernetes se trabaja por semantica y contratos: reconciliacion, estado deseado, secretos, almacenamiento y ownership claros.
- Una vez exista el primer corte funcional del reconciliador, se podra crear un laboratorio opcional con `kind` para verificar:
  - traduccion basica de componentes a objetos de Kubernetes
  - suposiciones de red y puertos
  - manejo de secretos y volumenes persistentes
  - despliegue temprano no productivo del stack recortado
- La validacion fuerte de Kubernetes sigue ubicada en Fase 8 y la implementacion real sigue fuera del alcance inmediato hasta Fase 9.