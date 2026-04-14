# ADR-0002 - Compose-first con portabilidad a Kubernetes

- Estado: Aceptado
- Fecha: 2026-04-14

## Contexto

El entorno objetivo inmediato para la migracion es Docker/Podman Compose. Sin embargo, la evolucion de plataforma prevista apunta a una implementacion posterior sobre Kubernetes, incluyendo la integracion con la imagen del producto de transformacion de datos.

El riesgo principal es resolver necesidades actuales con atajos de Compose que luego hagan costosa o confusa la migracion a Kubernetes.

## Decision

- La migracion se implementa primero sobre Docker/Podman Compose.
- Cada cambio estructural importante debe evaluarse tambien por su portabilidad a Kubernetes.
- Compose se considera plataforma operativa inmediata, no arquitectura final.
- La solucion debe evitar dependencias que luego sean dificiles de portar, por ejemplo:
  - escritura cruzada entre contenedores como mecanismo de control
  - configuracion manual sin fuente de verdad persistente
  - secretos embebidos en imagenes
  - suposiciones de red o almacenamiento no trasladables a objetos de Kubernetes
- Las decisiones de configuracion del broker, secretos, persistencia y observabilidad deben modelarse desde ahora con una semantica compatible con una futura reconciliacion o patron operador.

## Consecuencias

- Los documentos de despliegue deben dejar claro que Compose es el primer objetivo operativo.
- Las fases de migracion deben incluir consideraciones explicitas para Kubernetes, aunque su implementacion se difiera.
- La validacion tecnica debe comprobar no solo que algo funciona hoy en Compose, sino que no bloquea la evolucion posterior.