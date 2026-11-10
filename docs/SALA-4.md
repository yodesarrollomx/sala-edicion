# Sala 4.0 · historias en episodios de 15 segundos

Decisión de Dirección (Alejandro, 9-nov-2026, por chat) después de ver el piloto con Gemini Omni
Flash: «vamos a contar una historia en 10 días de 15 segundos, en bloques de escenas de 15 o 30
segundos», con semillero limpio nutrido de lo pasado, todo en línea, en automático, y editable
desde la Sala sin tocar código. Antes había pedido lo mismo con sus palabras: una sola escena por
video, personajes guardados e historias que se entrelazan al final, y el cliente siempre de
protagonista.

**El canon de producción** (personajes, lugares, objetos, encuadres, reglas del mundo y temporada,
con sus imágenes de referencia) tiene su propio documento: `docs/SALA-CANON.md`.

Mapas (Graphify): `docs/grafos/sala-actual.html` (cómo funciona la Sala de siempre) y
`docs/grafos/sala-4.html` (cómo funciona la 4.0). Los dos salen de `docs/grafos/construir.py`:
`python3 docs/grafos/construir.py` rehace los JSON y, con Graphify instalado
(`pip install graphifyy`), también las páginas. Cada decisión lógica es un rombo y dice a dónde
lleva el «sí» y a dónde el «no».

## Qué es

Una **serie** cuenta una historia en N episodios (de fábrica 10), uno por día. Cada episodio es una
toma continua de 15 s con la voz del propio modelo, o un bloque de 30 s hecho de dos tomas (la
segunda arranca en el último cuadro de la primera). El protagonista siempre es un cliente; cada
serie cambia de industria y enseña un vértice del negocio.

## Cómo se usa (Dirección)

1. En la Sala, botón **Historias** (o `historias.html`).
2. **Series**: el semillero deja propuestas. Se abren, se edita el texto si hace falta y se toca
   **Aprobar la serie** o **No va**. También hay **Nueva serie** para escribir una propia.
3. La nube produce primero **un solo episodio, el piloto**. Se ve ahí mismo (o con «Abrir en
   Drive») y se marca:
   - **Sí**: aprobado. Con el «sí» del piloto siguen los demás.
   - **Pedir cambio**: con una nota. Se rehace como versión nueva y la marca vieja deja de valer.
   - **No va**: el episodio **queda fuera de la serie**. No se produce (si aún no tenía video), no
     se rehace y no entra al paquete. Se puede regresar con «Regresarlo a la serie».
4. Con todos los episodios decididos, la nube deja el **paquete** en Drive, en
   `_LISTAS PARA PUBLICAR/Historia · <título>`: los episodios aprobados, la historia completa unida
   y `COPY.txt` con el texto de cada día. Si después se pide un cambio, el paquete se rehace cuando
   la versión nueva tenga su «sí». **Publicar sigue siendo el clic de Dirección.**
5. **Universo**: el canon. La temporada (las historias que se cruzan), personajes, lugares, objetos,
   encuadres, reglas del mundo, formato de las tomas, vértices e **instrucciones para el guionista**.
   Todo es texto y se cambia ahí mismo; cada sección se abre sólo cuando se necesita. Arriba está la
   liga a la carpeta de las imágenes del canon en Drive: para usar una imagen propia de alguien o de
   algo, se sube ahí y se pega su liga en la ficha.
6. **Ajustes**: semillero encendido o apagado, cuántas propuestas esperan, episodios por serie,
   **tomas por día** e **imágenes de referencia por día** (los dos topes de gasto), piloto primero y
   los modelos que escriben y pintan.

## El mismo personaje, lugar y objeto en todos los episodios

Cada personaje, lugar y objeto que usa una serie aprobada tiene una **imagen de referencia** en
Drive (`_HISTORIAS/_CANON/`), que viaja a Omni en cada toma donde aparece: hasta cuatro por toma,
primero quién sale, después los objetos y al final el lugar. El texto de la toma dice qué es cada
imagen. La imagen es la que Dirección pegó en la ficha o, si no, la del canon: la que pinta la nube
a partir de la ficha (una vez; si la ficha cambia, se vuelve a pintar) o, cuando el piloto se
produjo sin imagen del protagonista, un cuadro de ese piloto. Un episodio marcado «misma escena que
el anterior» arranca además en el último cuadro del episodio previo.

Con las imágenes de referencia encendidas, **un episodio espera** a que lo que sale en él tenga su
imagen al día; mientras tanto no gasta y la corrida dice a quién espera. Y antes de reservar una
toma la nube hace lo que no cuesta: baja las imágenes, saca el cuadro de arranque y pasa el veto
sobre el texto. Si algo de eso no se puede, el episodio no se produce a medias ni gasta, y el aviso
aparece en la serie.

Cada toma baja un escalón si Google rechaza las imágenes (HTTP 400, que no se cobra): primer cuadro
con referencias, primer cuadro solo, todas las referencias, sólo las de los personajes, sólo texto.
Así un bloque de 30 s no pierde la primera toma ya pagada, y la pantalla avisa en el episodio qué
no se pudo usar.

