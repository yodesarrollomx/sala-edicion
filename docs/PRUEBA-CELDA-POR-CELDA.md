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

# COMPARACIÓN · lo predicho contra lo que pasó

Corrida el 8-sep-2026, 18:37–18:39, en el Chrome de Alejandro, con su sesión real.
**5 sobres · 20 filas** en la pieza de prueba.

## Lo que salió EXACTO

| Predicción | Resultado |
|---|---|
| `lamina` en base 0 | ✓ `0, 1, 2` |
| `quien` = el rol, no el nombre | ✓ `editor` |
| Acto 1 → `si, pendiente, pendiente` | ✓ idéntico |
| Acto 2 → `si, no+nota, pendiente` | ✓ idéntico |
| Acto 3 → `si, no+nota, si` | ✓ idéntico |
| **Acto 4 (deshacer) → marca `borrar`** | ✓ **`marca=borrar`**, no `pendiente` |
| Acto 5 → `si, no+nota, no+nota` | ✓ idéntico |
| Cada sobre repite las marcas anteriores | ✓ los 5 |
| Un `envio_id` distinto por acto | ✓ 5 distintos |
| La nota en `nota_propuesta`, no en `nota_dia` | ✓ |
| `guardado` en hora de Hermosillo | ✓ 18:37–18:39, sin desfase |
| Fusión final `["si","no","no"]` + las 2 notas | ✓ idéntico |
| **Las 3 piezas reales intactas** | ✓ video `[null,"si"]` · apodo-g5 `null` · comprador `["si"]` |

La invariante 11 («pendiente nunca borra») se sostuvo: las piezas reales viajaron como
`pendiente` en los 5 sobres y no perdieron nada.

## Lo que NO salió como decía el renglón

### 1. El `prop_id` que predije estaba mal
**Decía:** `prueba-celdas-3e54c4`. **Salió:** `prueba-celdas-e1e74e`.
**Por qué real:** el id es `slug + sha1(carpeta)`, y en macOS `/tmp` es un enlace a `/private/tmp`.
Yo calculé el sha1 de `/tmp/prueba_celdas`; el publicador usó la ruta resuelta.
**Estrategia:** el id no debe depender de una ruta del sistema de archivos — dos rutas al mismo
lugar dan ids distintos, y una carpeta movida cambia el id de una pieza que ya existe. Debe salir
del **contenido** (huella de las láminas) o del slug + fecha. Mientras tanto, `sala_supuesto.py`
debe imprimir el `prop_id` real antes de montar, no después.

### 2. Mi auditor estaba ciego: leía `prop_id` y el GAS devuelve `prop`
**Decía:** las filas se filtran por `prop_id`. **Salió:** 0 filas, y llegué a escribir que el
Sheet estaba vacío cuando tenía las 20 filas.
**Por qué real:** `recurso=envios` renombra el campo a `prop` (línea 395 del Code.gs). Mi script
pedía `f.get('prop_id')` y siempre daba vacío — **sin fallar**, que es lo peor: un auditor que
devuelve «no hay nada» cuando no sabe leer.
**Estrategia:** que el lector **truene** si el campo que espera no existe, en vez de devolver
vacío. Un `KeyError` es información; un vacío silencioso es una mentira.

### 3. La Sala mostraba «Último intento de guardado: Failed to fetch» con todo bien guardado
**Decía:** nada — no lo había previsto.
**Por qué real:** `guard.ultimoError` se escribe cuando un envío falla y **no se limpiaba nunca**.
Un tropiezo de red de horas antes dejaba el aviso puesto para siempre, aunque los 5 sobres de esta
prueba hubieran entrado bien. Una alarma que no se apaga deja de ser alarma: enseña a ignorarla.
**Estrategia:** aplicado ya — se limpia en cuanto un guardado sirve. Y la regla general: **todo
indicador de error necesita su condición de apagado escrita junto a la de encendido.**

### 4. El borrador local arrastra piezas ya retiradas
**Decía:** nada.
**Por qué real:** `sala2-2026-09-08` conserva `apodo-g1-c5fa4c`, `apodo-g3`, `apodo-video-8sep` y
`vendo-construyo-g1-41098b` marcadas `_reabierta`, y sus marcas viajan en cada sobre. Hoy no hace
daño (el Sheet las ignora porque están retiradas) pero engorda cada envío y es la clase de resto
que un día resucita algo.
**Estrategia:** al recibir el día, podar del borrador toda pieza que ya no esté viva, dejando
constancia en la bitácora de qué se podó. **No aplicado todavía** — quiero medirlo antes de tocar
la fusión, que es la pieza más delicada del sistema.

## Qué se hizo con la pieza de prueba

Se retira de la mesa al terminar. Sus filas quedan en DECISIONES como registro de esta prueba.


### 5. El deshacedor revertía archivos compartidos y casi tira el catálogo
**Decía:** nada. Salió de un accidente mío durante esta misma prueba.
**Qué pasó:** lancé por error `sala_publicar.py --pub /dev/null`. La guardia lo detuvo bien, pero
`_deshacer()` hacía `git checkout --` sobre `datos/manifiesto.json`, `datos/catalogo.json` y
`datos/laminas_vistas.json`. Esos archivos son **compartidos**: revertirlos enteros tira el
trabajo sin commitear de todo lo demás. Estuvo a un pelo de borrar los 115 ids de Drive recién
subidos.
**Por qué real:** confundí «deshacer lo que hizo esta corrida» con «devolver estos archivos a su
último commit». No es lo mismo, y la diferencia es el trabajo de otro.
**Estrategia:** aplicado — el deshacedor ya no revierte ningún archivo entero. Quita la carpeta
de la pieza, su tira, y **sólo su entrada** del manifiesto. Regla general: **un rollback nunca
puede tocar más de lo que su propia corrida escribió.**
