# El Apodo · corte v7 — lo que va a pasar (escrito ANTES de ejecutar)
9-sep-2026. Sale de la nota con la que Alejandro rechazó el v6.

## Su nota, partida en encargos
| # | lo que dijo | qué se hace hoy |
|---|---|---|
| 1 | «hay una o dos láminas que hablan del nombre del terreno, es medio repetitivo, no llegamos al punto rápido» | RETIRAR láminas |
| 2 | «las láminas quedaron mal los textos» | MODIFICAR textos |
| 3 | «proponer láminas rehechas» | REHACER la del giro |
| 4 | «si aprobamos, volver a animar cada lámina» | NO se hace hoy — espera su sí |
| 5 | «después de eso sigues con el audio, mezclado, que no se empalme» | NO se hace hoy — va al final |
| 6 | «las voces no sabes interpretar quién es narrador y quién es vecino» | se deja el ROL escrito en el guion; se ejecuta en la etapa de audio |
| 7 | «el ruido de fondo muy alto, entra y sale, se corta» | etapa de audio |
| 8 | «voces más expresivas donde lo requiere, analiza cuándo y por qué» | etapa de audio |

Los encargos 4-8 **no se tocan hoy** porque él fijó el orden: láminas → aprobación → animación → audio.

## 1 · Lo repetitivo, medido
Las 8 escenas del v6 dicen esto:

| esc | texto | idea |
|---|---|---|
| 1 | ¿Ya sabes cómo le dicen a tu terreno? | le dicen |
| 2 | Los vecinos le dicen «el de la esquina». | le dicen |
| 3 | También le dicen «lote baldío». O «tierra de nadie». | le dicen |
| 4 | En cada sobremesa le inventan un apodo nuevo | le dicen |
| 5 | El apodo se mueve con cada rumor | le dicen |
| 6 | Ninguno de esos nombres se lo puso tu terreno | **el giro** |
| 7 | Tu terreno sí tiene un nombre propio… | el giro |
| 8 | Pídele su Plan de Potencial Personalizado | CTA |

**Cinco escenas seguidas dicen lo mismo.** El giro llega en la 6 de 8: segundo ~26 de 40.

**Se retiran la 4 y la 5.** Son la tercera y cuarta vuelta al mismo clavo: la 2 y la 3 ya
nombraron apodos concretos, con comillas, que es lo que la idea necesitaba. La 4 y la 5
sólo lo comentan otra vez, en abstracto y sin nombre nuevo.

Predicción medible: **6 escenas**, el giro en la 4 de 6, alrededor del segundo 15 de ~30.

## 2 · Los textos, medidos
Alto de la letra en las 8 láminas del v6 (píxeles):

| esc | alto | |
|---|---|---|
| 1 | 75 | el estándar |
| 4 | 74 | |
| 5 | 74 | |
| 6 | 73 | |
| 2 | 54 | chica |
| 3 | 56 | chica |
| 7 | **49** | la del giro |
| 8 | **44** | el CTA, la que tiene que convertir |

Cuatro tamaños distintos en una sola pieza. El CTA es casi la mitad del estándar.

**Causa raíz** (`apodo/montar_v6.py`, y el mismo patrón en el generador de láminas):

```python
ts = 78
while ts > 46:              # encoge la LETRA hasta que el TEXTO quepa en 2 renglones
    ...
```

Está al revés. **La letra manda; el texto se acomoda.** Se cambia a: piso de 66 px, y si no
cabe en 2 renglones se usan 3. Nada baja de 66 nunca más.

Predicción medible: las 6 láminas del v7 con alto de letra **entre 66 y 78 px**, y la
diferencia entre la más grande y la más chica **menor a 12 px** (hoy es 31).

Un texto se acorta, y sólo uno: la 7 dice «Tu terreno sí tiene un nombre propio: lo que de
verdad puede sostener» — dos frases en una lámina, y es la del giro. Se parte: la 7 se queda
con el remate.

## 3 · La lámina que se rehace
La 7 es la del giro y hoy tiene **una ciudad grande con un tripié**. Ni es su terreno ni es
lo que dice el texto. Se rehace con el terreno solo, en luz de amanecer, sin nadie hablando
de él: es la escena donde por fin se le ve.

## 4 · Lo que NO va a pasar hoy
- No se anima nada. La animación espera su sí sobre estas 6.
- No se toca el audio ni la mezcla.
- No se junta ningún corte nuevo. La compuerta lo impide y así debe ser.

## 5 · Lo que llega a su mesa
UNA carta: las 6 láminas del v7 en tira, con las 2 retiradas marcadas como retiradas y el
motivo, y los textos que cambiaron señalados. Tres opciones: aprobar y animar, cambiar algo,
o rechazar con nota.
