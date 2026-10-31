# Registro privado de presentaciones desde PPP

Implementación local del contrato `CHG-PPP-PRESENTACIONES-20261031`, pendiente de integración, verificación del Apps Script vivo y despliegue. Este documento no acredita un trabajo ejecutado con datos reales.

El agente del PPP registra un storyboard visual en el catálogo existente de Presentaciones Master Developer. Cada registro conserva un `presentation_id`; las entregas usan `presentation_version_id`. El contador `revision` resuelve concurrencia técnica. `releaseRevision` conserva su significado de publicación y permanece vacío para estos paquetes privados. No se modifican cálculos, escenarios ni revisiones del PPP.

## Archivos y fuentes de verdad

- `gas/PresentacionesDominio.gs`: espejo del contrato puro `presentacion/registry-core.js` del board. Controla identidad, revisión esperada, padres, recibos y etapas.
- `gas/PresentacionesStoryboard.gs`: espejo del adaptador de datos `presentacion/storyboard-core.js`. Rechaza código, diagramas no soportados y referencias inválidas; produce una proyección explícita sin guion ni referencias internas.
- `gas/PresentacionesYOD.gs`: adaptador al despliegue y carpeta privada existentes. Sirve el mismo catálogo, identidad Portero, almacenamiento y chinches.
- `gas/PresentacionesAgente.gs`: puente del worker. Recibe la prueba firmada íntegra y consulta al Portero que la emitió.

El PPP sigue siendo la fuente financiera. La copia privada guardada identifica caso, PPP, escenario visto, revisión PPP, revisión del expediente, tipo de modelo y SHA256 del snapshot. El artefacto guarda narrativa y referencias a ese snapshot; no es un segundo modelo financiero.

## Transporte autenticado

Se reutiliza `doPost` con `accion: "presentaciones"`. Las peticiones del navegador siguen usando `presentation` y la identidad actual de Portero. El worker usa `{accion: "presentaciones", proof: <petición original firmada>}`. No se acepta un rol enviado por el navegador, una clave de propietario ni una URL de servicio del llamante.

Sala consulta el `PORTERO_EXEC` existente con `tipo: "despacho-v1"`, `operation: "presentationPermit"`, `payload: {case_id, proof}` y el objeto `worker` original. Comprueba respuesta afirmativa, propietario vigente, correo, caso, PPP, operación y SHA256 de la serialización canónica del payload. Portero conserva la verificación de firma, ACL y vigencia; Sala no incorpora una clave compartida nueva.

Payload común: `case_id`, `board_case_id`, `worker_id`, `actor_id`.

| Operación firmada | Campos adicionales | Resultado |
| --- | --- | --- |
| `presentationRegister` | `presentation_id`, `request_id`, `registration`, `lease` | Versión y recibo releídos, origen, hash del artefacto y URL canónica |
| `presentationReceipt` | `presentation_id`, `request_id`, `job_id`, `presentation_version_id`, `source_hash` | El mismo resultado guardado o `found:false`; no genera contenido |
| `presentationList` | Ninguno | Metadatos de versiones del caso/PPP autorizado, sin cuerpo del guion |
| `presentationAuthorization` | `presentation_id`, `presentation_version_id`, `authorization_id` | Autorización ya guardada por el propietario, origen, hash, revisión técnica y estado de versión vigente |

`registration` contiene `{op:"register_storyboard",id,requestId,data:{expectedRevision,version}}`. `version` contiene `presentation_version_id`, `parent_version_id`, `job_id`, `source`, `method_version`, `renderer_version`, `storyboard`, `stage` y `production_authorization_id`. `stage` predeterminado es `storyboard`; su autorización es nula. Los IDs de registro usan letras ASCII, números, guion y guion bajo, hasta 100 caracteres; `requestId` tiene al menos ocho.

`lease` conserva `job_id`, `worker_id`, `actor_id`, `lease_epoch`, `lease_expires_at` ISO, `request_id` y `source_hash`. Sala comprueba identidad, vinculación y expiración antes de registrar. La exclusión de una época antigua contra el journal durable pertenece al worker; Sala no afirma consultar ese journal. Añade revisión esperada, padre exacto e idempotencia. Consultar un recibo requiere autoridad firmada vigente, pero no una lease de ejecución vigente.