## Historias que se cruzan

**La temporada** es el plan de series que comparten barrio, objetos y personajes; el semillero las
escribe en orden y, cuando se acaban, propone historias libres. Cada historia planeada fija su
protagonista, su lugar, su objeto, los guiños del mundo que deben verse y lo que siembra su último
episodio. Si el guionista olvida un guiño o un invitado, el código lo coloca.

En una serie, **Guardar en el universo** pasa algo propio (un personaje, un lugar, un objeto) al
mundo compartido, con su imagen. En cualquier episodio se marcan invitados y objetos. En historias
libres, el semillero puede proponer que un personaje conocido aparezca en el último episodio.

## Los candados de Dirección

El semillero lee la hoja CANDADOS y se los entrega al guionista como obligatorios; los de tipo veto
no se negocian. Lo mismo al escribir el texto para publicar. Si la hoja no contesta, la serie se
escribe con la estrategia común y la corrida lo dice. El veto de ubicaciones se revisa además por
código, sobre todo el texto de la serie y de cada instrucción que recibe el motor de video.

## Dónde vive cada cosa

Todo en la hoja EXPEDIENTES, con `recurso=expedientes` y `accion=expediente`, que el Apps Script
ya atendía. **No se cambió el backend.** Cada documento tiene un solo dueño:

| Llave | Dueño | Contenido |
|---|---|---|
| `v4:universo` | editor | el canon: temporada, encuadres, reglas del mundo, formato, vértices, guionista y ajustes |
| `v4:mundo:<clase>` | editor | los personajes, los lugares y los objetos del mundo, cada clase en su celda |
| `v4:serie:<id>` | quien la crea; después sólo el editor | la historia, sus episodios y lo propio de la serie |
| `v4:dec:<id>` | editor | aprobar la serie; sí / cambio / no por episodio y versión |
| `v4:prod:<id>` | nube | versiones, ligas de Drive, intentos por día, paquete, avisos |
| `v4:canon` | nube | las imágenes de referencia (pintadas o sacadas de un piloto), los fallos al pintar y el índice |
| `v4:estado` | nube | qué hizo la última corrida |

`nube/sala_v4.py` se niega, antes de la red, a escribir decisiones o a pisar lo del editor. Cada
documento vive en una celda del Sheet (tope real: 50 000 caracteres); la nube y la pantalla se
niegan a guardar uno de más de 45 000 y lo dicen. Por eso el mundo se guarda partido: la pantalla
manda primero las clases que cambiaron y al final `v4:universo`; si una parte no llega lo dice, y
el reintento sólo manda lo que faltó. Cuánto cabe está en `docs/SALA-CANON.md`.

`.github/workflows/sala-v4.yml` lo corre con horario y con botón: semillero → referencias →
productor → paquete → estado. En Drive: los videos en `_HISTORIAS/<serie>/`, las imágenes de
referencia y `CANON.txt` (quién es quién) en `_HISTORIAS/_CANON/`, y el paquete en
`_LISTAS PARA PUBLICAR/Historia · <título>` (la misma carpeta de la estación de salida).

Un universo guardado antes del canon (versión 1) recibe lo nuevo al leerse, en la nube y en la
pantalla, sin perder sus ajustes; queda en versión 2, y partido, la primera vez que Dirección lo
guarda.

## Revisión doble del plan

**Primera pasada, contra las reglas vigentes**

- *Decidir es de los editores* (INVIOLABLE 3): la nube no escribe `v4:dec`. Probado.
- *«No contestó» nunca es «no hay nada»* (4): si la hoja no contesta, la corrida se detiene; la
  pantalla no guarda a ciegas. Probado.
- *Ningún botón depende de un temporizador* (11): la pantalla no usa temporizadores.
- *Ubicaciones vetadas*: se revisa TODO el texto de la serie y de cada prompt. El revisor común
  sólo miraba ciertos campos; el piloto se corrigió igual.
- *Sala corta (9-nov)*: no se reactiva la línea vieja de video ni el generador de ideas viejo. Es
  un camino aparte, pedido por Dirección, y un solo flujo nuevo.
- *Publicar*: nada se publica solo.
- *La pantalla de Publicaciones* listaba todos los expedientes: ahora ignora las llaves `v4:`.

**Segunda pasada, buscando cómo falla**

- *Gasto*: cada toma cuesta alrededor de 1.05 USD. El tope diario se reserva ANTES de llamar, así
  que un intento fallido también cuenta y una falla detiene la corrida. De fábrica son 2 tomas al
  día. Además el crédito de Gemini es prepago: sin saldo, Google rechaza y no se cobra.
- *Pagar un video que no se puede guardar*: antes de reservar se asegura la carpeta de la serie en
  Drive; si Drive no contesta, no se reserva ni se llama al motor.
