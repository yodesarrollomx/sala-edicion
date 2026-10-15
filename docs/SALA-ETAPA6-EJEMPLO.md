# Etapa 6: ejecutar, inspeccionar y corregir

El ejemplo técnico aislado usa motores reales y archivos privados. No crea
decisiones, trabajos de negocio ni aprobaciones editoriales. Su aprobación
técnica se distingue de una pieza lista para publicar.

## Evidencia inicial

- Ejemplo `38814111428`: success; 254.1 s de producción; seis archivos
  descargados y verificados por SHA256; video H264/AAC, 1080x1920, 30fps,
  18.167 s. Lámina y fotogramas inspeccionados.
- Voz presente: actividad entre aproximadamente 6.04 y 9.68 s. Los márgenes
  heredados ocupaban casi todo el ejemplo breve. La receta del ejemplo ahora
  pide 0.35 s de margen y 0.5 s de cola; comprueba que el corte exceda la voz
  entre 0.9 y 1.5 s. No modifica los defaults ni las reglas editoriales.
- Escena: parallax con Depth Anything V2. Es movimiento sobre una imagen;
  no se declara video generativo.
- Sonda `38814278019`: reglas, cola y catálogo respondieron; día agotó tres
  intentos de lectura. No acredita estabilidad del backend.

## Corrección de consultas repetidas

`fusionDia_` y `fusionProduccion_` consultaban CONFIG por cada firma. Con
240 firmas de dos editores realizaban 240 lecturas. Cada función guarda ahora
los nombres únicamente durante su invocación: dos lecturas y los mismos
120 vetos, firmas y notas. La siguiente consulta recupera nombres frescos.
No cambia autenticación, orden de decisiones, reglas de aprobación ni permisos.

Pruebas sintéticas: 504 Python, 111 Node y 13 verificaciones de Sala. Los seis
casos nuevos cubren volumen, vetos, notas, pendiente, borrar y nombres frescos.
Atlas PR258 integrado; el workflow fija el commit aprobado.

## Activación separada

Se localizó el proyecto original mediante Extensiones del Sheet. Ambas
funciones coinciden con las probadas y tienen respaldo privado. La cuenta
abierta puede leer el código, pero Gestionar implementaciones responde
«No tienes permiso para realizar esta acción», también tras recargar.
El parche del repositorio no acredita reparación del endpoint vivo. No se
crea otro despliegue ni se cambian accesos para eludir esta restricción.

Para activarlo, el propietario autorizado debe aplicar únicamente los cambios
de ambas funciones en sus archivos originales, conservar los demás archivos,
guardar y actualizar la versión del despliegue existente, sin cambiar URL,
identidad ejecutora ni acceso. Después se repiten la sonda y la lectura real
del día. Un fallo sigue siendo fallo; no se sustituye con una lista vacía.

Rollback: restaurar sólo las funciones respaldadas y la versión anterior del
despliegue existente. Conservar decisiones, cola, medios y bitácora.
