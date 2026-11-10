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

## El montón y el plan de salida (en «Te toca»)

El 9-nov, ya con 24 publicaciones listas, Dirección dijo: «no voy a publicar aún, quiero hacer montón
para nunca quedarnos… que vayamos armando un paquete para ir lanzando». Por eso «Te toca» abre con
**el montón**: todo lo listo, en una rejilla, en el orden en que va a salir.

- **Qué se ve.** Cuántas hay, para cuántas semanas alcanza al ritmo elegido y, si hay día de
  arranque, la fecha de cada una. Abajo, lo que espera su texto y lo guardado por regla.
- **El plan es de los editores y se cambia sin código**: cuántas por semana (1 a 7), el día de
  arranque (opcional) y el orden («Cambiar el orden» → flechas o elegir el lugar → «Guardar el orden»).
- **Dónde vive.** Una sola fila de EXPEDIENTES con la llave **`salida:plan`**:
  `{v, orden:[nombres], por_semana, arranque, cuando, por}`. La escribe la Sala con la llave del
  editor (`accion: expediente`, la misma que usa Historias) y **la nube nunca la escribe**. Las llaves
  con prefijo (`v4:`, `salida:`) no son publicaciones y no entran a la lista de Publicaciones.
- **Si no sube**, el cambio se queda en el aparato y se reintenta al abrir. Hoy la hoja sólo deja
  guardar a la llave de Dirección (`editor`); con la de Sayri (`editor2`) la Sala lo dice y conserva
  su cambio en su aparato (falta abrirlo en el Apps Script; es la misma tarea que Historias).
- **Lo que el plan no nombra** (lo recién empacado) entra al final, por el número de su carpeta.
- **El calendario** reparte así: 1 → miércoles · 2 → martes y jueves · 3 → lunes, miércoles y viernes ·
  4 → lunes, martes, jueves y viernes · 5 → lunes a viernes · 6 → lunes a sábado · 7 → diario. Si el
  día de arranque ya pasó, corre desde hoy. Si a la primera le toca hoy, el montón lo dice («Hoy toca
  «…»») y resalta su tarjeta. Es una guía: **nada sale solo**.
- **La mesa se pliega** a un renglón cuando hay montón y nada por revisar («Ver la mesa» la abre). Con
  algo por revisar, o sin montón, se ve entera como antes.
- El número de la carpeta en Drive es el orden de llegada y **no cambia** al reordenar: la Sala abre
  cada carpeta por su liga.

## Pedir cambio a una pieza lista (orden de cambio)

**Para qué.** Un editor ve mal una imagen que ya estaba aprobada y pide rehacerla, aunque la pieza ya
esté en el montón. La aprobación anterior no se borra: queda en la historia y se suma una orden.

**La llave.** Una fila de EXPEDIENTES por pieza, llave **`cambio:<slug>`**:
`{v:1, pieza, tira, paquete, ordenes:[{n, nota, cuando, por}], cuando, por}`.

- `tira`: la versión de la pieza sobre la que se pidió. La orden **vale sólo para esa tira**.
- `paquete`: la versión que estaba empacada al pedir (o vacío). Sólo lo usa la pantalla.
- `ordenes`: una por imagen (`n` = número de lámina) con la nota del editor.

**Quién escribe y quién lee.** La escriben **los editores**, desde la Sala, con su llave
(`accion: expediente`, como `salida:plan`). La nube **sólo la lee** (`nube/sala_cambios.py`): la mesa
rehace la lámina con la nota y crea una tira nueva (`origen: rehecha-de <tira>`). La nube nunca
escribe `cambio:`; una prueba lo vigila.

**Mientras la orden siga viva**, la estación no empaca la pieza y la pantalla la saca del montón.
En el pie del montón y en «Cómo va» se ve en uno de dos estados:

- **Pedido**: Producción todavía no la atiende. «Producción la rehace con tu nota.» Aquí se puede
  «Quitar la petición».
- **Volvió**: ya se rehízo (o hay una versión más nueva en camino). El paquete viejo no se ofrece, no se
  puede quitar y la versión nueva se decide en la mesa. Cuando se rearma su paquete, vuelve al montón.

**Segunda vuelta.** Si se pide otro cambio sobre la versión rehecha antes de que se vuelva a empacar,
el registro cambia de `tira`. Sin el campo `paquete`, el paquete viejo reaparecía como listo para
publicar. Con él, la Sala sabe que ese paquete es anterior a la orden y lo mantiene fuera del montón.

