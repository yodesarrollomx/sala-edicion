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
| Una lectura intermitente de COLA devolvió HTTP404 antes de responder correctamente | Tercer GET fresco sólo tras 404 y dentro del presupuesto original | La sonda diagnóstica no se usa para acreditar éxito |
| El recibo servido podía no acreditarse durante la espera | Clave de caché distinta por GET, plan fijado antes del bundle y diagnóstico de campos distintos | Conserva igualdad exacta y guardias; la causa del incidente previo sigue sin confirmarse |
| La interfaz prometía horarios y una ronda futura sin evidencia | Representa copy, publicación y cola con estados comprobados | Casos renderizados sin horarios inventados |

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

## Evidencia de activación

Atlas [235](https://github.com/yodesarrollomx/yod-portal/pull/235) y Sala
[305](https://github.com/yodesarrollomx/sala-edicion/pull/305) quedaron integrados.
La publicación [38682616103](https://github.com/yodesarrollomx/sala-edicion/actions/runs/38682616103)
confirmó el recibo FULL del código `b6884d1`. La publicación posterior
[38683590998](https://github.com/yodesarrollomx/sala-edicion/actions/runs/38683590998)
confirmó código `8761404`, snapshot `413425842` y hash de datos
`a576545e88e76b040abc2e6788dda4afc5f57f0bc5ffd6ef0fb1e249e950d186`.
Un cambio posterior puede sustituir estos recibos; el archivo servido
`version-online.json` es la comprobación vigente.

El cierre [38683590924](https://github.com/yodesarrollomx/sala-edicion/actions/runs/38683590924)
localizó un fallo de lectura de COLA, sin efectos iniciados. El diagnóstico de
[306](https://github.com/yodesarrollomx/sala-edicion/pull/306) sólo publica fases,
tipos y códigos permitidos. Un preflight fallido no acredita producción.

El recorrido [38683389298](https://github.com/yodesarrollomx/sala-edicion/actions/runs/38683389298)
procesó cero piezas en Mesa y rechazó guardar porque main avanzó. No acredita
nueva generación. Se conserva esa guardia; Ejecutor y Revisión pueden atender
la cola existente con sus validaciones propias aunque falle una fase anterior.
Continuar exige éxito de Mesa y Revisión para no relanzar Mesa tras un fallo.

## Capacidad disponible

El intento de restablecer Modal
[38683018389](https://github.com/yodesarrollomx/sala-edicion/actions/runs/38683018389)
se detuvo porque A10G requiere un método de pago. No invocó GPU ni añadió
facturación. La cascada existente permite Wan en Hugging Face, Modal, parallax
CPU y cámara CPU. Las reglas observadas habilitan las cuatro etapas de nube,
el respaldo de cámara y su uso al agotar cuota. No se observaron reglas que
sustituyan los defaults del ejecutor: `escena_parallax=1` y `escena_modal=0`.
El respaldo CPU queda disponible cuando existe trabajo vigente aprobado y se
cumplen sus compuertas; esta lectura no acredita una salida nueva. Parallax y
cámara son movimiento sobre láminas; sus metadatos conservan `generativa:false`.
El Space de Wan y su API estaban disponibles; eso no demuestra cupo de cuenta
ni generación nueva. No existe adaptador Gemini/Veo de video en este proceso.

El vigilante externo de Render está sano y observa; su recuperación automática
requiere completar la conexión GitHub App. GitHub exige confirmar la identidad
de la cuenta antes de revisar esa instalación. La tarea diaria existente de
revisión de Sala conserva horario y ahora recoge la continuidad de ChatGPT.
La estabilidad de siete días y la recepción del próximo correo siguen siendo
comprobaciones futuras, separadas de guardar código y publicar el sitio.

## Verificación y reversión

Las pruebas usan datos sintéticos. La lectura agregada del Sheet real es de
sólo lectura y no se almacena en este repositorio. CI, publicación, montaje y
recepción de correo son comprobantes diferentes. Cada cierre debe vincular los
recibos correspondientes, sin declarar resueltas chinches de otros proyectos.

Antes de revertir tras emitir deltas: desactivar el flag con el lector compatible,
publicar FULL, verificar su recibo y sólo entonces revertir lectores si procede.
Conservar releases, medios, decisiones, cola e historial. El correo puede volver
al cuerpo anterior conservado sin cambiar destinatario, URL ni permisos.

## Corte operativo y recuperación de fallos

El recorrido [38685236773](https://github.com/yodesarrollomx/sala-edicion/actions/runs/38685236773)
completó Mesa, Productor y Ejecutor sobre `a2bbfce`. Productor recuperó las
decisiones existentes y no añadió trabajos; Ejecutor no encontró pendientes.
Eso no acredita generación nueva. Revisión guardó su estado privado, pero su
publicación [38686617000](https://github.com/yodesarrollomx/sala-edicion/actions/runs/38686617000)
no acreditó el recibo exacto en el plazo. Una lectura posterior sí observó código, datos, snapshot y run previstos;
el hash del plan esperado por ese runner no quedó registrado. Esto no basta
para atribuir la causa a la caché. El nuevo diagnóstico
distingue campos, HTTP, JSON y transporte sin publicar sus valores.

`Auditar cortes fallidos sin reencolar` es manual y comparte la exclusión del
Ejecutor. No siembra reglas ni modifica COLA, decisiones, contenido o medios.
Exige snapshot publicado con recibo independiente, fuente vigente, guion completo
aprobado sin vetos, identidad exacta del plan y de las dependencias, bytes y MD5
de Drive, etapa habilitada y una segunda lectura estable. Su informe detallado
se conserva en la carpeta privada configurada; el log público sólo contiene
conteos y códigos permitidos. Elegibilidad no significa reencolado ni producción.
El workflow necesita visibilidad de releases draft y de Pages; el cliente se
limita explícitamente a GET y bloquea mutaciones de GitHub.

La cancelación única de la corrida huérfana
[37655539140](https://github.com/yodesarrollomx/sala-edicion/actions/runs/37655539140)
fue rechazada con HTTP409 en el mantenimiento
[38685379932](https://github.com/yodesarrollomx/sala-edicion/actions/runs/38685379932).
La corrida seguía queued y sin jobs al releerla; no se afirma que esté drenada
ni se repite el POST. La emisión incremental sigue apagada.

El artefacto observado ocupaba 897647868 bytes, aproximadamente 95% del
presupuesto de 900 MiB. No se amplía ese límite ni se borran históricos. La
continuidad de producción necesita una migración de medios verificada antes
de agotar esa capacidad. El [inventario de chinches](SALA-CHINCHES-CORTE-20261015.md)
separa reparaciones técnicas de decisiones editoriales y aceptación pendiente.

## Resultado posterior a PR308

[308](https://github.com/yodesarrollomx/sala-edicion/pull/308) se integró en
`e4da08887e45e984be8ea945ce607db464b0fb52`, con cinco controles de CI aprobados
sobre su head exacto y 394 pruebas Python, 18 Node y 13 verificaciones locales.
La publicación [38688574369](https://github.com/yodesarrollomx/sala-edicion/actions/runs/38688574369)
acreditó el código nuevo. Plan
[38688574251](https://github.com/yodesarrollomx/sala-edicion/actions/runs/38688574251)
y su publicación [38688736093](https://github.com/yodesarrollomx/sala-edicion/actions/runs/38688736093)
acreditaron un snapshot nuevo, no sólo la republicación de datos anteriores.
El [Cierre38688574178](https://github.com/yodesarrollomx/sala-edicion/actions/runs/38688574178)
completó preflight, Productor y Ejecutor: 14 fuentes, 29 decisiones afirmativas,
153 trabajos existentes y ninguno nuevo; cero pendientes ejecutables. No hubo
operaciones de correo ni escrituras de negocio en el preflight.
Revisión [38688731578](https://github.com/yodesarrollomx/sala-edicion/actions/runs/38688731578)
y su publicación [38689030877](https://github.com/yodesarrollomx/sala-edicion/actions/runs/38689030877)
también terminaron correctamente, con snapshot 413460646. Esto acredita el
recorrido observado; no producción nueva, entrega del próximo correo ni
estabilidad de siete días. La causa exacta del incidente anterior sigue
sin confirmarse.

La QA pública posterior encontró otro texto ambiguo: contar publicaciones
no publicadas no acredita que haya trabajos activos. La vista vacía distingue
visitante, lector y editor y describe el estado de consulta; conserva roles,
acciones y decisiones. No afirma «Todo decidido» sin identidad editorial.