El resultado de registro/recibo contiene `ok`, `found`, `request_id`, `case_id`, `presentation_id`, `presentation_version_id`, `source`, `artifact_hash`, `receipt`, `url` y `version` sin cuerpo. `artifact_hash` es SHA256 de `YODPresentationsDomain.stable(YODStoryboard.normalize(storyboard))`. Los listados añaden `registry_revision` y `latest` a cada versión. Un resultado ambiguo se concilia por recibo antes de repetir la escritura.

## Persistencia y recuperación

Los originales están en la carpeta privada ya configurada por `YOD_PRES_FOLDER_V1`. `YOD_PRES_INDEX_V1` conserva sus registros anteriores. Una extensión privada de ese mismo índice evita el límite de 9 KB de un valor ScriptProperties; su puntero es `extensionFileId` dentro del índice actual. No crea otro catálogo, aplicación ni backend. Los registros generados carecen de datos privados en el JSON público de GitHub.

Drive y ScriptProperties no proporcionan una transacción distribuida. Bajo el candado existente, se guarda el archivo con nombre determinista, se enlaza el índice y se relee el resultado. Una respuesta perdida después de crear el archivo puede dejar el enlace pendiente. El recibo localiza ese archivo, valida solicitud, actor, versión, job y origen, y completa únicamente el enlace. No regenera, sustituye ni borra el contenido. Duplicados por nombre o huellas inconsistentes se rechazan. La extensión admite hasta 500 registros; cada archivo tiene un límite de 8 MB para las actualizaciones. Alcanzar un límite requiere mantenimiento explícito, no purgar historia.

Los nuevos registros son privados aunque sus indicadores públicos se alteren por error: el dominio los excluye del catálogo público, lecturas públicas, sesiones heredadas y catálogo de brokers. Las chinches del visor genérico se filtran por `presentation_id` o pantalla específica, además del origen, para que quitar parámetros de URL no mezcle casos.

## Storyboard, instrucción y producción

La primera entrega queda como `storyboard`, `ready_for_review`. `authorize_production` exige propietario verificado, revisión técnica esperada, versión exacta e instrucción `produce_presentation`; registra un evento y recibo sin cambiar el artefacto. El worker sólo puede consultar esa autorización y generar una nueva versión después.

Registrar `stage:"presentation"` exige una autorización existente del mismo actor, un padre storyboard exacto, y la fuente completa y hash originales. Conserva las dos versiones. Producir no publica ni inicia una sesión pública. `read_projection` requiere propietario, versión producida y el adaptador explícito que elimina `spoken`, `question`, `source_ref` y audiencia; conserva condiciones materiales. No hay publicación anónima de estos paquetes en este cambio.

## Verificación y activación

Pruebas sintéticas ejecutadas: registro, replay, respuestas perdidas, recuperación de índice, denegación de firma/ACL, revocación, lease vencida, fuentes cruzadas, padre/revisión, autorización de etapa dos, proyección privada, permisos de Drive y chinches de casos distintos. `tests/presentaciones-agente-gas.test.cjs` simula al emisor Portero; no demuestra una conexión productiva real. Las pruebas del dominio y renderer viven también en el board.

Antes de activar: comparar con el Apps Script vivo, conservar respaldo privado, instalar los cuatro módulos compatibles en el despliegue existente y comprobar Portero `presentationPermit` y su forward. La propiedad `YOD_PRESENTATION_SALA_ENDPOINT_V1` del Portero señala la URL de Sala ya existente; no contiene una credencial. La activación del piloto y del agente es independiente de guardar este código. Verificar lectura exacta del escenario, recibo y navegación con un caso sintético aislado antes de cualquier cliente.

Reversión: desactivar el alcance de presentaciones en el agente/Portero y revertir código mediante revisión. Conservar archivos, extensión del índice, snapshots, autorizaciones, recibos y chinches. El índice original permanece legible para el código anterior; las versiones generadas dejan de ofrecerse mientras la capacidad esté desactivada. No restaurar ni borrar datos de negocio.
