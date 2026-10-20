# Apertura progresiva y medios diferidos

Dirección reportó más de70segundos sin contenido después de la primera mejora y pidió integrar opciones1 y6 juntas. La caché no resuelve la primera visita: sólo existía tras completar servidor, inventario y tiras.

## Cambio

- La primera visita consulta el manifiesto público existente en paralelo con Apps Script. Muestra su fecha y permite consulta; las decisiones esperan la respuesta vigente. No publica datos nuevos ni cambia autenticación.
- Cada tira aparece al terminar su lectura. El inventario y otra tira lenta no bloquean las publicaciones disponibles. Cuatro trabajadores como máximo; lecturas repetidas de una tira comparten petición. Los fallos temporales no quedan guardados como ausencia definitiva.
- El control de integridad de medios sigue cerrando imágenes ante fallo, pero ya no bloquea texto y navegación. Imágenes fuera de vista se activan mediante IntersectionObserver; los videos usan preload none y los iframes carga diferida. La tarjeta siguiente y las fuentes tipográficas no bloquean la apertura.
- Notas, cola y borradores se mantienen separados. Un rechazo de credencial retira la consulta y otra sesión no recibe la caché privada anterior. La copia pública existente permanece distinta de una sesión validada.

## Evidencia y alcance

Recorrido sintético de primera visita con servidor, manifiesto de medios, inventario y una tira retenidos: primera publicación visible antes de liberar cualquiera de ellos; decisiones deshabilitadas, cero POST y cero errores de página. Muestras locales521ms escritorio y331ms móvil. Son muestras controladas, no p95 ni garantía para una red real. Regresiones de caché conservan borradores y retiran copia ante rechazo.

El servidor puede seguir tardando en validar y habilitar decisiones. Esta entrega elimina su bloqueo de consulta; no acredita reparación ni despliegue del backend Apps Script. Atlas: yod-portal#289, CHG-SALA-ARRANQUE-PROGRESIVO-20261020. Publicación se acredita con CI, recibo Pages y hashes de archivos servidos del PR consumidor.

## Reversión

Revertir el PR de frontend, sin borrar borradores, cola, decisiones, snapshots ni medios.

## Hipótesis 8 y diagnóstico 3/4/9

Autorización ampliada por Dirección: timeout8000ms por lectura del día (también topes explícitos, incluye cuerpo JSON), máximo2 solicitudes totales aun con credenciales alternativas, backoff400ms. Se elimina el ciclo automático posterior de30 intentos. Un clic explícito puede iniciar otra actualización. Snapshot/tiras/medios tienen tope8000ms y no bloquean el texto disponible.

La copia publicada se cachea tras cada publicación visible, con origen published y fecha; no espera servidor ni inventario completo. La reapertura conserva modo consulta y bloqueo de decisiones. Una clave rechazada retira la copia; una identidad distinta no reutiliza la anterior. Marca performance sala-contenido-visible después de dos frames y métricas SalaRendimiento sin URLs ni credenciales.

Traza real aportada por Claude, atribuida al20-oct15:32Z sobre c528567: /exec inicia1.6/42.3/83.7s, tres abortos40000ms,0bytes/estado0; snapshot inicia123.7s y tarda200ms. No es medición propia. El código anterior no mostraba respaldo a una sesión. La nueva ruta muestra consulta explícita. El valor UI547s era histórico local, no una duración de servidor probada.

El espejo gas/Code.gs muestra autenticación delegada a dos Porteros y seis lecturas completas de pestañas al fallar cache del día. No demuestra dónde se detiene la versión viva. No se modifica ni se afirma desplegar ese espejo. El workflow Medir lectura de Sala ejecuta dos GET del día con agente,8s cada uno y400ms entre ellos; registra sólo métricas y cache_hit si existe. Primera y consecutiva no demuestran runtime frío/caliente. Sin acceso al editor/ejecuciones no se pueden atribuir cuotas ni etapa exacta.

Validación local final:52 pruebas Node,13 controles nube/verificar.py, prueba del presupuesto/privacidad de sonda y recorrido completo tablero/tira/carrusel. Reapertura sintética146/169ms. Primera visita sintética última corrida1415/317ms bajo carga: no garantía subsegundo. La primera tarjeta aparece y se cachea antes de soltar servidor,medios,inventario y tira lenta. Cero POST y errores JS. Atlas ampliado en PR291 conserva propuesta paralela de revisión de tomas PR290.
