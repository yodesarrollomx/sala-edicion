# Cierre técnico y comparación en nube

Dirección autoriza el 11-oct-2026 cerrar la Sala en nube, volver a solicitar su correo y comparar contra la instalación anterior. Contrato aprobado en Atlas `a629594fcf13d4db20d4e86fa9412e0ce1613bbf`.

La sonda real `38164806597` observa las cuatro etapas habilitadas, Drive configurado y 95 trabajos acumulados: 84 hechos, siete fallidos, cuatro obsoletos y ninguno pendiente. Las rutinas declaradas de Sala están activas. Bitácora registra correo diario el 9, 10 y 11 de octubre a las 07:13 Hermosillo. Eso acredita el registro del backend, no la recepción en una bandeja ni todos sus disparadores.

El cierre guarda un acuse privado antes de solicitar entrada mediante el backend original. No pasa destinatario, no usa otra identidad Gmail y no reintenta llamadas con efectos tras un resultado ambiguo. Un `ok:true` de entrada se registra como solicitud aceptada, sin presentarlo como recepción. El correo diario ya funciona según bitácora; no se reprograma al incorporar código. El botón manual permite restablecer sólo `correoDiario` en su zona original si fuera necesario.

La revisión diaria vuelve a leer correo y estado activo de los workflows, conserva fechas del último dato confirmado y representa fallos de lectura. Productor y ejecutor siguen sus compuertas, peticiones, silencio y límites. El cierre vuelve a correr ambos por sus workflows originales; la comparación aislada no escribe la cola.

## Corrección del montaje

Antes, `tpad` agregaba el mínimo completo incluso a escenas suficientemente largas. Las voces se concatenaban sin esperar el comienzo del siguiente video. Ahora cada escena sólo recibe el tiempo que falta, las duraciones se miden y cada voz se coloca en el inicio de su escena; se conservan los márgenes de inicio/fin configurados. Una prueba de ffmpeg real mide duración, voz, silencio y arranque de la segunda voz. El ejecutor instala las dependencias que requiere su respaldo generativo CPU.

## Comparación

Se toma el corte archivado de septiembre del mismo commit que su guion y cinco de sus seis láminas, con SHA256 de video acreditado previamente. La sexta ruta del guion falta también en ese commit: se busca por ruta exacta en el catálogo y, si no existe un original único y comprobable, se extrae una referencia visual del propio corte. Su procedencia y la comparación parcial quedan explícitas. La nube produce seis voces, seis escenas parallax y un corte; el guion se conserva. Original, salida, guion y acuse se guardan exclusivamente en Drive privado y se descargan para comprobar bytes.

La comparación mide codecs, resolución y duración. Señala que parallax es 2.5D y registra el motor real. También contrasta las dos voces originales recuperadas con la nueva voz de la lámina uno; no presume que el guion de aquellas revisiones esté documentado. El archivo original no incluye un recibo completo de los insumos efectivos del montador Mac. La equivalencia visual y la aceptación editorial requieren revisar ambos videos; no se infieren de las medidas técnicas.

## Alcance pendiente

Los proyectos fuente originales de Apps Script y su inventario completo de triggers no se sustituyen con el espejo público. El ajuste del conteo del correo está implementado y probado en el repositorio; su activación en el proyecto original sigue requiriendo confirmar el código y el despliegue vivos. Los 26 medios históricos no localizados tampoco se reemplazan por una regeneración. Las decisiones de Alejandro y Sayri permanecen en su formato y con veto igual. No cancelar las rutinas anteriores de Claude hasta conciliar la comparación y esos pendientes.


## Correo con estado histórico (15-oct-2026)

La copia anterior de `correoDiario` contaba solamente filas de PROPUESTAS fechadas hoy. Ignoraba la decisión y podía anunciar «hoy no hay pendientes» cuando quedaban tarjetas de días anteriores o producción aprobada. El código corregido calcula el último registro de cada tarjeta de todo el historial hasta hoy; excluye retiradas y fechas futuras. Reutiliza la fusión existente por editor, tarjeta y lámina, también entre fechas. Un «pendiente» no borra una marca y el veto del otro editor sigue vigente. No escribe decisiones.

El correo informa por separado tarjetas pendientes de revisión, tarjetas activas aprobadas, tarjetas con cambios, piezas con corte producido, publicaciones registradas con enlace y registros de publicación sin enlace. También informa trabajos pendientes, en curso y fallidos de COLA. Son conteos de distintas unidades y no se suman como etapas excluyentes. Un corte terminado no acredita publicación en redes; un registro `publicada` con enlace acredita lo declarado por el backend, no una comprobación de la plataforma social.

Si falta una pestaña, su cabecera no corresponde, una lectura falla o los datos requeridos están rotos, el mensaje dice que el estado no se pudo confirmar. No reemplaza una fuente rota por cero. Incluye texto plano además de HTML, conserva el destinatario `CORREO`, la entrada original y el disparador diario. MailApp debe aceptar el envío antes de registrar «Correo de las 7:00 enviado». El log nuevo sólo contiene conteos agregados; `nube/correo_estado.py` distingue contenido confirmado, correo diagnóstico y asuntos históricos sin telemetría. Ninguno prueba recepción en la bandeja.

### Activación desde la nube, sin Mac

1. Recuperar y respaldar de forma privada el proyecto fuente original con la identidad Google autorizada. La conexión del agente al `/exec` y una cuenta de servicio de Drive no conceden acceso de edición de Apps Script. `sala-access-discovery.yml` ya sabe comprobar la presencia de `YOD_APPS_SCRIPT_OAUTH`, `APPS_SCRIPT_OAUTH`, `CLASPRC_JSON`, `SALA_SCRIPT_ID` y `APPS_SCRIPT_PROJECTS` sin imprimir sus valores; no implementa un despliegue del GAS.
2. Comparar las funciones reales con el espejo y aplicar únicamente el parche de correo al proyecto original. Preservar CONFIG, todas las claves reales, el acceso de los dos editores y los disparadores. No reemplazar el proyecto original por el archivo público con marcadores. La actualización del proyecto puede afectar sus disparadores aunque el `/exec` todavía sirva una versión anterior.
3. Mantener el despliegue web existente, su URL, identidad ejecutora y acceso. El repositorio actual prohíbe desplegar GAS desde workflows; ese control y el procedimiento deben conciliarse antes de automatizar el cambio. Un push de este repositorio por sí solo no corrige el correo vivo.
4. Sin enviar ningún correo, consultar con rol agente `recurso=correo_estado`. La respuesta debe contener `ok:true`, `version:correo-historico-2026-10-15` y el resumen completo. Un error de lectura debe devolver `ok:false`, nunca un resumen vacío. Esta prueba no modifica el trigger ni las decisiones.
5. Tras el siguiente envío diario normal, comprobar el log agregado `correo:2`, `lectura:confirmada` y los conteos. No usar «Mándame mi entrada» para validar el resumen: es otro correo. La recepción y el contenido visible de la bandeja se verifican por separado si se dispone de acceso.

Validación local sin red: `python3 nube/verificar.py`, `git diff --check`, `python3 -m unittest discover -s tests -p correo_estado_test.py -v` (incluye los diez casos GAS mediante Node), más `cierre_online_test.py` y `revision_diaria_test.py`. No se modificó el GAS vivo, no se enviaron correos y no se ejecutaron workflows para estas pruebas. Rollback: revertir el commit de correo y restaurar sólo las funciones cambiadas desde el respaldo del proyecto original; no borrar datos de las hojas ni recrear el despliegue.
