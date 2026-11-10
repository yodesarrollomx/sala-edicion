# Sala 4.0 · historias en episodios de 15 segundos

Decisión de Dirección (Alejandro, 9-nov-2026, por chat) después de ver el piloto con Gemini Omni
Flash: «vamos a contar una historia en 10 días de 15 segundos, en bloques de escenas de 15 o 30
segundos», con semillero limpio nutrido de lo pasado, todo en línea, en automático, y editable
desde la Sala sin tocar código.

Mapas (Graphify): `docs/grafos/sala-actual.html` (cómo funciona hoy) y `docs/grafos/sala-4.html`
(el plan). Los dos salen de `docs/grafos/construir.py`.

## Qué es

Una **serie** cuenta una historia en N episodios (de fábrica 10), uno por día. Cada episodio es una
toma continua de 15 s con la voz del propio modelo, o un bloque de 30 s hecho de dos tomas (la
segunda arranca en el último cuadro de la primera). El protagonista siempre es un cliente; cada
serie cambia de industria y enseña un vértice del negocio.

## Cómo se usa (Dirección)

1. En la Sala, botón **Historias** (o `historias.html`).
2. **Series**: el semillero deja propuestas. Se abren, se edita el texto si hace falta y se toca
   **Aprobar la serie** o **No va**. También hay **Nueva serie** para escribir una propia.
3. La nube produce primero el **episodio 1**. Se ve ahí mismo y se marca **Sí**, **Pedir cambio**
   (con nota: se rehace como versión nueva) o **No va**. Con el «sí» del primero siguen los demás.
4. Cuando todos tienen «sí», la nube deja el **paquete** en Drive: los episodios, la historia
   completa unida y un borrador de copy. **Publicar sigue siendo el clic de Dirección.**
5. **Universo**: personajes, lugares, vértices y formato de cámara. **Ajustes**: semillero
   encendido o apagado, episodios por serie y **tomas por día**, que es el tope de gasto.

## Dónde vive cada cosa

Todo en la hoja EXPEDIENTES, con `recurso=expedientes` y `accion=expediente`, que el Apps Script
ya atendía. **No se cambió el backend.** Cada documento tiene un solo dueño:

| Llave | Dueño | Contenido |
|---|---|---|
| `v4:universo` | editor | formato, ajustes, vértices, personajes, lugares |
| `v4:serie:<id>` | quien la crea; después sólo el editor | la historia y sus episodios |
| `v4:dec:<id>` | editor | aprobar la serie; sí / cambio / no por episodio y versión |
| `v4:prod:<id>` | nube | versiones, ligas de Drive, intentos por día, paquete, avisos |
| `v4:estado` | nube | qué hizo la última corrida |

`nube/sala_v4.py` se niega, antes de la red, a escribir decisiones o a pisar lo del editor.
`.github/workflows/sala-v4.yml` lo corre con horario y con botón: semillero → productor →
paquete → estado. Los videos quedan en Drive, `_HISTORIAS/<serie>/E01-v1.mp4`.

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
- *Piloto primero*: los episodios 2 en adelante esperan el «sí» del 1, para no producir diez tomas
  de una serie que no gustó.
- *Decisión vieja sobre versión nueva*: cada marca guarda su versión; al rehacer deja de aplicar.
- *Dos escritores sobre el mismo documento*: no existen; cada llave tiene un dueño y el flujo corre
  de uno en uno.
- *Texto del modelo mal formado*: se valida forma, número de episodios y que cada frase quepa en
  15 s (38 palabras); un segundo intento y, si no, no se propone nada.
- *Bloque de 30 s*: cuenta dos tomas y no entra a medias si el tope no alcanza.

## Lo que NO está acreditado

- La acción `expediente` se leyó en la copia pública del Apps Script; falta comprobarla en vivo.
  En esa copia sólo escriben el agente y `editor`: **Sayri (`editor2`) puede ver, pero no guardar**
  hasta que se cambie una línea del backend.
- Que el personaje salga igual de un episodio a otro. La continuidad disponible es arrancar en el
  último cuadro del episodio anterior; no hay todavía imagen de referencia del personaje.
- Los horarios de GitHub llegan unas cuatro veces al día, con retraso.
- Ninguna serie completa producida, ningún paquete y ninguna publicación.

## Cómo se apaga

Ajustes → tomas por día en 0 (no produce) y semillero apagado (no propone). O desactivar el
workflow «Sala 4.0 · Historias». Los documentos `v4:` y los videos de Drive se conservan.
