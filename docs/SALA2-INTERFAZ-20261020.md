# Sala 2.0 · interfaz sobre la misma Sala

Encargo autorizado de Alejandro, preparado por Claude en CL-SALA2-EN-LINEA-20261020.
Se copió sala2.css sin cambios y sala2.js con ajustes mínimos de integración.
El index añade sólo los dos includes y el sello de versión.

El turno abre directamente cuando el motor confirma permiso y pasos vigentes.
Mientras el servidor no responde se conserva la copia publicada en consulta;
esta interfaz no elimina la demora del backend ni autoriza decidir sobre snapshots.
Aprobar y pedir cambios reutilizan decidir/data-op/data-ning/pedirNota.
No se modifican datos, Apps Script, llaves, cola ni funciones de guardado.

Ajustes: permiso cerrado ante error; no convertir copia en turno vacío;
observadores idempotentes; navegación renombrada respetando iconos;
dock móvil sobre navegación inferior; segundo de video en click (ratón/tacto/teclado);
enlace clásico conserva parámetros. El segundo es manual para Drive.
Vista anterior: `?clasica=1`; CSS queda inactivo y JS retorna antes de modificar DOM.

Verificación local: 128 pruebas Node y 13 puertas nube/verificar.py OK.
Chromium 1440/390, editor/lector/clásica/servidor fallido: cinco cortes sintéticos,
nota, NO VA, segundo, aprobar, deshacer y navegación. Cero errores JS y
cero escrituras reales. Las rutas externas se interceptan antes de la red.
Pruebas de caché y arranque progresivo clásicas OK.
Recorrido completo clásico y CI: recibos en PR/Buzón. Publicación se acredita
por Pages y comparación de activos en vivo, no por estas pruebas sintéticas.

Rollback: revertir PR de interfaz; no borrar datos, medios, cola ni borradores.
