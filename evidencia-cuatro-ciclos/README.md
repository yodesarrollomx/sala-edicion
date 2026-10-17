# Sala en línea: evidencia funcional del 17 de octubre de 2026

[Abre la Sala](https://yodesarrollomx.github.io/sala-edicion/) · [Controlador de la prueba](https://github.com/yodesarrollomx/sala-edicion/actions/runs/39076552760) · [Bitácora JSON](bitacora.json)

## Producción real previa a las repeticiones

El recorrido [39073909910](https://github.com/yodesarrollomx/sala-edicion/actions/runs/39073909910) terminó correctamente: montó cuatro láminas rehechas de **La servilleta contra el estudio**, con dos opciones por lámina (ocho tomas HiDream-O1-Image-Dev). El corte **Apodo**, de 48 segundos, quedó producido y guardado. Su entrega posterior a revisión quedó montada en [39075627756](https://github.com/yodesarrollomx/sala-edicion/actions/runs/39075627756).

## Cuatro recorridos completos consecutivos

| Ciclo | Ejecución | Inicio real UTC | Fin del workflow UTC | Resultado |
|---|---|---|---|---|
| 1 | [39075517796](https://github.com/yodesarrollomx/sala-edicion/actions/runs/39075517796) | 2026-10-17T22:32:53Z | 2026-10-17T22:46:47Z | SUCCESS |
| 2 | [39076641729](https://github.com/yodesarrollomx/sala-edicion/actions/runs/39076641729) | 2026-10-17T22:49:55Z | 2026-10-17T23:01:17Z | SUCCESS |
| 3 | [39077452048](https://github.com/yodesarrollomx/sala-edicion/actions/runs/39077452048) | 2026-10-17T23:02:22Z | 2026-10-17T23:13:51Z | SUCCESS |
| 4 | [39078280391](https://github.com/yodesarrollomx/sala-edicion/actions/runs/39078280391) | 2026-10-17T23:15:01Z | 2026-10-17T23:29:27Z | SUCCESS |

Cada recorrido ejecutó Mesa, Productor, Ejecutor y Revisión en producción, sin modo simulado. Después se verificaron:
- 22 publicaciones y 77 láminas en el navegador; escritorio y móvil alternados.
- Las ocho opciones nuevas, descargadas completamente y cotejadas por SHA256 y tamaño con el manifiesto fijado por el recibo publicado.
- El video real completo desde Drive: 6,054,335 bytes, 48 segundos, pistas de audio y video, MD5 `ed5db7d90ca6cb7ebdad89fc55ac7721`.
- Cero errores JavaScript y cero escrituras editoriales desde la prueba de navegador.

**Las cuatro repeticiones produjeron cero tomas nuevas:** comprobaron estabilidad y conservación del lote ya producido. No son cuatro lotes nuevos ni cuatro pruebas adicionales del proveedor generativo. Se conservaron las aprobaciones; no se inventaron decisiones para generar más contenido.

## Capturas y comprobantes

- [Escritorio: tablero](ciclo-1/pasada-1-tablero.jpg) · [lámina y opciones](ciclo-1/pasada-1-lamina2-opcion2.jpg)
- [Móvil: tablero](ciclo-4/pasada-1-tablero.jpg) · [lámina y opciones](ciclo-4/pasada-1-lamina2-opcion2.jpg)
- [Resultado ciclo 1](ciclo-1/resultado.json), [2](ciclo-2/resultado.json), [3](ciclo-3/resultado.json), [4](ciclo-4/resultado.json)
- [Comprobación completa del video, ciclo 4](ciclo-4/video-verificado.json)

Las capturas usan modo lector: el aviso de inicio de sesión y los botones editoriales desactivados corresponden a ese rol. No acreditan una nueva aprobación editorial. La prueba del video verifica sus bytes y pistas desde Drive; no equivale a probar reproducción en una sesión privada del usuario.

## Trazabilidad y límites

Los archivos originales de la evidencia están en el commit `5a69faf4d4beee0710991a1074f2f982008c9739`. Los tiempos de la tabla vienen de la API de GitHub; el campo `inicio` del primer ciclo en bitacora.json corresponde a su reverificación, después de terminado ese workflow. El primer recorrido comenzó con SHA `7c74c9e76822fd2394e4adffd67abf0be4672063`; los tres siguientes con `78d9a1d23857314d13ebb350dca35e7c5c3b1841`. Los metadatos completos están en [ejecuciones-github.json](ejecuciones-github.json).

Antes de esta serie hubo fallos de publicación por avance concurrente de main y dos ajustes del verificador (atribuir el recibo al run correcto y leer logs ANSI como datos). Esos fallos no se cuentan como pasadas aprobadas ni se borraron de Actions.

Se observó una advertencia de compatibilidad entre gradio-client y huggingface-hub durante la instalación del Ejecutor; está registrada para seguimiento. El corte ffmpeg y las comprobaciones descritas sí pasaron. Esta evidencia no certifica todos los motores alternativos, nuevas aprobaciones ni publicaciones sociales.
