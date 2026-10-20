# Chinches con audio y secuencia · entrega técnica

Estado: implementación en rama, pendiente de activación y verificación en producción. No es un recibo de despliegue.

Mecánica compartida: audio MediaRecorder, lápiz/marcador/formas, tiempo por punto, deshacer, capturas intermedias y reproducción sincronizada. Se conserva contexto y archivo local; la entrega sólo se confirma por ID y SHA256. No se sustituye un audio fallido por texto ni se publica contenido privado en issues.

Fuentes centrales: yod-portal/chinche/secuencia.js y entrega.js. `scripts/chinche-bundle.cjs` actualiza core y copia de presentaciones. Amalaya y EMD incorporan el mismo grabador y conservan sus autenticaciones/bandejas. Las superficies técnicas privadas no capturan nombres ni respuestas automáticamente.

## Instalación pendiente

1. Comparar código VIVO y despliegue existente de cada Apps Script con el cambio del PR; respaldar la fuente privada. El espejo público no sustituye la fuente viva.
2. Sala: agregar ChincheSecuencia.gs y el despacho de acciones acotado a doPost; configurar carpeta privada mediante configurarChincheSecuencia. Conservar roles, URL /exec y demás funciones. Revisar autorización de Drive del propietario. Nunca crear otra implementación ni cambiar compartición.
3. Amalaya: agregar ChincheSecuencia.gs y adaptador Code.gs al motor existente, conservando CARPETA_ID y roles. EMD: igual con FOLDER_ID, regenerar Index.html; la columna M de Chinches guarda hash de secuencia, sin desplazar A:L. Conservar acceso por autor y separación QA.
4. Actualizar versión de la implementación EXISTENTE, comprobar identidad, permisos y lectura. No utilizar registros productivos ficticios como pruebas. Activar los consumidores sólo después de confirmar la capacidad de almacenamiento.
5. Verificar una entrega real autorizada: archivo privado completo, mismo ID/hash, reproducción de audio y pasos, recuperación tras recarga y revisión desde otra sesión autorizada. No cerrar el encargo sin esta evidencia.

Revisor diario ampliado y releído el20oct: misma rutina08:00Hermosillo; todas las superficies detectadas, descubrimiento de faltantes y paquetes completos. La rutina no puede observar IndexedDB de todos los aparatos.

## Evidencia local y límites

Portal:856 pruebas y verificadores OS/portal/accesos/obra. Presentaciones:151 pruebas. Sala:verificador sin red y4 pruebas de almacenamiento/idempotencia/roles/integridad. Grabador:prueba Chromium con MediaRecorder y micrófono simulado, trazos/capturas/reproducción en390/768/1280px. Amalaya:build y pruebas. EMD:comprobación local separada. Estos resultados no acreditan permisos del micrófono en Safari real ni backend publicado.

Bloqueo de activación observado: navegador de nube sin sesión Google, Apps Script redirige a página pública. No se ha editado el servidor ni ampliado permisos. Mantener PR en borrador hasta completar integración y QA nativa. No sustituir faltantes por una demo.

Reversión: revertir cambios de código, conservando IDs, paquetes, recibos y borradores. No borrar registros ni archivos privados.
