# Continuidad de la revisión de tomas · 20 octubre 2026

Cambio técnico autorizado de SYS-SALA. Base: c528567c2b844f79f67fb5e10d8a4667c88a63b4. Atlas: PR290, 72a399021cfbf37e5f4b76a122b4fd9f3faf6fe7.

- Escritorio mayor de 900 px: dos tomas disponibles abren comparadas; móvil conserva una toma legible. El control permite cambiar de vista sin decidir.
- Aprobar por clic conserva la toma original elegida y avanza a la siguiente lámina pendiente, en orden circular. La cola no se rellena y ninguna otra página se aprueba por navegar. Sin pendientes, conserva la página y remite al indicador real de guardado.
- Una lámina aprobada con fuente original conocida admite pedir cambio con nota obligatoria. Usa `reabrirAprobada` existente y conserva la historia. Se revalida sesión, versión y origen al confirmar. Consulta fresca del inventario no habilita aprobar de nuevo; sólo admite esta petición explícita cuando existe `t.base`.

No cambia carga, medios, productor, cola, credenciales ni decisiones editoriales. Una solicitud de cambiar el contenido requiere su dirección editorial específica; arreglar el botón no acredita que la nueva imagen exista.

## Evidencia local

- `node --test tests/tablero-sala.test.cjs tests/mesa-local.test.cjs tests/sala-carga.test.cjs`: 32 PASS.
- `SALA_TEST_URL=http://127.0.0.1:8765/ CHROMIUM_EXECUTABLE_PATH=/tmp/sala-chromium SALA_CHINCHE_SOURCE=../atlas-review-20261020/chinche.js node tests/tablero-sala.browser.cjs`: PASS, Chromium, 1440/390, seis publicaciones y 36 láminas sintéticas. Comprueba comparación, avance tras aprobar, reapertura con nota, roles de lectura, selección original, gestos, contexto embebido y medios.
- `python3 nube/verificar.py`: 13 verificaciones PASS; incluye pruebas Python/Node con dobles y sello.
- `git diff --check`: PASS.
- QA visual de comparación de escritorio y recorrido móvil con datos sintéticos. Todas las escrituras Google están interceptadas por el test.

Esta evidencia no acredita una escritura real de un editor ni una nueva producción. Publicación y bytes servidos deben registrarse aparte. Rollback: revertir este PR sin borrar borradores, decisiones, medios ni historial.

## Publicación comprobada

PR354 integrado en 25e5b9dade0dc2c32fac3a0312dfbc13feb696ba. Checks del head702ba536030354162240b9b85132f3ebf2dd7f2b: navegador, verificar, Arquitectura YOD y regresiones SUCCESS. Publicación39448620966 SUCCESS. Bytes públicos cotejados: tablero-sala.js36960bytes SHA25656c74e45f1d798fb9878cd56144c9244263b04088e0ce5f67db03596db7dee4a; index.html293124bytes SHA256153f9f9581fee4169e1f55f598161b27e8a6db437aeb72255b859ca63969658b. Ambos iguales al código probado. version-online.json confirma ese merge y run, snapshot418538841; data_sha ca433dfde0f5d8d4ec131c19c9e997a48e926acab17e43dd0073e42411b99027. No acredita decisiones reales de editores.

Los marcadores #356 y #357 corresponden a las dos correcciones completas de navegación/comparación. #358 conserva pendiente la dirección editorial específica y la producción de una nueva lámina: la petición de revisión está reparada, pero no sustituye esa parte del encargo.
