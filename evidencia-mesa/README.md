# Evidencia real de la mesa · 17 de octubre de 2026

Estado de aceptación integral: **PENDIENTE**. Estos resultados acreditan lectura y navegación del sitio publicado, no cuatro producciones nuevas.

Código desplegado: `ee3e9a5b54b08fa59ed6d2d7df17c8550b102d68` ([PR 316](https://github.com/yodesarrollomx/sala-edicion/pull/316)).
[Corrida visual](https://github.com/yodesarrollomx/sala-edicion/actions/runs/39039317567).
[Bitácora JSON](resultado.json).

| Pasada | Inicio UTC | Fin UTC | Pantalla | Publicaciones | Imágenes comprobadas | Errores |
|---|---|---|---|---:|---:|---:|
| 1 | 2026-10-17T14:06:54.674Z | 2026-10-17T14:07:11.200Z | escritorio | 11 | 57 | 0 |
| 2 | 2026-10-17T14:07:11.208Z | 2026-10-17T14:07:29.919Z | movil | 11 | 57 | 0 |
| 3 | 2026-10-17T14:07:29.924Z | 2026-10-17T14:07:45.465Z | escritorio | 11 | 57 | 0 |
| 4 | 2026-10-17T14:07:45.471Z | 2026-10-17T14:08:04.051Z | movil | 11 | 57 | 0 |

Cada pasada abre un contexto nuevo de navegador, cierra la bienvenida con su botón, abre todas las publicaciones mediante clic, recorre sus láminas y comprueba carga real de cada imagen. Después recorre también las miniaturas del tablero antes de capturarlo. El rol es **lector**, sin credenciales editoriales; se bloquearon escrituras de red y no hubo ninguna. No se sustituyeron respuestas ni imágenes por fixtures.

Capturas:
- [Escritorio](pasada-1-pantalla.jpg), [tira completa](pasada-1-tira.jpg), [tablero completo con imágenes cargadas](pasada-1-mesa.jpg).
- [Móvil](pasada-4-pantalla.jpg), [tira móvil](pasada-4-tira.jpg), [tablero móvil completo](pasada-4-mesa.jpg).

El inventario procede de Mesa `39038648620`, actualizado a `2026-10-17T13:58:48.682801+00:00`: 11 fuentes vigentes observadas, 57 láminas, cuatro pendientes. No acredita cobertura de todo el historial.

## Producción y bloqueos comprobados

[Recorrido real Mesa → Productor → Ejecutor → Revisión](https://github.com/yodesarrollomx/sala-edicion/actions/runs/39038648620):
Mesa preparó cero láminas nuevas; Productor encoló cero trabajos nuevos; Ejecutor produjo cero trabajos. **No cuenta como producción completa aprobada**.

[Lectura real de preparación](https://github.com/yodesarrollomx/sala-edicion/actions/runs/39038776105):
el endpoint histórico responde `sala_recurso_no_disponible`; COLA contiene 138 hechos, 11 fallos y cuatro obsoletos. El contenido de las fuentes actuales todavía tiene vetos editoriales, y Mesa Vacía conserva cuatro láminas pendientes. No se cambiaron esas decisiones ni las reglas para pasar la prueba.

La bitácora privada de continuidad contiene el procedimiento concreto de activación del contrato histórico en el proyecto Apps Script original. Falta ejecutar y validar ese despliegue, preparar revisiones válidas, obtener las decisiones editoriales necesarias y acreditar cuatro producciones completas consecutivas. La independencia de la suscripción para mantenimiento también permanece pendiente.
