# Imágenes nuevas fuera del bundle de Pages

La fase1 mantiene todos los archivos y URLs históricos de Git y snapshots. Sólo
considera PNG/JPG/JPEG/WebP nuevos de `laminas/`, ausentes de Git y del snapshot
base. No mueve videos, audio, originales de Drive ni ZIP privados. El límite
de900MiB se conserva; esta fase no añade capacidad ilimitada ni rebaja huellas.

El emisor está apagado por defecto. `SALA_MEDIOS_PUBLICOS=1` permite un lote
sólo cuando el lector del HEAD aprobado ya está servido y una corrida exitosa
de `publicar.yml` lo acredita independientemente. El lote se valida y decodifica,
se sube a un release del mismo repositorio y sólo devuelve referencias tras
comprobar inmutabilidad y descargar sus bytes anónimamente con hash exacto.
No transmite claves a las URLs públicas ni guarda redirecciones firmadas.

El tag identifica el contenido del lote, no el runner. Ante respuesta perdida
o un runner nuevo, consulta la identidad remota antes de crear otro objeto.
Un checkpoint local por sí solo no prueba una escritura remota.

`datos/medios-publicos.json` conserva ruta lógica, SHA256, bytes, MIME, release,
asset y URL estable. El snapshot FULL conserva ese mapa y omite únicamente
los bytes externos verificados; bootstrap/stage los hidratan para Mesa y
cortadores. Pages conserva los históricos y omite las imágenes nuevas del mapa.
`version-online.json.media_manifest_sha256` fija los bytes exactos del mapa.
La interfaz verifica ese pin y cierra la aprobación mientras se valida o falla.

## Activación verificable

1. Integrar el lector, comprobar CI y el recibo Pages del código exacto.
2. Ejecutar `sonda-medios-publicos.yml` con `aplicar=false`: sólo consulta.
3. Comprobar y habilitar la protección de releases inmutables del repo existente.
4. Ejecutar una vez la sonda con `aplicar=true`: publica sólo un PNG técnico8×8
   neutro, sin Sheet, Drive ni manifiesto de producción. Exigir bytes/dimensiones
   y reentrada con cero mutaciones en la segunda instancia.
5. Sólo tras esos recibos cambiar la variable del repositorio a1. Leer la siguiente
   producción real y su manifiesto/recibo; no inventar una pieza para llenar cola.

El lector histórico tiene su propia bandera y despliegue de AppsScript; no se
activa al habilitar medios. La emisión incremental sigue separada y apagada.

## Reversión

Apagar el emisor conserva referencias ya publicadas y el lector compatible.
No revertir a un lector antiguo después de emitir manifiestos: primero habría
que repatriar y verificar todos los bytes y demostrar que caben. Conservar
assets inmutables, mapas, snapshots, decisiones y los enlaces históricos.

La implementación y los tests no acreditan una sonda ni una producción real.
Los recibos de activación se registran por separado en la auditoría vigente.
