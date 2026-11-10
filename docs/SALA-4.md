# Sala 4.0 · historias en episodios de 15 segundos

Decisión de Dirección (Alejandro, 9-nov-2026, por chat) después de ver el piloto con Gemini Omni
Flash: «vamos a contar una historia en 10 días de 15 segundos, en bloques de escenas de 15 o 30
segundos», con semillero limpio nutrido de lo pasado, todo en línea, en automático, y editable
desde la Sala sin tocar código. Antes había pedido lo mismo con sus palabras: una sola escena por
video, personajes guardados e historias que se entrelazan al final, y el cliente siempre de
protagonista.

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
5. **Universo**: vértices, personajes, lugares, formato de cámara y las **instrucciones para el
   guionista** (el criterio con que se escriben las historias; es texto, se cambia ahí mismo).
6. **Ajustes**: semillero encendido o apagado, cuántas propuestas esperan, episodios por serie,
   **tomas por día** (el tope de gasto), piloto primero y el modelo que escribe.

## El mismo personaje en todos los episodios

Del piloto aprobado la nube saca un **retrato** (un cuadro del video) y lo guarda en Drive junto a
los episodios. Los episodios siguientes mandan ese retrato a Omni como imagen de referencia
(`reference_to_video`), y el texto dice quién es la persona de la imagen. Si el piloto se rehace,
el retrato se vuelve a sacar de la versión nueva. Un episodio marcado «misma escena que el
anterior» no usa retrato: arranca en el último cuadro del episodio previo.

Cada toma baja un escalón si Google rechaza la imagen (HTTP 400, que no se cobra): del último
cuadro del episodio anterior al retrato, y del retrato a sólo texto. Así un bloque de 30 s no
pierde la primera toma ya pagada, y la pantalla avisa en el episodio qué no se pudo usar.

## Historias que se cruzan

En la serie, **Guardar en el universo** copia al protagonista con su retrato. Desde entonces:

- En cualquier episodio de otra serie se puede marcar como **invitado**; viaja con su retrato y
  sale igual que en su historia.
- El semillero recibe la lista de personajes conocidos (los guardados y los protagonistas de series
  aprobadas) y puede proponer que **uno aparezca en el último episodio**, para entrelazar las
  historias.

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
| `v4:universo` | editor | formato, ajustes, vértices, personajes, lugares, guionista |
| `v4:serie:<id>` | quien la crea; después sólo el editor | la historia y sus episodios |
| `v4:dec:<id>` | editor | aprobar la serie; sí / cambio / no por episodio y versión |
| `v4:prod:<id>` | nube | versiones, ligas de Drive, retratos, intentos por día, paquete, avisos |
| `v4:estado` | nube | qué hizo la última corrida |

`nube/sala_v4.py` se niega, antes de la red, a escribir decisiones o a pisar lo del editor. Cada
documento vive en una celda del Sheet (tope real: 50 000 caracteres); la nube y la pantalla se
niegan a guardar uno de más de 45 000 y lo dicen.

`.github/workflows/sala-v4.yml` lo corre con horario y con botón: semillero → productor → paquete
→ estado. En Drive: los videos y el retrato en `_HISTORIAS/<serie>/`, el paquete en
`_LISTAS PARA PUBLICAR/Historia · <título>` (la misma carpeta de la estación de salida).

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

## Comprobado en vivo (9-nov-2026, hora de Hermosillo)

- Texto a video de 15 s con voz, Gemini Omni Flash: corrida 42726461524 (el piloto que vio
  Dirección).
- La pantalla publicada lee la hoja con la llave de Dirección y muestra las series.
- La nube lee la hoja como agente: corrida de simulación 42737798270.
- La nube siembra el universo y propone una serie de 10 episodios: corrida 42737957598 dejó
  «El Heredero del Olivo», y la pantalla la mostró como «Propuesta · espera tu decisión».

## Lo que NO está acreditado

- **Imágenes de referencia en vivo.** El retrato y los invitados están probados con el contrato
  que publica Google, no contra Google. La primera serie aprobada lo dirá; si Google las rechaza,
  la toma sale del texto y se avisa.
- Que el personaje salga de verdad igual de un episodio a otro, aun con retrato.
- Ninguna serie completa producida, ningún paquete y ninguna publicación.
- El reproductor de Drive dentro de la pantalla en iPhone; por eso está «Abrir en Drive».
- **Sayri (`editor2`) puede ver, pero no guardar**: en la copia pública del Apps Script la acción
  `expediente` sólo la aceptan el agente y `editor`. Cambiarlo es una línea del backend.
- Los horarios de GitHub llegan unas cuatro veces al día, con retraso.

## Cómo se apaga

Ajustes → tomas por día en 0 (no produce) y semillero apagado (no propone). O desactivar el
workflow «Sala 4.0 · Historias». Los documentos `v4:` y los videos de Drive se conservan.
