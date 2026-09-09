# Prueba celda por celda · el supuesto ESCRITO ANTES de tocar el navegador

*8-sep-2026. Pedido de Alejandro: «¿dónde está el documento inicial de lo que cada renglón y celda
va a decir ANTES de que tú hagas la prueba en el navegador actuando como si fuera yo? Y luego me
comparas las dos respuestas y me dices qué sucedió y por qué real de lo que cambió, y me propones
una estrategia para cada uno de los puntos donde no salió como decía el renglón.»*

**Este documento se escribe primero y no se edita después.** Lo que salga distinto se anota abajo
en la sección de comparación, no se corrige aquí arriba. Si lo corrigiera, la prueba no valdría.

---

## 0. Qué se prueba y sobre qué

Se monta una **pieza desechable** de 3 láminas para no tocar las 7 decisiones reales que están
esperando en la mesa.

| | |
|---|---|
| carpeta | `/tmp/prueba_celdas` |
| slug | `prueba-celdas` |
| **prop_id que debe salir** | **`prueba-celdas-3e54c4`** (= slug + sha1 de la carpeta, 6 hex) |
| láminas | 3 (copias de láminas ya existentes, para no generar imágenes) |
| fecha | la que dicte el GAS (`2026-09-08`), nunca el reloj de la Mac |

**Riesgo asumido y por qué es aceptable:** el sobre que manda la Sala incluye TODAS las piezas del
día, así que las reales viajarán con marca `pendiente`. Por la invariante 11 («pendiente nunca
borra»), eso no puede tocar nada de lo suyo. Si esa invariante falla, la prueba lo va a demostrar
— y sería el hallazgo más grave del día.

## 1. Las 10 columnas de la hoja DECISIONES

`envio_id · quien · guardado · fecha · prop_id · lamina · marca · nota_propuesta · nota_dia · nota_estrategia`

Regla que leí en el código del GAS (no supuesta): **cada envío escribe, por cada pieza del día,
una fila por lámina + una fila de nota de pieza; y al final una fila de cierre del día.**

## 2. Los 5 actos, y lo que cada uno debe escribir

Voy a actuar como editor en el navegador, sobre `prueba-celdas-3e54c4`:

| # | Acto en pantalla | Lámina |
|---|---|---|
| 1 | clic en **Aprobar** | 1 |
| 2 | clic en **Pedir cambio** + escribo `prueba: entonación de pregunta` | 2 |
| 3 | clic en **Aprobar** | 3 |
| 4 | **Deshacer** la lámina 3 | 3 |
| 5 | clic en **Pedir cambio** + escribo `prueba: la imagen no sostiene el argumento` | 3 |

### Lo que cada celda debe decir (predicción)

**Acto 1 — Aprobar lámina 1.** Un sobre nuevo. Filas de la pieza de prueba:

| envio_id | quien | guardado | fecha | prop_id | lamina | marca | nota_propuesta |
|---|---|---|---|---|---|---|---|
| `<uuid A>` | `editor` | sello del GAS | 2026-09-08 | prueba-celdas-3e54c4 | `0` | **`si`** | *(vacío)* |
| `<uuid A>` | `editor` | " | " | prueba-celdas-3e54c4 | `1` | **`pendiente`** | *(vacío)* |
| `<uuid A>` | `editor` | " | " | prueba-celdas-3e54c4 | `2` | **`pendiente`** | *(vacío)* |
| `<uuid A>` | `editor` | " | " | prueba-celdas-3e54c4 | *(vacío)* | *(vacío)* | *(nota de pieza, vacía)* |

Más una fila de cierre con `prop_id` vacío, y filas `pendiente` para las piezas reales del día.

- `lamina` es el **índice base 0**, no el número de lámina.
- `quien` debe decir **`editor`** (el rol), no «Alejandro».
- `guardado` lo pone el GAS con hora de Hermosillo; **no** debe salir 7 horas atrás.

**Acto 2 — Pedir cambio + nota, lámina 2.** Sobre nuevo `<uuid B>`:

| prop_id | lamina | marca | nota_propuesta |
|---|---|---|---|
| prueba-celdas-3e54c4 | `0` | **`si`** | *(vacío)* |
| prueba-celdas-3e54c4 | `1` | **`no`** | **`prueba: entonación de pregunta`** |
| prueba-celdas-3e54c4 | `2` | `pendiente` | *(vacío)* |

La marca de la lámina 1 debe **repetirse** en este sobre: la Sala manda el borrador completo.

**Acto 3 — Aprobar lámina 3.** Sobre `<uuid C>`: `0=si`, `1=no` con su nota, `2=si`.

**Acto 4 — Deshacer lámina 3.** Sobre `<uuid D>`: `0=si`, `1=no`+nota, y la lámina 2 (índice 2)
debe salir con marca **`borrar`** — explícita, no `pendiente`. Es la invariante 11: deshacer viaja
como `borrar` para que la fusión sepa que se está quitando, no que no se ha decidido.

**Acto 5 — Pedir cambio + nota, lámina 3.** Sobre `<uuid E>`: `0=si`, `1=no`+nota,
`2=no` + **`prueba: la imagen no sostiene el argumento`**.

## 3. Lo que `recurso=dia` debe devolver al final

Después de los 5 actos, la fusión (`fusionDia_`, por editor y por pieza y por lámina, gana la fila
más reciente con marca real) debe devolver:

```
decisiones.propuestas["prueba-celdas-3e54c4"].laminas = ["si", "no", "no"]
decisiones.propuestas["prueba-celdas-3e54c4"].notas   = ["", "prueba: entonación de pregunta",
                                                        "prueba: la imagen no sostiene el argumento"]
```

Y **las 3 piezas reales deben quedar exactamente como están ahora**:

| pieza | marcas que debe conservar |
|---|---|
| `apodo-video-9sep-v5` | `[null, "si"]` |
| `apodo-g5-dcff8d` | las 6 en `null` (pendientes) |
| `comprador-g5-b1cf4e` | `["si", null]` |

## 4. Lo que el supuesto (`sala_supuesto.py`) debe decir después

```
prueba-celdas-3e54c4
  lámina 1    ✓ aprobada     → NO se toca
  lámina 2    ✗ cambio       tu nota: «prueba: entonación de pregunta»   → HARÉ receta nueva
  lámina 3    ✗ cambio       tu nota: «prueba: la imagen no sostiene…»   → HARÉ receta nueva
```

Y los bloqueos deben seguir siendo **uno solo**: el del video sin nota.

## 5. Lo que NO debe pasar (si pasa, es hallazgo)

1. Que una pieza real pierda una marca o una nota.
2. Que `lamina` salga en base 1 en vez de base 0.
3. Que `guardado` salga con 7 horas de diferencia.
4. Que el deshacer escriba `pendiente` en vez de `borrar`.
5. Que un sobre no repita las marcas anteriores (y la fusión las pierda).
6. Que la nota se guarde en `nota_dia` en vez de `nota_propuesta`.
7. Que dos actos compartan `envio_id` (la idempotencia descartaría el segundo).
8. Que la Sala pinte la lámina 1 después de aprobarla (no debe volver a preguntarla).

---

# COMPARACIÓN · se llena DESPUÉS de correr

*(vacío hasta que la prueba corra)*
