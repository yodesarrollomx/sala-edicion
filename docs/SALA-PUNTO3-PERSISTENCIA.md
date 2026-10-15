# Punto 3 · ejecución persistente y recuperable

Se implementa el proceso integral de interacción especificado en los puntos 1 y 2. La unidad de trabajo es una toma de una fuente vigente, con sus entradas, variante y política. Las decisiones editoriales siguen perteneciendo a los editores.

| Situación | Comportamiento |
|---|---|
| «No cambies el texto» o corrección sólo visual | Conserva el texto original; una prohibición expresa prevalece ante ambigüedad |
| Corrección visual y traductor sin respuesta | Pendiente; nunca presenta como corregida una receta que omitió la nota |
| Texto nuevo | 1–14 palabras separadas por espacios, sin truncar; la salida inválida sigue la cascada acotada o queda pendiente |
| Texto histórico sin edición | Se conserva; el nuevo límite no reescribe aprobaciones previas |
| Recuperación HiDream por recibo | Devuelve la huella de la receta original, aunque la consulta de recuperación sea distinta |
| Resultado privado confirmado | Recupera bytes y metadatos; no llama otra vez al cerebro ni al motor de imagen |
| Envío incierto | Consulta recibo del proveedor sin generar; si falta confirmación, requiere conciliación |
| Cuota HiDream explícitamente rechazada sin imagen | Permite otro intento en otra ejecución; no activa pago ni repite en el mismo intento |
| Entrada, referencia o fuente distinta | Identidad nueva; se conservan los registros anteriores |

## Conexión con el circuito existente

Arranque conserva su guion en un draft privado antes de producir la primera toma. Mesa y Arranque usan `sala_recibos.py` para guardar plan, envío y resultado, mediante la identidad nativa del workflow. El lease existente serializa la ejecución. La identidad de la toma depende de fuente/entradas/variante/política, no de la fecha de la carpeta de salida.

El plan conserva las entradas, la referencia **descriptiva**, llamadas de cerebro efectivamente intentadas con instrucción/modelo, configuración permitida sin credenciales y prompt entregado al adaptador de imagen. El resultado conserva bytes, hash, modelo y parámetros confirmados disponibles. HiDream recibe el prompt completo; otros adaptadores conservan sus transformaciones específicas y no se presenta este registro como captura HTTP universal.

Los recibos son releases **draft** de tipo `yod-sala-ejecucion-privada`. Cada activo es inmutable y se relee después de guardar. Una respuesta perdida se concilia por identidad y contenido. No se publican esos drafts; `snapshots_online.latest` sólo admite el tipo público anterior. Los prompts no se escriben en el checkout, Pages, logs ni filas públicas. No se guardan claves en el plan.

Una llamada al proveedor puede quedar incierta si el proceso muere antes de conservar el resultado. No se promete ejecución exactamente una vez de un proveedor sin tal contrato. Ese caso queda pendiente y se consulta su recibo; nunca se repite a ciegas. La conciliación manual de un proveedor sin recibo no forma parte de una aprobación editorial.

Tras recuperar o producir una toma, el compositor, snapshot, Pages, montaje, Productor y Ejecutor mantienen sus compuertas actuales. Esta entrega no cambia voces, chinches, selección de finalistas ni publicación externa: esos contratos se abordan en los bloques siguientes.

## Validación y operación

- `python3 -m unittest discover -s tests -p '*_test.py'`
- `node --test tests/*.test.cjs tests/*.test.mjs`
- `python3 nube/verificar.py`
- Workflow «Sala · recuperación entre runners»: primer job guarda un plan y bytes sintéticos en un draft real; segundo job usa otro runner y recupera sin llamar planificador/generador. No usa modelos, credenciales de negocio, votos ni Sheets.

La prueba entre runners acredita almacenamiento y continuidad independientes de esta conversación. No acredita por sí sola disponibilidad de un motor, calidad de una lámina real, cierre físico del chat, ni recepción de un correo. El punto 5 cubre la medición de casos reales.

Reversión: revertir el PR y conservar drafts privados, snapshots, imágenes, guiones, decisiones y colas. No borrar historial ni publicar recibos para recuperar acceso. Para una entrada cambiada, usar su nueva versión; no editar activos existentes.
