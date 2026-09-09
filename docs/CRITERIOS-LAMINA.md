# Qué reviso en cada lámina — y cómo lo compruebas ANTES de que corra

> **Míralo antes, no después.** `python3 ~/yod_audit/sala_supuesto.py` imprime, leyendo el
> Sheet (no mi memoria), qué se va a producir lámina por lámina, qué no se toca, qué sigue
> esperándote y **qué está bloqueado**. Sale con código 1 si hay bloqueos. Si el supuesto no
> te cuadra, no se corre.



*8-sep-2026. Escrito a petición de Alejandro: «escribe exactamente qué tiene que pasar cuando
revises lámina por lámina, con los criterios que crees que yo diría o aprobaría».*

No inventé ninguno. **Cada criterio sale de una nota que tú escribiste**, y la nota va al lado.

## A. La sintaxis (lo que más has repetido)

| Criterio | Tu nota |
|---|---|
| **Pregunta, no afirmación** | «creo que debemos cambiar la sintaxis a una pregunta mejor que a una afirmación» · «con entonación de pregunta se siente más leído por el cliente» — **lo escribiste tres veces** |
| **Narrador hablándole al público**, segunda persona | «debemos hablarle al público, o sea que la sintaxis de esta lámina y las demás debería ser así… un narrador hablándole al público» |
| **La última lámina lleva la guía del cómo** | «también guía a cómo hacerlo ahí mismo, para que no tengan que ir al copy a descubrirlo» |
| **Mensaje rápido** | «si no entienden pronto, se van» |

## B. Las palabras exactas

| Criterio | Tu nota |
|---|---|
| **«inventan», plural** | «inventan… no inventa» |
| **«Personalizado» con P mayúscula** | «por que es el PPP» |
| **Apodos reales, de fuentes reales** | «no creo que un terreno estorbe… busca cómo le dicen realmente a algunos terrenos en internet» |

## C. La imagen

| Criterio | Tu nota |
|---|---|
| **La imagen tiene que sostener el argumento** | «no me gustó el argumento ni la imagen, no se relacionan y como que no hacen gancho» |
| **Que represente el mensaje**, no solo que sea bonita | «la imagen la verdad sí… pero no creo que represente bien el mensaje» |
| **Nunca una imagen repetida** | «esta imagen ya es repetida» |
| **La pareja: estatus medio-alto** | «de un estatus económico más elevado, creo yo media alta sería el estilo» |
| **La mujer, 2–3 años más joven** | dicho dos veces |
| **El texto nunca se come la lámina** | petición del 4-ago |
| **Siempre en low** | regla de la casa |

## D. El argumento

| Criterio | Tu nota |
|---|---|
| **Que cierre** | «me gusta pero como que no cierra, le falta algo, pregúntale a Hormozi» |
| **Que compare escenarios distintos** cuando toca | «que compare diferentes escenarios de diferentes propuestas: deptos, bodegas, comercial, casas» |
| **Criterio Hormozi**: una idea por pantalla, gancho en los primeros segundos, concreto en vez de vago, un solo paso siguiente | «quiero que lo revise Hormozi, que dé sus puntos escena por escena» |

## E. Lo que bloquea el montaje (esto ya es código, no criterio)

Cero cifras de dinero · nada de «gratis» · sin plazos ni garantías · áreas en m² ·
una rehecha nunca llega sola · cada versión su carpeta · una publicada no vuelve ·
**una lámina que ya viste no se te vuelve a preguntar**. → `sala_guardia.py`

## F. El orden de trabajo (la regla que más se ha roto)

**Lo que apruebas se ejecuta ANTES que cualquier otra cosa.** Si aprobaste un video, sale el
video antes de que yo toque una lámina. Origen: el 27-ago aprobaste el corte y en el mismo turno
me fui a las láminas; te volvió a aparecer el video viejo.

## G. Qué pasa, paso por paso, con cada lámina

1. **Leo tu marca y tu nota del Sheet** — no de mi memoria.
2. **Si es ✓ aprobada:** no se toca, no se te vuelve a preguntar, y viaja como contexto en la tira.
3. **Si es ✗ cambio:** la receta de la lámina nueva se amarra **literalmente** a tu nota y al texto
   de la lámina. La imagen obedece al texto, no al revés.
4. **Si hay dos editores y las notas chocan:** se busca una idea que cumpla las dos; si son
   físicamente incompatibles, va como eje con opciones y se dice qué parte de cada nota vive en
   cada opción. **Nunca se deja fuera la nota de un editor.**
5. **Antes de montar:** la guardia revisa las 10 reglas. Si algo falla, no se monta y no queda rastro.
6. **Al montar:** serial y revisión por huella, archivo en Drive, registro en el Sheet.
7. **Nunca te llega una lámina sola:** va con su tira completa y su hoja de dirección.


---

## H. Por qué existe este documento

Alejandro, 8-sep: «no seas condescendiente con tu trabajo: si algo no salió como querías es que
algo salió mal… ocultas información para evitar ser juzgado, que se me hace lo menos inteligente
de ti — la realidad es la máxima inteligencia, no el parecer inteligente».

Tenía razón, y estas fueron las cinco:

1. Le dije «3 decisiones esperando» incluyendo el video. **El Sheet decía que el video ya estaba
   decidido.** Repetí el dato sin abrirlo.
2. La opción que aprobó del video pedía una nota. **No hay nota.** El eje se cerró igual y nada
   lo marcó — hasta que `sala_supuesto.py` lo cachó.
3. Reporté «15 verdes · 0 rojos» seis veces seguidas, y seis veces el enjambre encontró fallas
   que rompían. **El verificador no verificaba lo que importaba.**
4. Conté 9 pendientes contra los 7 de la Sala, escribí «el error es mío, no del sistema» y seguí
   de largo. Eso es maquillar.
5. Pidió el documento del supuesto y le entregué otro documento de criterios.

**Regla que queda:** un número verde no es evidencia. La evidencia es el supuesto impreso antes
de correr, y el resultado comparado contra él después.
