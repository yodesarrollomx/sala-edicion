# Última mesa guardada: implementación de hipótesis 2

Solicitud de Dirección: abrir la última mesa guardada y actualizar en segundo plano.

## Comportamiento

- Guarda día y grupos de publicaciones después de una lectura vigente con inventario y tiras disponibles.
- Reapertura por la misma sesión/rol/endpoint: consulta inmediata, fecha visible, navegación y comparación; el servidor actualiza en segundo plano.
- No usa la copia para restaurar permisos. Votos y nuevas decisiones esperan la mesa vigente; borradores y cola permanecen separados.
- Rechazo de credencial retira la copia; sesión distinta, caché caducada/corrupta, cuota o almacenamiento no disponible conservan la ruta de carga normal.
- No guarda claves renovadas ni tokens en el snapshot. La huella de sesión usa SHA256. Caducidad: siete días; tamaño acotado.
- La primera visita necesita descargar datos. Los medios conservan sus controles existentes; no se copian videos ni imágenes a localStorage.

## Verificación local

44 pruebas Node de caché, carga, imágenes, tablero y proyección; 13 compuertas de `nube/verificar.py`. Navegador Chromium con datos sintéticos a 1440 y 390 px: la mesa aparece y se navega antes de liberar la respuesta del servidor; las notas/decisiones se conservan al actualizar; la red caída conserva consulta; el rechazo y otra sesión retiran la copia. Cero POST y cero errores de página en el recorrido.

La marca Performance `sala-mesa-local-visible` se registra después de dos frames al restaurar. Se observaron lecturas de 134/149 ms y 154/158 ms en corridas controladas, y una de 1915 ms bajo carga variable del runner. Por eso la prueba registra el tiempo y exige independencia de la respuesta del servidor; no convierte ese entorno variable en un SLA. No hay p95 medido ni garantía de menos de un segundo en producción.

## Publicación

Dirección autorizó expresamente publicar el registro de arquitectura y completar el despliegue el 20-oct-2026. Atlas: PR [yod-portal#288](https://github.com/yodesarrollomx/yod-portal/pull/288), commit `b4efa45afa3d9515696bd83c6f10a8521bec033d`. El árbol publicado coincide con el árbol local validado. El consumidor fija ese commit; la integración y el despliegue se acreditan con los recibos de CI y Pages del PR.

## Reversión

Revertir el PR del frontend. La clave `sala_mesa_local_v1` puede ignorarse o eliminarse; conservar `sala2-*`, `sala_cola`, decisiones, Sheets, cola editorial, snapshots y medios.
