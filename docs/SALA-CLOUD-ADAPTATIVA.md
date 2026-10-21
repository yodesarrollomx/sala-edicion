# Producción adaptativa en nube

La ejecución vive en GitHub Actions con las APIs ya conectadas y Drive/Sheets. No depende de la Mac ni de una sesión Claude/Codex. No se habilitan planes de pago.

`nube_adaptativa=1` es el valor por omisión autorizado. `0` restaura el selector anterior. `motores_vetados` es una lista separada por comas en REGLAS y siempre prevalece. MOTORES conserva encendido, costo y tope_dia. El motor `codigo` es CPU en Actions y puede apagarse con ese veto o una fila propia apagada. No se reutilizan cámara/parallax retirados.

Entre motores gratuitos implementados, el 80% de los trabajos prioriza puntuación y el 20% explora otro disponible. El hash del ID hace la decisión repetible. Actualmente escenas: Wan y código; voces: las filas gratuitas activas con adaptador Gemini/Kokoro. No se activa Kokoro sin fila autorizada. Imágenes conserva su circuito HiDream actual; no se declara integrada una API sin conexión comprobada.

Antes de consumir se reserva uso diario en COLA; un fallo no devuelve cuota. Los saldos externos que no publica el proveedor son desconocidos. Una respuesta de cuota suspende ese motor durante una hora; tres fallos técnicos recientes también. Esto no baja la puntuación editorial. Los topes son por intento de trabajo, no por token externo.

El pintarrón tipográfico se renderiza con Pillow/FFmpeg en CPU durante toda la voz durable, con paginación del texto aprobado, trazos progresivos y movimiento continuo. Se identifica como `animacion_codigo`, nunca como generativa. Una voz mayor de cinco segundos salta Wan por incompatibilidad de duración. Si todas las alternativas están vetadas/agotadas, la cola espera con motivo explícito.

La descripción de cada corte muestra motores y formatos. Revisiones firmadas puntúan sólo dependencias del corte efectivamente revisado. Puntuación por etapa; clasificación más fina por estilo/tarea requiere muestras suficientes y no está activada. No se cambia ninguna decisión ni aprobación.

Verificación: pruebas aisladas del selector, topes, vetos, exploración, duración y render MP4 real. Producción sólo se acredita con archivo durable y recibo de entrega. Revertir por PR y `nube_adaptativa=0`; conservar todo el historial.
