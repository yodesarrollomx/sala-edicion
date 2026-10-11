# Agregados de Plan en nube

La cuenta de servicio existente lee sólo columnas permitidas de la hoja canónica, con permiso lector. La configuración está en el documento privado «SALA · conexiones-online-v1» de Drive; no contiene credenciales y su búsqueda debe ser única.

El workflow sala-plan corre cada hora al minuto 25 y sólo en main aprobado. Identidad y diagnóstico se guardan en Drive privado, con bytes releídos. Ninguna fila se crea o modifica. Los folios quedan en memoria para deduplicar; PRUEBA se excluye. Cita requiere estado SESIÓN AGENDADA y fecha confirmada registrada; un clic o texto libre no cuenta. Se leen los campos de campaña/pieza y se publican únicamente conteos históricos y agregados.

La nueva salida datos/plan-agregados.json pasa por snapshots privados y Pages. version-online.json enlaza su SHA256. Los datos históricos no se presentan como leads del día. Si la fuente rechaza la cuenta de servicio, el workflow falla y conserva la última versión confirmada.

Las fuentes originales, inventario de Apps Script y correo siguen pendientes. No se sube el espejo GAS ni se cambia el formulario. Reversión por PR: retirar esta ruta y restaurar el último snapshot confirmado, conservar todas las hojas y retirar sólo el permiso lector específico si se añadió.

Si Sheets REST devuelve SERVICE_DISABLED, el cliente usa el protocolo de consulta Google Charts con la misma cuenta lectora y Authorization en cabecera. Primero consulta sólo encabezados (limit0); después sólo las columnas permitidas. No desactiva controles, no envía tokens en URLs y no usa ese respaldo para ocultar una denegación de permiso. Parseo JSON estricto, sin ejecutar JavaScript.