**Quitar la petición.** Es escribir el mismo registro con `ordenes: []`; conserva `tira` y `paquete`.
Sólo se puede mientras el estado sea «pedido» **y la mesa confirme** que todavía enseña la versión de la
orden (`SalaTablero.pidDe`). Si la Sala no lo puede confirmar (mesa sin cargar o en copia guardada), no
ofrece el botón: quitar a ciegas podía devolver al montón un paquete que Producción ya estaba rehaciendo.
Piezas ya publicadas no se rehacen.

**Una sola cuenta.** El montón, su pie y «Cómo va» salen de la misma función (`estadoDe` en
`sala-salida.js`, sobre la función pura `retiro`): toda pieza con paquete y no publicada está en el montón
o en el pie, con un renglón por pieza. Si una pieza tiene dos registros (el slug de la mesa y el de su
paquete no coinciden), manda el que la saca del montón.

**En la nube.** Las piezas con orden van primero en la ronda de la mesa, para que el tope de láminas no
las deje esperando. La mesa cuenta en `datos/mesa-estado.json` (sólo números) `ordenes_de_cambio` y
`ordenes_sin_tira_vigente`, y avisa en el registro de la corrida por cada orden que no puede atender (su
tira ya no es la vigente, no tiene fuente en el Sheet o la pieza ya se publicó). Así una orden perdida
se ve en vez de quedarse diciendo «Producción la rehace» para siempre.

**Límites conocidos.**

- Dos aparatos sobre la misma pieza: **gana el último** que escribe.
- Según la copia pública del Apps Script (`gas/Code.gs`), `accion: expediente` sólo acepta los roles
  agente y editor: Sayri (`editor2`) todavía no puede pedir ni quitar cambios (lo mismo le pasa con
  `salida:plan`). La pantalla se lo dice y no da nada por pedido.
- Una orden contra una versión que ya no es la vigente **se ignora por diseño**: la versión nueva
  debe pasar por la mesa.
- «Cómo va» lo sabe por `SalaSalida.cambioDePieza`; funciona también para una pieza sin paquete.

## Cómo abre (medido el 9-nov en el navegador de Dirección)

| Lo que pasaba | La causa | Cómo quedó |
|---|---|---|
| La página se encogía al centro sobre fondo oscuro y regresaba, una y otra vez | El indicador de carga le ponía a `<html>` la clase `cargando`, la misma del esqueleto de una carta (`position:absolute; display:grid; font-size:13px…`) | La clase se llama `trayendo` |
| «Copia disponible · sin conexión» hasta tocar un botón | Con el caché del Apps Script frío el día tarda **14 s** (tibio, 2.6 s) y cualquier escritura lo enfría; la Sala esperaba 8 s, dos veces | El día tiene su propio tope: 30 s (`SALA_TOPE_DIA_MS`), dos peticiones como máximo, sin ciclos. La última mesa se ve desde el primer segundo |
| Lo listo para publicar aparecía al minuto, o nunca | Los expedientes sólo se pedían cuando el día llegaba | Se piden al abrir, en paralelo (`arrancarSalida`), y lo último visto se pinta al instante desde el aparato |
| «Reintentar ahora» no hacía nada | Con la mesa en copia sólo reintentaba *subir* | Vuelve a preguntar al Sheet |
| Una publicación de una sola lámina ocupaba toda la pantalla | `repeat(auto-fit,minmax(155px,1fr))` | Cada página crece hasta 260 px |

Lo guardado en el aparato (`sala_salida_local_v1`) es sólo para pintar: lleva título, portada, imágenes,
texto y la liga de la carpeta de las piezas listas; pertenece a quien lo guardó (misma huella que la
mesa local), dura siete días y se borra si la hoja rechaza la llave. No da permiso de nada.

Para YOD OS (mismo origen) la Sala deja además `sala_resumen_v1`: `{listas, cuando}`. Es sólo el número
de piezas listas y la hora en que se vio; sin títulos ni textos. Se borra junto con la copia.

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
- Renombrar las carpetas de Drive según el orden del plan.
- Calentar el caché del día después de cada escritura de la nube (hoy lo calienta el disparador de
  diez minutos del Apps Script; entre una escritura y el siguiente disparo el día tarda 14 s).
- Traer los números de cada publicación a la Sala (hoy las métricas se leían desde la Mac).
- Empacar historias de 15 segundos: el video sigue en pausa.

## Pruebas

`tests/sala_salida_test.py` (estación), `tests/sala-salida.test.cjs` y `tests/sala-carga.test.cjs`
(pantalla, sin navegador) y `tests/salida.browser.cjs` (dos recorridos en teléfono y escritorio: publicar,
y el montón con su orden, ritmo, arranque, copia en el aparato, hoja lenta, hoja caída y llave que no
puede guardar).
Código y pruebas locales no acreditan corridas reales: la primera corrida con Drive y el Sheet de
verdad queda registrada en el Buzón.
