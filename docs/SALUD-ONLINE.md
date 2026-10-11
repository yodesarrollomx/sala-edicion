# Pruebas pequeñas de la Sala

Revisión autorizada de cola, reglas, rutinas y bitácora cada15min; mantiene observación diaria07:05Hermosillo. El correo permanece a07:00, sin correos de prueba adicionales.

Canario diario05:20Hermosillo: voz Kokoro real con texto sintético, figura sintética animada parallax, corte H264/AAC y archivo temporal de prueba subido/releído/retirado en `_prueba_nube`. No usa cola ni decisiones del negocio. Profundidad aproximada queda explicitada y no se certifican motores alternativos por esta prueba.

Resultados sanitizados en rama `salud-canario`, `estado-canario.json`; caducan36h. Un fallo actual reemplaza el éxito anterior; la publicación se relee byte exacto. El panel de Accesos consume resultados y horarios; el cron puede retrasarse y la edad real debe quedar visible.
