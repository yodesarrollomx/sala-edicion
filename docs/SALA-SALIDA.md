# Estación de salida · de «imágenes aprobadas» a «lista para publicar»

9-nov-2026 · Sala corta (`docs/SALA-CORTA-20261109.md`). Dirección pidió «el proceso de creación de
inicio a final completo… no me borres nada de lo pasado de ideas ya aprobadas… sólo quiero orden
para poderlas desatorar».

## Qué estaba pasando

Medido ese día con lo que publica la propia mesa: las **27 piezas vivas tenían todas sus láminas
aprobadas** (94 imágenes) y ninguna avanzaba. La línea tenía dibujada una etapa «copy» que nadie
hacía desde que se fue la Mac, y no había a dónde entregar. En la pantalla todas decían «25% ·
sigue · no hay una tarjeta por responder»; en el teléfono, además, «Cómo va» y Ajustes quedaban
tapados por la mesa.

## La línea completa

```
idea elegida → guion y primera imagen → imágenes → (consejo) → texto y paquete → TU CLIC → publicada
   arranque          arranque             mesa      jurado      estación de salida    Dirección
```

| Paso | Quién | Dónde se ve |
|---|---|---|
| Idea elegida → guion + lámina 1 | `sala_arranque.py` | «Te toca»: se decide |
| Láminas (rehacer lo regresado, continuar el guion) | `sala_mesa.py` | «Te toca»: se decide |
| Juzgar con CANDADOS | jurado de nube + `sala_consejo.py aplicar` | la marca del consejo cede ante la humana |
| **Texto de la publicación** | jurado de nube (juicio) | — |
| **Paquete + registro** | `sala_salida.py paquete` (sin juicio) | «Te toca»: lista para publicar |
| Publicar | Dirección, desde su teléfono | hoja de la pieza: imágenes, texto, liga |
| «Ya la publiqué» | Dirección, un toque | sale de la lista; pasa a `_PUBLICADAS` |

## Reparto: ninguna llave pasa por un modelo

| Quién | Qué hace | Con qué |
|---|---|---|
| `sala-consejo.yml` · `expediente` | Además de las cartas por juzgar, deja en el expediente (`salida`) las piezas completas que esperan su texto, con sus imágenes y lo que dice cada una. No escribe nada más. | secretos de Actions |
| Tarea programada de Claude | Escribe el texto de cada pieza (receta abajo) y anota lo que vea en las imágenes que convenga revisar antes de publicar. | suscripción de Dirección |
| `sala-consejo.yml` · `paquete` | Valida el texto, sube a Drive las imágenes aprobadas en orden con su documento, y lo anota en EXPEDIENTES y PRODUCCION. Cierra lo que la Sala anotó como publicado. | llave del **agente** y cuenta de servicio de Drive. **No recibe la llave del consejo.** |

La estación entra como agente: no decide (INVIOLABLE 3), no publica y no borra.

## Qué es «completa»

Con la misma regla de producción que la mesa (`sala_produccion.resolver_tira`): todas las láminas
de la tira vigente están aprobadas —con su toma elegida donde hubo tomas— y ya no falta ninguna
lámina del guion. La tira vigente es **la que la mesa publicó** (`datos/mesa-estado.json`); sin esa
lectura, la estación no empaca lo dudoso. Comprobado con todas las versiones reales de las 27 piezas
(156 tiras, hasta 19 por pieza): 27 de 27 coinciden con la mesa.

Lo que nació para video sale como carrusel con sus láminas aprobadas **mientras el video esté en
pausa** (`nube_ejecuta_etapas` sin escena ni corte).

## El paquete

`YOD Editorial/_LISTAS PARA PUBLICAR/<N · Título>/`

- `01.png`, `02.png`… las tomas elegidas, en el orden en que van (1080 × 1350, el original).
- `COPY · <Título>`: documento con el texto de Instagram, la liga del primer comentario, el texto de
  Facebook, lo que conviene mirar antes de publicar y de qué tomas salió.

`N` es el orden de llegada. Repetir la estación no duplica: reusa la carpeta de la pieza y no vuelve
a subir una imagen idéntica (md5). Cada imagen se comprueba contra lo que la casa ya sabe de ella
(sha256 del recibo público, md5 de la toma aprobada): si no coincide, la pieza no se empaca.

Al anotarse como publicada, la carpeta pasa a `YOD Editorial/_PUBLICADAS/` y el expediente queda
«publicada» con su liga. Nada se borra.

## El texto: receta y compuerta

**Receta.** La que trae el expediente en `salida.receta`. Por omisión es la de `RECETA` en
`nube/sala_salida.py`; Dirección la cambia sin código en la hoja **PROMPTS, fila `_copy`**,
columna `prompt_base`.

**Compuerta** (`revisar_texto`): lo que una regla sí puede comprobar. Si falla, el texto regresa
(código en el registro, nunca el texto) y la pieza espera otra sesión.

