# Plan · dejar todo en orden (8-sep-2026)

Objetivo de Alejandro: «dame el plan de acción para dejarlo todo perfecto… déjamelo probado y
funcionando desde mi Chrome». Meta medible: **el ciclo completo corre de punta a punta sin que
él tenga que corregir nada** — una lámina nueva entra con serial, se archiva en Drive, se
registra en el Sheet, aparece en su mesa, él decide, y la decisión regresa; y nada de lo que ya
vio le vuelve a aparecer.

## Estado al empezar

| | |
|---|---|
| ✅ Serial por lámina | 49 láminas, 115 revisiones, `datos/catalogo.json` |
| ✅ Archivo en Drive | 230 archivos, original + prueba sellada |
| ✅ Registro en el Sheet | pestaña `CATALOGO`, `recurso=catalogo` (35 KB de texto) |
| ✅ La Sala pide la foto a Drive | `ligera()` / `original()` / `serialDe()` |
| ✅ La guardia bloquea | 10 reglas, incl. no repetir lo ya visto |
| ✅ Se cerró la llave del Drive | los 2 repos salieron del Escritorio espejado |
| ⬜ Falta | probarlo con sesión real en su Chrome |

## Las seis puertas (nada se cierra sin su comprobación)

1. **P1 · La llave cerrada.** Cero `.git` en el Escritorio; Drive deja de crear carpetas basura.
   *Se comprueba:* `find ~/Desktop -name .git` = 0, y sin lotes nuevos en Drive mañana.
2. **P2 · El catálogo cuadra con la realidad.** Toda lámina de la mesa tiene serial, su revisión
   coincide con su huella, y su liga de Drive responde.
3. **P3 · La Sala carga sólo letras.** Con sesión: el día y el catálogo son texto; ninguna imagen
   sale del repo si Drive la tiene; el serial se ve en la carta.
4. **P4 · El ciclo completo.** Montar una pieza de prueba → aparece con serial → decidir →
   la decisión llega al Sheet → no vuelve a preguntar.
5. **P5 · Nada duplicado.** Ninguna carta repite una lámina ya vista; ninguna pieza publicada
   regresa a la mesa.
6. **P6 · Probado en su Chrome.** Las tres pantallas (OS, Sala directa, móvil) sin errores.

## El enjambre (Sonnet, pocos y dirigidos — regla del 8-sep)

| Agente | Qué revisa | Cómo lo prueba |
|---|---|---|
| `catalogo` | P2 | corre `sala_catalogo.py`, compara huellas contra `catalogo.json`, pide cada liga de Drive |
| `sala` | P3 | lee `index.html`: que `ligera/original/serialDe` estén enganchados y el JS sea válido |
| `ciclo` | P4+P5 | contra el GAS real: catálogo, día, guardia; que la guardia detenga una repetida |
| `limpieza` | P1 | que no vuelva a entrar basura y que nada en la Mac apunte a las rutas viejas |

Cada uno **sólo reporta hallazgos verificables**, con el comando que los reproduce. Yo aplico
los arreglos; los agentes no escriben en producción.

## Cierre

El ciclo se repite hasta que **dos vueltas seguidas salgan limpias**. Después: la prueba en su
Chrome con su sesión, y la mesa lista con lo que le falta decidir.
