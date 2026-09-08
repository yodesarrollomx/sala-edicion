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

---

# Lo que encontró el enjambre (primera vuelta, 8-sep)

4 hallazgos confirmados de 6 reportados. Los 2 graves habrían roto el sistema en la siguiente
publicación:

| # | Qué | Por qué importaba |
|---|---|---|
| 1 **rompe** | `sala_catalogo.py` **borraba los ids de Drive** al reconstruir (607 líneas menos por corrida) | y el publicador lo llama al montar: **la próxima publicación habría dejado el catálogo sin sus fotos** |
| 2 **rompe** | `sala_publicar.py` montaba la pieza en la mesa **antes** de catalogarla, con un `except` que solo imprimía | una falla de red dejaba una carta viva **sin serial**: justo lo que produce los duplicados |
| 3 molesta | el respaldo de `montarImagen()` bajaba el **PNG maestro de 1.8 MB** al teléfono | pasaba justo cuando la señal está mal, que es cuando más duele |
| 4 molesta | `vigilante.py` apuntaba a los repos en el Escritorio | quedó ciego cuando se movieron a `~/Repos` |

Y uno mío, visto en su Chrome: **el catálogo llegaba después del pintado** y las fotos seguían
saliendo del repo; además el navegador **cacheaba** la respuesta del catálogo.

## Cómo quedaron

1. `construir()` **fusiona** con lo guardado: la huella es la identidad, así que una revisión que
   conserva su huella conserva sus ids de Drive. Probado corriéndolo dos veces seguidas: 115 de 115.
2. **El catálogo primero, la mesa después.** Si el catálogo, Drive o el Sheet fallan, la pieza
   **no se monta** (`sys.exit`), en vez de llegar sin serial.
3. El respaldo cae a la **ligera del repo**, nunca al maestro.
4. `vigilante.py` → `~/Repos`.
5. `traerCatalogo()` **repinta** al llegar y la liga lleva el sello (`cache:'no-store'`).

## Comprobado en su Chrome (8-sep)

| Puerta | Resultado |
|---|---|
| P1 · llave cerrada | `find ~/Desktop -name .git` = **0** |
| P2 · catálogo | 49 láminas · 115 revisiones · **142 rutas** · 115 ids de Drive |
| P3 · sólo letras | **29 imágenes, las 29 de Drive**, 0 del repo, **0 maestros .png** |
| P4/P5 · guardia | repetida **bloquea**; dinero/gratis/plazo **3 de 3** |
| P6 · pantallas | Sala directa ✓ · máscara del OS ✓ · móvil 375 px sin desborde ✓ |
| serial a la vista | **APODO-L01 · revisión 3 de 3**, sobre la lámina |

Verificador: **15 verdes · 0 rojos**.


---

# Segunda vuelta del enjambre — y el hallazgo que valía por todos

La primera vuelta cerró 4 fallas. La segunda encontró una **peor**, y desmonta lo que yo había
dado por bueno:

## El serial se asignaba por POSICIÓN del archivo, no por la lámina real

Una carpeta montada casi nunca trae las láminas 1..N: trae **las que se rehicieron**. La tira
ya lo decía en su campo `mapa`, y yo nunca lo leí. `laminas/apodo-g5/L2.png` no es la lámina 2:
es la **3**.

| Archivo | Serial que le puse | El que le tocaba |
|---|---|---|
| `apodo-g5/L2.png` | APODO-L02 | **APODO-L03** |
| `apodo-g5/L3.png` | APODO-L03 | **APODO-L04** |
| `apodo-g5/L4.png` | APODO-L04 | **APODO-L05** |
| `apodo-g5/L5.png` | APODO-L05 | **APODO-L06** |
| `apodo-g5/L6.png` | APODO-L06 | **APODO-L09** |
| `comprador-g5/L1.png` | COMPRADOR-L01 | **COMPRADOR-L04** |
| `comprador-g5/L2.png` | COMPRADOR-L02 | **COMPRADOR-L07** |

Consecuencias reales que ya estaban en el catálogo:
- La rehecha de hoy de la **lámina 9** de El Apodo nunca llegó a `APODO-L09`: se guardó como
  `APODO-L06`. `APODO-L09` seguía mostrando la versión vieja.
- Las **cinco versiones de la lámina 4** de El Comprador estaban apiladas en `COMPRADOR-L01`,
  mientras `COMPRADOR-L04` se quedó atorada en la r2 del 3-sep.

Es exactamente la enfermedad que el catálogo venía a curar, en otra forma: **un serial que
cambiaba de identidad**. Sin este arreglo, el catálogo habría sido una capa de orden encima
del mismo desorden.

**Arreglado:** `_mapa_de(slug)` lee la tira y el número real manda sobre el nombre del archivo.
Después: catálogo reconstruido, archivo de Drive rehecho y registro del Sheet reescrito.

## Las otras dos de la segunda vuelta

| | Qué | Arreglo |
|---|---|---|
| **rompe** | La guardia bloqueaba **después** de copiar las láminas y escribir el manifiesto; como `empujar()` hace `git add -A`, la basura de una pieza rechazada viajaba en el push de otra | `_deshacer(slug, pid)`: si algo bloquea, se borran los archivos y se revierte el manifiesto |
| molesta | Con `SALA_FORZAR=1` el catálogo se saltaba en silencio y la pieza salía sin serial | ahora lo grita: «esta pieza va a la mesa SIN SERIAL» |

---

# Vueltas 3 a 6

| Vuelta | Qué salió | Cómo quedó |
|---|---|---|
| 3 | **rompe** · una carpeta con slug fuera de `PIEZAS` se descartaba **en silencio** y la pieza llegaba a la mesa sin serial | avisa por pantalla y el montaje se detiene |
| 4 | **rompe** · de las tres salidas por bloqueo, la del choque de id **no deshacía** su rastro | las tres deshacen |
| 5 | **rompe** · el registro de «ya vistas» se escribía **antes** de la guardia: la pieza se topaba consigo misma y `regla_no_repetir_lo_visto` **bloqueaba toda publicación con tira** | se anota al final, cuando la pieza ya pasó todo |
| 5 | **rompe** · `launch.json` y `settings.json` apuntaban a los repos en el Escritorio | 11 rutas → `~/Repos` |
| 6 | **cero hallazgos de código** | — |

La de la vuelta 5 era la peor de todas: lo que existía para impedir un duplicado impedía
publicar, y la única salida era `SALA_FORZAR=1`, que apaga **todas** las reglas de golpe.

## Lo único que queda abierto — y no lo puedo tocar yo

Google Drive Desktop **sigue espejando tres carpetas** de la Mac hacia
`direccion@aurumarquitectos.com`: **Escritorio, Documentos y Descargas**. Comprobado en su
propia base (`mirror_sqlite.db`, `root_state=1` en las tres, escrita hoy).

Mover los dos repos quitó el síntoma de hoy. La llave sigue abierta: cualquier repo, PDF de
cliente o captura que caiga en esas tres carpetas se sube igual.

**Es un ajuste de la app, en su cuenta.** Google Drive → Preferencias → *Carpetas de tu Mac* →
quitar el espejo de Escritorio, Documentos y Descargas. Lo tiene que hacer Alejandro.
