# Sala: auditoría y continuidad en nube

La revisión del 15-oct-2026 UTC retoma el proceso editorial existente. El Sheet
conserva decisiones y cola; Drive conserva originales; GitHub Actions ejecuta
Mesa, Productor, Ejecutor y puente; Pages sirve la Sala. La operación no utiliza
la Mac ni requiere una conversación abierta para esos trabajos.

## Defectos comprobados y reparación

| Defecto observado | Reparación | Comprobación |
| --- | --- | --- |
| Productor agotó una lectura fresca del día | Presupuesto de lectura explícito, dos intentos por GET lento y validación del contrato | Regresión de transporte; no sustituye errores con listas vacías |
| POST podía reenviarse al perder el acuse | Un solo envío; conciliación específica antes de repetir | Servidor sintético aplica el POST y pierde la respuesta: una escritura |
| Reintento de Actions compartía run_id con el dueño anterior del mutex | Lease por ejecución, intento y proceso; CAS ambiguo se relee | Recuperación y colisiones entre intentos |
| Preparar el sitio ya guardaba published_receipt | Stage guarda staged_receipt; confirmar promueve sólo tras leer el recibo servido | Publicación incompleta no monta cartas |
| HTTP 500 o indexación tardía podían duplicar o abandonar publicaciones | Correlación exacta y espera de lectura sin segundo dispatch | Dos consultas vacías y posterior corrida aceptada conservan el mutex |
| Cada snapshot volvía a transportar los medios acumulados | Lector de overlays completos y deltas; emisor FULL predeterminado | Replay, hashes, orden, borrados explícitos y retorno a FULL |
| ZIP pequeño no garantizaba sitio dentro de Pages | Presupuesto de 900 MiB del bundle completo antes de subir/copiar | Exceso detiene publicación y conserva históricos |
| Correo sólo contaba propuestas fechadas hoy | Historial y decisiones, vetos, producido/publicado/cola separados; texto plano y diagnóstico | Casos GAS, fuente original cotejada y lectura agregada del Sheet real |
| Pedir ideas se registraba CUMPLIDO | Solicitud durable; no acredita entrega | Dispatch ambiguo no se repite |
| Cerrar NOT_PLANNED se mostraba cumplido | Descartado y completado tienen estados distintos | Regresiones del puente |
| Etiqueta fallida podía duplicar un append de cumplimiento | Checkpoint anterior al efecto y relectura por ID/evento/clave | ACK perdido, ventana limitada y etiqueta fallida conservan el pendiente |

## Activación y límites

La emisión incremental permanece apagada hasta comprobar una publicación FULL
con el lector nuevo y que las ejecuciones anteriores hayan terminado. El flag
es `SALA_SNAPSHOT_INCREMENTAL=1`; sólo se introduce después de ese corte. El
presupuesto del sitio sigue aplicando: un delta no añade capacidad ilimitada.

El correo original fue localizado en su contenedor y respaldado de forma
privada. Sus funciones de fecha, sello, fusión y cierre coinciden con las probadas.
La activación en el proyecto original conserva el cuerpo anterior en
`correoDiarioAnterior20261015_` y añade `CorreoNube20261015.gs`; la función del
disparador conserva el nombre `correoDiario`. El proyecto se guarda y se relee
tras recargar. Esto modifica el código usado por el disparador; no afirma que
la versión web desplegada tenga el endpoint nuevo `correo_estado`.

No se envían entradas ni se repite la comparación histórica al hacer push del
workflow de cierre. Sus opciones manuales explícitas se conservan. La recepción
del próximo correo se comprueba en la bandeja y no se infiere de guardar código.

El vigilante de Render ya corre y conserva estado, pero no tiene todavía una
conexión GitHub comprobada para recuperar ejecuciones. El servicio de oficina
y el sitio estático experimental no equivalen a un worker editorial nuevo.
La vigilancia externa se acepta sólo con su conexión y recuperación verificadas.

El puente cosecha y concilia chinches. Corregir código de una chinche exige su
revisor, pruebas y publicación; el puente no realiza esa implementación.
La revisión de mantenimiento debe usar la rutina existente de ChatGPT, conservando
el historial y comprobantes, sin depender de una sesión de Claude.

## Verificación y reversión

Las pruebas usan datos sintéticos. La lectura agregada del Sheet real es de
sólo lectura y no se almacena en este repositorio. CI, publicación, montaje y
recepción de correo son comprobantes diferentes. Cada cierre debe vincular los
recibos correspondientes, sin declarar resueltas chinches de otros proyectos.

Antes de revertir tras emitir deltas: desactivar el flag con el lector compatible,
publicar FULL, verificar su recibo y sólo entonces revertir lectores si procede.
Conservar releases, medios, decisiones, cola e historial. El correo puede volver
al cuerpo anterior conservado sin cambiar destinatario, URL ni permisos.
