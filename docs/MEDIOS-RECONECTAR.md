# Reconexión de originales recuperados

El mantenimiento ejecuta el contrato CTR-SALA-RECONECTAR-MEDIOS aprobado en Atlas PR165. Usa el informe de recuperación único en la carpeta privada de conexiones; no incluye referencias de clientes o archivos en el código.

Antes de escribir verifica que las dos copias son WAV originales retenidos, con MD5/SHA256/tamaño exactos, y que cada trabajo existente está terminado, corresponde a voz y conserva ese MD5 y la referencia anterior. Prepara ambas filas antes de empezar; una discrepancia detiene la operación. Relee inmediatamente cada fila, actualiza sólo evidencia de archivo y procedencia y relee el resultado. Estados, motores, bloqueos, prioridades y decisiones se conservan. API heredada sin CAS atómico: los cambios detectados se rechazan y se registra antes/después para conciliar cualquier conflicto.

Workflow sin cron, activación por incorporación del código y manual posterior. Serializa con sala-ejecutor; secretos únicamente en main. Si la referencia ya corresponde al original recuperado, verifica sin reescribir. Guarda y relee el acuse completo en Drive privado antes y después; el log público muestra sólo conteos y error tipificado. Distingue intentos de escritura de actualizaciones confirmadas.

Pruebas sintéticas cubren corrupción, copia equivocada, MD5 original, filas activas/duplicadas, evidencia inválida, concurrencia, acuse rechazado, campos conservados e idempotencia. No se hacen escrituras de prueba en producción. La aplicación real es la reparación autorizada de referencias originales.

Estado inicial: implementación preparada; ejecución y acuse reales se registrarán en el Atlas. No cierra inventario de Apps Script/correo ni otros medios históricos no localizados.

Reversión: detener/revertir workflow; conservar acuses y medios. Conciliar sólo referencia técnica previa contra lectura reciente, nunca restaurar hojas completas o cambiar aprobaciones.
