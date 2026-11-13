# Producción adaptativa en nube

La ejecución vive en GitHub Actions con las APIs ya conectadas y Drive/Sheets. No depende de la Mac ni de una sesión Claude/Codex. No se habilitan planes de pago.

`nube_adaptativa=1` es el valor por omisión autorizado. `0` restaura el selector anterior. `motores_vetados` es una lista separada por comas en REGLAS y siempre prevalece. MOTORES conserva encendido, costo y tope_dia. El motor `codigo` es CPU en Actions y puede apagarse con ese veto o una fila propia apagada. No se reutilizan cámara/parallax retirados.

Entre motores gratuitos implementados, el 80% de los trabajos prioriza puntuación y el 20% explora otro disponible. El hash del ID hace la decisión repetible. Actualmente escenas: Wan y código; voces: las filas gratuitas activas con adaptador Gemini/Kokoro. No se activa Kokoro sin fila autorizada. Imágenes conserva su circuito HiDream actual; no se declara integrada una API sin conexión comprobada.

Antes de consumir se reserva uso diario en COLA; un fallo no devuelve cuota. Los saldos externos que no publica el proveedor son desconocidos. Una respuesta de cuota suspende ese motor durante una hora; tres fallos técnicos recientes también. Esto no baja la puntuación editorial. Los topes son por intento de trabajo, no por token externo.

El pintarrón tipográfico se renderiza con Pillow/FFmpeg en CPU durante toda la voz durable, con paginación del texto aprobado, trazos progresivos y movimiento continuo. Se identifica como `animacion_codigo`, nunca como generativa. Una voz mayor de cinco segundos salta Wan por incompatibilidad de duración. Si todas las alternativas están vetadas/agotadas, la cola espera con motivo explícito.

La descripción de cada corte muestra motores y formatos. Revisiones firmadas puntúan sólo dependencias del corte efectivamente revisado. Puntuación por etapa; clasificación más fina por estilo/tarea requiere muestras suficientes y no está activada. No se cambia ninguna decisión ni aprobación.

Verificación: pruebas aisladas del selector, topes, vetos, exploración, duración y render MP4 real. Producción sólo se acredita con archivo durable y recibo de entrega. Revertir por PR y `nube_adaptativa=0`; conservar todo el historial.

## Motor de pago autorizado: `omni_flash` (9-nov-2026)

Excepción expresa de Dirección a «no se habilitan planes de pago»: Gemini Omni Flash por la API oficial de Gemini, con la `GEMINI_API_KEY` que ya usa la voz. Cuesta alrededor de 0.07 USD por segundo en 720p y no tiene nivel gratuito; la llave necesita facturación activa en Google AI Studio.

Nace apagado. Se enciende con la REGLA `omni_flash_tope_dia` = número de clips permitidos por día (vacío o 0 = apagado). Una fila encendida en MOTORES no basta sin esa regla, y `motores_vetados` sigue prevaleciendo. La reserva se registra antes de llamar: un intento fallido también gasta el tope, así que el gasto diario máximo es tope × 15 s × precio.

Orden cuando está autorizado: Wan gratis primero si la voz cabe en 5 s; después Omni (voces de hasta 15 s; pide segundos enteros que cubren la voz, mínimo 3); la animación por código queda como último recurso y sigue cubriendo voces de más de 15 s. El audio de Omni se descarta: la voz aprobada la pone el corte. `escena_omni_modelo` permite fijar otro identificador de modelo.

Pendiente de acreditar: el contrato de la API no se ha probado en vivo. `response_format.duration` proviene de guías de terceros; la primera corrida real con archivo durable y recibo es la evidencia. Apagar: `omni_flash_tope_dia=0`.

## Piloto de historias de 15 segundos (9-nov-2026)

Dirección pidió historias de 15 s en una sola toma, con personajes que se guardan y tramas que se cruzan. El piloto es UNA historia generada sólo de texto, con la voz y los labios del propio Omni (el motor de escena de arriba, en cambio, anima láminas y descarta el audio).

- `datos/universo/universo.json` guarda formato, vértices del negocio, personajes, lugares e historias. Es la semilla; la meta es que viva en el Sheet y se edite desde la Sala. El código no contiene texto de contenido.
- `nube/piloto_omni.py <historia>` arma el prompt, pasa el veto de ubicaciones y genera. `--simular` no llama a nadie.
- `.github/workflows/sala-piloto-omni.yml` lo corre sólo a mano. No pasa por la COLA ni por `nube_ejecuta_etapas`: la producción de video sigue en pausa. Sube el MP4 a Drive (`_PILOTOS`) y lo deja como artefacto.