| Código | Candado | Qué mira |
|---|---|---|
| `ubicacion` | A01 | Hermosillo, Sonora, México y lo que agregue `contenido_ubicaciones_vetadas` |
| `palabra_vetada` | A11 | pleito, estorba, gremio… y `salida_palabras_vetadas` |
| `nombre_del_plan` | A13 | siempre «Plan de Potencial Personalizado», completo |
| `dinero_o_gratis`, `plazo` | A14 | cifras de dinero, «gratis», «N horas/días/semanas» |
| `otra_marca` | A15 | Aurum |
| `liga` | — | las ligas las pone la estación |
| `corto`, `largo`, `caracteres_de_control` | — | 120 a 1 900 caracteres |

Que enganche y que cuente lo que cuentan las láminas es juicio del jurado y, al final, de Dirección:
el texto se puede cambiar en la Sala antes de copiarlo.

**Las ligas** se arman aquí y se miden por pieza:
`<salida_liga>?utm_source=instagram|facebook&utm_medium=social&utm_campaign=ig|fb-<fecha>&utm_content=<slug>`.
`utm_content` es lo que `plan_agregados.py` usa para contar contactos y citas por pieza.

## El JSON de los textos (`paquete`)

```json
{
  "esquema": 1,
  "paquetes": [
    {
      "id": "<id de la pieza, tal cual viene en salida.pendientes>",
      "sello": "<sello de esa pieza en el expediente>",
      "texto": "<el texto de la publicación, sin ligas ni hashtags>",
      "revision": ["Lámina 3: el fondo no se siente de aquí (A07). Ya la aprobaste."]
    }
  ]
}
```

`gh workflow run sala-consejo.yml -R yodesarrollomx/sala-edicion --ref main -f modo=paquete -f paquetes="$(cat paquetes.json)"`
(con `-f ensayo=true` valida y dice qué haría, sin escribir). Máximo 60 000 caracteres y 40 piezas.

Lo que hace con ellos: ignora una pieza que ya no está completa, que ya tiene paquete o cuyo
`sello` cambió (Dirección cambió de toma: el texto era para otra versión); regresa el texto que
rompe la compuerta; empaca lo demás. Si Drive o el Sheet fallan en una pieza, sigue con las otras y
la corrida termina en rojo: esa pieza se reintenta sin duplicar nada.

## Lo que se anota en la Sala

- **EXPEDIENTES** (una fila por pieza): `estado: lista`, `paquete` (carpeta, orden, imágenes),
  `copy` (texto, instagram, comentario, facebook, revisión), `portada`, `ahora` y un hito. Conserva
  todo lo que el expediente ya decía: historia, reglas, versiones y las palabras de los editores.
- **PRODUCCION**: «paquete listo» con la liga de la carpeta.
- Desde la Sala, **«Ya la publiqué»** agrega una fila `publicada` a PRODUCCION (con la liga y, si
  Dirección cambió el texto, el que usó). En su siguiente sesión la estación cierra el expediente.

## Frenos (REGLAS; todos opcionales)

| Regla | Por omisión | Qué hace |
|---|---|---|
| `salida_activa` | `1` | `0` detiene los paquetes; lo publicado se sigue asentando |
| `salida_piezas_por_sesion` | `3` | piezas que el jurado recibe por sesión para escribir |
| `salida_excluir` | vacío | slugs que **no salen** hasta que Dirección lo diga |
| `salida_reels_como_carrusel` | `1` | `0`: lo que nació para video nunca sale como carrusel |
| `salida_liga` | plan-potencial | base de las ligas medibles |
| `salida_cierre_ig` | «(la liga te espera en el primer comentario)» | última línea del texto de Instagram |
| `salida_palabras_vetadas` | vacío | palabras extra para la compuerta |

## Lo que la estación nunca hace

- Publicar, mandar mensajes o correos.
- Decidir: no conoce la llave del consejo ni la acción `decidir`.
- Borrar: ni carpetas, ni archivos, ni historia.
- Imprimir el texto o las notas de revisión en los registros (son públicos).
- Empacar una versión que no sea la vigente o una imagen que no sea la aprobada.

## Lo que todavía no hace

- El botón «Publicar» que suba a Instagram y Facebook desde la Sala (va con su propio PR; publicar
  seguirá siendo el clic de Dirección).
- Traer los números de cada publicación a la Sala (hoy las métricas se leían desde la Mac).
- Empacar historias de 15 segundos: el video sigue en pausa.

## Pruebas

`tests/sala_salida_test.py` (estación), `tests/sala-salida.test.cjs` y `tests/sala-carga.test.cjs`
(pantalla, sin navegador) y `tests/salida.browser.cjs` (recorrido completo en teléfono y escritorio).
Código y pruebas locales no acreditan corridas reales: la primera corrida con Drive y el Sheet de
verdad queda registrada en el Buzón.
