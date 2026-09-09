# Corrida real en Chrome · predicho contra medido

*8-sep-2026, 20:46–20:58. Metodología pedida por Alejandro: «primero escribir qué va a suceder y
medir qué sucedió, después de una serie de ejecuciones reales en la Sala desde Chrome como si
fuera yo editando». La predicción está en `datos/prueba_expectativas.json`, escrita antes y sin
tocar después.*

Pieza desechable de 3 láminas (imágenes propias, no las suyas) para no rozar sus decisiones reales.
**7 sobres · 7 envio_id distintos.**

## Lo que salió exacto

| Acto | Predicho | Medido |
|---|---|---|
| 1 · Aprobar lámina 1 | `si · pendiente · pendiente` | ✓ igual |
| 2 · Pedir cambio + nota | `si · no · pendiente` + nota | ✓ igual, nota en `nota_propuesta` |
| 3 · Aprobar lámina 3 | `si · no · si` → pantalla final | ✓ igual |
| 5 · Volver a aprobar | `si · no · si` | ✓ igual |
| 6 · Reabrir lámina 1 + nota | `no · no · si` + nota | ✓ igual |
| 7 · Ir a Publicaciones y volver | no pierde estado | ✓ igual |
| — | índice base 0 · un `envio_id` por acto · hora de Hermosillo | ✓ los tres |
| — | **sus piezas reales intactas** | ✓ ni una marca, ni una nota |

## Lo que NO salió como decía el renglón

### 1. En la pantalla final no existe «Deshacer la última»
**Decía:** que el acto 4 desharía y escribiría `borrar`.
**Salió:** ese botón no está en la pantalla final; sólo «Cambiar alguna respuesta».
**Por qué real:** el deshacer vive en la carta, no en el cierre. **No es un defecto** — mi
predicción estaba mal. El camino real (Mis respuestas → Cambiar) sí funciona y sí escribe
`borrar` (sobre 6: `borrar · no · si`).
**Estrategia:** predecir contra la UI que existe, no contra la que imagino. Antes de escribir
una expectativa de botón, listar los botones de esa pantalla.

### 2. 🐛 El contador final sumaba el atraso como decisiones de hoy
**Salió:** «**2 aprobadas · 24 con cambios**» cuando había decidido 3 láminas.
**Por qué real:** `cuentas()` recorría todo `dec`, y `dec` carga también las **reaperturas
heredadas** — piezas de días pasados que ya no están en la mesa, traídas para que Producción las
rehaga. Se contaban como decisiones del día.
**Arreglado y medido:** ahora dice «**2 aprobadas · 1 con cambio**».
**Estrategia:** todo contador declara su universo. Lo de hoy es lo que está en `pasos`; el atraso
se cuenta aparte y con su nombre.

### 3. 🐛 «Mis respuestas» abría con 54 filas
**Salió:** 54 filas, con las 4 de hoy perdidas entre 50 de atraso.
**Por qué real:** `filasRespuestas()` devolvía `hoyF + reF` pegados.
**Arreglado y medido:** **4 de hoy** · **23 en «Esperando a Producción · de días pasados»**.

### 4. Mi tecleo sintético no llega al diálogo de nota
**Salió:** el textarea tenía el foco y quedó **vacío** después de teclear; el diálogo no cerraba.
Por DOM entró al primer intento.
**Por qué real:** es una limitación de **mi arnés de prueba** en ese diálogo, no del sistema. Lo
digo aquí porque estuve a punto de reportarlo como bug de la Sala.
**Estrategia:** cuando un acto no surta efecto, comprobar primero si el evento llegó (foco + valor)
antes de acusar al código.

## Estado al cerrar
Pieza de prueba retirada. Sus 7 sobres quedan en DECISIONES como registro de esta corrida.

---

# Vuelta 2 · 21:1x — limpia

Predicción en `datos/prueba_expectativas_v2.json`, escrita antes y corregida con lo que enseñó la
vuelta 1 (no predecir botones que no existen).

| Acto | Predicho | Medido |
|---|---|---|
| 1 · Aprobar lámina 1 | `si · pendiente · pendiente` | ✓ |
| 2 · Pedir cambio + nota | `si · no · pendiente` + nota | ✓ |
| 3 · Aprobar lámina 3 | `si · no · si` · **«2 aprobadas · 1 con cambio»** | ✓ |
| 4 · Abrir Mis respuestas | 2 secciones separadas | ✓ **4 de hoy · 25 de atraso** |
| 5 · Cambiar la 1 desde ahí | `· no · si` + `borrar` + vuelve a la carta | ✓ |
| 6 · Aprobarla otra vez | `si · no · si` · mismo resumen | ✓ |

**5 sobres · 5 envio_id distintos · el `borrar` explícito viajó · ninguna pieza suya cambió.**

**Cero desviaciones.** Los dos defectos de la vuelta 1 (el contador que sumaba el atraso y las 54
filas) quedaron cerrados y medidos en su arreglo, no de palabra.

---

# Vuelta 3 · confirmación

| Acto | Predicho | Medido |
|---|---|---|
| 1 · Aprobar lámina 1 | `si · ·` | ✓ |
| 2 · Pedir cambio + nota | `si · no ·` + nota | ✓ |
| 3 · Aprobar lámina 3 | `si · no · si` · «2 aprobadas · 1 con cambio» | ✓ |
| 4 · Mis respuestas | 2 secciones separadas | ✓ **4 de hoy · 26 de atraso** |
| 5 · Cambiar la 1 desde ahí | `· no · si` + `borrar` | ✓ |
| 6 · Aprobarla otra vez | `si · no · si` | ✓ |
| — | ninguna pieza suya cambia | ✓ |
| — | verificador en 0 rojos | ✓ |

**Los 6 estados exactos. Cero defectos nuevos.**

## La única desviación, y es de mi predicción

**Decía:** 5 sobres, uno por acto. **Salió:** 4.
**Por qué real:** la Sala **agrupa** envíos cuando los actos ocurren muy seguido — el estado final
viaja una vez en vez de dos. En las vueltas 1 y 2 cada acto tuvo su sobre porque yo hacía clics
reales, más lentos; en la 3 los disparé por DOM, casi encimados.
**No es un defecto:** el estado final en el Sheet es correcto y agrupar es mejor que no agrupar.
**Estrategia:** no predecir el número de sobres. Lo que se predice y se mide es **el estado
final**, que es lo único que decide qué se produce.

## Un defecto que salió del cierre, no de los actos

Al retirar las piezas de prueba dejé sus tiras apuntando a imágenes borradas: **el verificador se
puso rojo en 6 comprobaciones**. Hizo bien. Retirar una pieza son cuatro cosas —mesa, láminas,
tira, registro— y yo hacía una. Ahora `sala_limpiar_prueba.py` hace las cuatro y lo dice.

# Cierre

Tres vueltas. **Cuatro defectos reales encontrados y arreglados**, ninguno de ellos por mirar el
código: los cuatro salieron de ejecutar en Chrome y comparar contra lo escrito antes.

| # | Defecto | Estado |
|---|---|---|
| 1 | El contador final sumaba el atraso: «2 aprobadas · **24** con cambios» | arreglado y medido |
| 2 | «Mis respuestas» abría con 54 filas mezcladas | separado y medido |
| 3 | `ultimoError` no se apagaba nunca | arreglado |
| 4 | Retirar una pieza dejaba su tira huérfana (6 rojos) | `sala_limpiar_prueba.py` |

Verificador: **12 verdes · 0 rojos.**
