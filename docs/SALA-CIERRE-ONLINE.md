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

Los proyectos fuente originales de Apps Script, su inventario completo de triggers y el ajuste del conteo del correo no se sustituyen con el espejo público. Los 26 medios históricos no localizados tampoco se reemplazan por una regeneración. Las decisiones de Alejandro y Sayri permanecen en su formato y con veto igual. No cancelar las rutinas anteriores de Claude hasta conciliar la comparación y esos pendientes.