- *Piloto primero*: los demás episodios esperan el «sí» del piloto, para no producir diez tomas de
  una serie que no gustó. El piloto es el primer episodio que sigue en pie.
- *Decisión vieja sobre versión nueva*: cada marca guarda su versión; al rehacer deja de aplicar.
- *«No va» en un episodio*: antes dejaba la serie sin terminar nunca. Ahora ese episodio queda
  fuera y la serie se completa con los demás.
- *Cambio después del paquete*: el paquete anota qué versiones lleva; si cambian, se rehace.
- *Dos escritores sobre el mismo documento*: no existen; cada llave tiene un dueño y el flujo corre
  de uno en uno.
- *Texto del modelo mal formado*: se valida forma, número de episodios y que cada frase quepa en
  15 s (38 palabras); un segundo intento y, si no, no se propone nada.
- *Bloque de 30 s*: cuenta dos tomas y no entra a medias si el tope no alcanza.
- *Clips que no se pueden unir*: cada clip se lleva al mismo formato antes de unir, y a uno mudo
  se le pone silencio.
- *Imagen rechazada a media producción*: un bloque de 30 s pagaba la primera toma y perdía el
  episodio si Google no aceptaba el primer cuadro de la segunda. Ahora la toma baja de escalón.
- *Lo tecleado mientras se guarda*: la pantalla se repinta al terminar de guardar y borraba lo
  escrito durante la espera (lo encontró la revisión automática del 9-nov). Ahora, mientras
  guarda, la pantalla no deja escribir y dice «Guardando…».
- *Revisión que se colgaba*: un recorrido de navegador que fallaba dejaba su navegador abierto y
  la revisión nunca terminaba. Ahora todos se cierran al final, pase lo que pase.
- *Imágenes de referencia*: de pago; una por elemento y sólo para series aprobadas, con su propio
  tope diario y reserva antes de pedir. Lo propio de una serie se guarda con el nombre de la serie
  delante, para que dos «Mateo» de series distintas no se pisen.
- *El piloto producido antes de tener sus imágenes*: saldría con una cara y los demás episodios con
  otra. Con las imágenes encendidas, el episodio espera a las suyas.
- *Encender las imágenes a media serie*: la nube pintaría al protagonista con otra cara que la del
  piloto ya aprobado. Cuando el piloto se produjo sin imagen del protagonista, su imagen se saca
  de ese piloto y no se pinta aparte.
- *Una imagen que existe pero no se puede leer*: antes se producía sin ella y se avisaba después de
  gastar. Ahora se detiene antes de reservar. Lo mismo una nota de Dirección con una ubicación
  vetada, que antes gastaba la reserva del día sin producir nada.
- *Una imagen que Google no quiere pintar*: dejaba sin imagen a todo lo que venía detrás. Ahora
  queda anotada con su motivo, no se vuelve a pedir ese día y lo demás se pinta.
- *Una liga que no es de un archivo* (la de una carpeta, un texto): la pantalla no la guarda y la
  nube no la cuenta como imagen.
- *Un personaje «nuevo» con el nombre de uno del mundo*: es el del mundo; nadie cambia de cara.
- *El mundo que deja de caber en una celda*: se guarda partido por clases (ver arriba).
- *Un modelo de Google retirado o renombrado*: la simulación pregunta la lista y lo dice sin gastar.

## Comprobado en vivo (9-nov-2026, hora de Hermosillo)

- Texto a video de 15 s con voz, Gemini Omni Flash: corrida 42726461524 (el piloto que vio
  Dirección).
- La pantalla publicada lee la hoja con la llave de Dirección y muestra las series.
- La nube lee la hoja como agente: corrida de simulación 42737798270.
- La nube siembra el universo y propone una serie de 10 episodios: corrida 42737957598 dejó
  «El Heredero del Olivo», y la pantalla la mostró como «Propuesta · espera tu decisión».

## Lo que NO está acreditado

- **Imágenes de referencia en vivo**, pintarlas con la llave de prepago, **la voz** igual de un
  episodio a otro y el guardado partido contra la hoja de verdad: el detalle está en
  `docs/SALA-CANON.md`, «Lo que NO está acreditado». La primera serie aprobada lo dirá; si Google
  rechaza las imágenes, la toma baja de escalón y avisa.
- Que el personaje salga de verdad igual de un episodio a otro, aun con su imagen.
- Ninguna serie completa producida, ningún paquete y ninguna publicación.
- El reproductor de Drive dentro de la pantalla en iPhone; por eso está «Abrir en Drive».
- **Sayri (`editor2`) puede ver, pero no guardar**: en la copia pública del Apps Script la acción
  `expediente` sólo la aceptan el agente y `editor`. Cambiarlo es una línea del backend.
- Los horarios de GitHub llegan unas cuatro veces al día, con retraso.

## Cómo se apaga

Ajustes → tomas por día en 0 (no produce) y semillero apagado (no propone). O desactivar el
workflow «Sala 4.0 · Historias». Los documentos `v4:` y los videos de Drive se conservan.
