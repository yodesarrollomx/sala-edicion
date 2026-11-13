# El canon de producción de las historias

Pedido de Dirección (Alejandro, 9-nov-2026, 19:04 de Hermosillo): que las historias de 15 segundos
no se vean «como pedazos separados»; que cada personaje, lugar y objeto sea el mismo en toda la
historia y entre historias («lo que decimos de Avengers»); que salga de «todo lo que hemos hecho»;
que él lo pueda cambiar en cualquier momento; que las referencias queden en Drive «para que sepamos
de quién se trata»; y que sea «el canon de producción para todo el futuro».

El canon son **datos**, no código. Vive en la hoja (`v4:universo` y `v4:mundo:<clase>`), se edita
en **Historias → Universo** y su versión de fábrica está en `datos/universo/universo.json`.

## De dónde sale cada regla

Nada de esto es gusto del programador. Cada regla viene de una nota fechada de Dirección o de una
pieza ya publicada.

| Regla del canon | De dónde sale |
|---|---|
| La cámara se mueve por el espacio; nunca una foto con acercamiento | Cortes de video rechazados el 20, 21 y 31-oct: «son movimientos de zoom» (`docs/SALA-CORTA-20261109.md`) |
| Voz natural, expresiva donde toca, un solo personaje hablando, sin narrador | 31-oct: «la voz está muy fea». 9-sep, nota al corte v6 de El Apodo: «las voces no sabes interpretar quién es narrador y quién es vecino», «voces más expresivas donde lo requiere» |
| Sonido de ambiente bajo y parejo | 9-sep: «el ruido de fondo muy alto, entra y sale, se corta» |
| Una serie es UNA conversación, pensada completa | 23/25-sep, La Mesa Vacía y Así Se Ve Saber: «las láminas como que son láminas separadas y no una misma conversación o relato»; «haz un solo guion y síguelo… piensa todo» |
| Continuidad de lugar y de personas entre tomas | 23-sep: «la primer imagen habla de otra cosa y de repente están dentro de la casa; hay que seguir la lógica de las imágenes: dónde están, contexto y personas» |
| La imagen muestra lo que dice la frase | El motivo más repetido de rechazo (44 % de las láminas): «la imagen no cuadra con el texto»; 15-sep: «la imagen no se ve un terreno en esquina como lo dice la lámina» |
| Lo que se enseña en papel se entiende desde la cámara | El comprador ya sabe: «son hojas en blanco, no hay nada que comparar. Algo muy esquemático, entendible desde la cámara» |
| Gente de clase media alta, con rasgos mexicanos; ciudad, no campo; imagen luminosa | «Cambia a la pareja: media alta» (varias veces); «no veo que sean de características latinas o mexicanas»; Sayri: «se ve un lugar rural, tendría que verse un lote baldío en ciudad»; «más luminosa» |
| En la pareja, ella dos o tres años menor | Dicho dos veces (`docs/CRITERIOS-LAMINA.md`): Sofía y Rodrigo |
| Frases para gente de 40 a 60 años, concretas | «Es para un público de 40 a 60»; «texto más concreto, menos vago»; «si no entienden pronto, se van» |
| El giro llega antes de la mitad | 9-sep: «es medio repetitivo, no llegamos al punto rápido» |
| Experto que propone, nunca ordena; tono positivo | 26-sep: «a nadie le gusta que le digan qué hacer… mejor que te propongamos los expertos» (`nube/motores/estrategia.py`) |
| Ficción honesta: nunca caso real ni testimonio | Mayo-2026, storyboards del Plan de Potencial: Dirección rechazó casos y testimonios inventados; lo hipotético se dice como supuesto |
| Sin ciudad, estado ni país; sin cifras de dinero, plazos ni garantías | Chinche 49 y candados (`docs/CONTENIDO-VETADO.md`, `docs/CRITERIOS-LAMINA.md`) |
| Cada episodio lleva encuadre, gesto y tono | Los storyboards de mayo ya lo traían por toma: «DIRECCIÓN: encuadre, gesto y tono» |
| El piloto fija el mundo visual | Nota de la FÁBRICA sobre La Mesa Vacía: «la 1 manda el mundo visual» |
| Cada cosa tiene un nombre fijo y su historia | `docs/LA-LEY.md`: sin identidad, todo parece nuevo |

## Lo que se rescató de lo ya hecho

Los personajes, lugares y objetos del canon no son nuevos: ya salieron en piezas aprobadas o
publicadas, sueltos. El canon los junta en un solo barrio.

- **Personajes:** Marta (el piloto de 15 segundos), Don Carlos («dudaba entre vender, rentar o
  construir locales en su esquina»), Sofía y Rodrigo (la pareja de las láminas), Don Roberto
  («¿Cuántos m² permite tu calle?»), Miguel («un día, Miguel se sentó en la cabecera», La Mesa
  Vacía), el comprador de la camioneta blanca (El comprador ya sabe) y el arquitecto, tomado del
  personaje con que Dirección graba sus videos (camisa verde olivo, lentes negros).
- **Lugares:** el terreno de la esquina («el de la esquina», El Apodo del Terreno), la mesa de la
  sobremesa (La Mesa Vacía, La Servilleta), el café luminoso donde se desliza la oferta.
- **Objetos:** la servilleta, el plano enrollado, la hoja del Plan («esa opinión cabe en una
  hoja»), los recibos del predial, la silla de la cabecera («esta silla es la tuya»), la camioneta
  blanca, la videollamada («el primer paso es una videollamada»).

## Cómo está armado

**El mundo.** Todas las historias pasan en la misma cuadra. Cada lugar tiene sus **anclas**: lo
que siempre se ve ahí (el olivo viejo de la esquina, el toldo verde del café).

**Las fichas.** Cada personaje tiene cara, vestuario fijo, voz, un gesto que lo distingue y su
objeto. Cada lugar, su aspecto y sus anclas. Cada objeto, su aspecto y lo que significa. Todo eso
entra, palabra por palabra, a la instrucción de cada toma donde aparece.

**Las imágenes de referencia.** Cada personaje, lugar y objeto que usa una serie aprobada tiene
una imagen en Drive, `_HISTORIAS/_CANON/`, en tres carpetas (`personajes`, `lugares`, `objetos`),
con el nombre de quien es. Esa imagen viaja al motor de video en cada toma donde aparece (hasta
cuatro por toma: quién sale, objetos y lugar). Sale de una de tres partes:

1. **La que pone Dirección.** Se sube la imagen (JPG o PNG) a la carpeta del canon y se pega su
   liga en la ficha. Manda sobre cualquier otra y la nube nunca la toca. Tiene que ser la liga de
   un archivo: la de una carpeta no se guarda y la pantalla lo dice.
2. **La que pinta la nube** a partir de la ficha, una sola vez. Si la ficha cambia, se vuelve a
   pintar.
3. **La que sale de un piloto.** Si el piloto de una serie se produjo sin imagen de su
   protagonista (las imágenes estaban apagadas, o Google no la aceptó), la cara que Dirección
   aprobó es la de ese piloto: la nube saca un cuadro del video y lo guarda en el canon como la
   imagen de ese personaje, para esa serie y para todas. No cuesta. Si el piloto se rehace, el
   retrato se vuelve a sacar; un piloto que se rehace nunca se copia a sí mismo.

La carpeta y `CANON.txt` (quién es quién, cómo se ve, la liga de su imagen y en qué series sale)
existen desde la primera corrida, haya o no series aprobadas.

**Un episodio espera a sus imágenes.** Con las imágenes de referencia encendidas, un episodio no
se produce hasta que lo que sale en él tenga su imagen al día; producido antes saldría distinto de
los demás. Mientras espera no gasta, y la corrida dice a quién espera. Con las imágenes apagadas
(«imágenes de referencia por día» en 0) no espera: el piloto sale del texto y de ahí se toma la
cara del protagonista.

**Lo que no cuesta va antes de gastar.** Antes de reservar una toma, la nube baja las imágenes
del episodio, saca el cuadro de arranque si continúa la escena anterior y revisa el veto de
ubicaciones sobre el texto completo, nota de Dirección incluida. Si una imagen no se puede leer
(por ejemplo, una propia que no está en la carpeta del canon), el episodio no se produce, no se
reserva y el aviso aparece en la serie.

**Si una imagen no se deja pintar.** El fallo queda anotado con su motivo y se ve en «El mundo de
esta serie». Esa imagen no se vuelve a pedir ese día (cada intento cuenta contra el tope) y lo
demás se sigue pintando; se reintenta al día siguiente, o enseguida si cambia la ficha o Dirección
pone su propia imagen.

**Los encuadres.** Una biblioteca de movimientos de cámara con nombre (seguimiento, revelación,
acercamiento al rostro, sobre el hombro, alrededor de la mesa, plano amplio, de las manos al
rostro, a través de la reja). Cada episodio elige uno.

**Los cruces.** Cada serie tiene un objeto propio y lleva guiños del mundo compartido que nadie
explica (la camioneta blanca que pasa, los recibos). El último episodio siembra la historia
siguiente. Si el guionista olvida un guiño o un invitado del plan, el código lo coloca.

**La temporada.** El plan de series que se cruzan; el semillero las escribe en orden:

1. *El terreno que no hacía nada*: Marta y las llaves. Plan de Potencial.
2. *El de la esquina*: Don Carlos y el plano. Captación de capital.
3. *La servilleta*: Sofía, Rodrigo y la servilleta. Arquitectura de autor.
4. *La libreta de Don Roberto*: la libreta. Control de obra.
5. *La mesa*: Miguel sienta a todos en la mesa del patio. Ahí se juntan las historias.

Cuando la temporada se acaba, el semillero propone historias libres con clientes nuevos, dentro
del mismo mundo.

## Qué se puede cambiar sin código

Todo, en **Historias → Universo**: la temporada (agregar, quitar, reordenar, cambiar premisa,
protagonista, guiños e invitados), personajes, lugares, objetos, encuadres, reglas del mundo,
formato de las tomas, vértices e instrucciones del guionista. En cada serie: su lugar y su objeto,
el encuadre, los objetos, los invitados y el tono de cada episodio, y las fichas propias de la
serie, que se pueden pasar al universo.

Lo que una serie o la temporada usa no se puede quitar: la pantalla dice quién lo usa.

## Dónde vive y cuánto cabe

Cada documento de la hoja vive en una sola celda, y una celda tiene tope. Por eso el canon se
guarda partido: los personajes, los lugares y los objetos van cada uno en su propia celda
(`v4:mundo:personajes`, `v4:mundo:lugares`, `v4:mundo:objetos`) y lo demás (temporada, encuadres,
reglas, formato, vértices, guionista y ajustes) en `v4:universo`. La pantalla lo parte sola la
primera vez que se guarda, y después sólo manda la parte que cambió. Un universo sin partir sigue
leyéndose igual, en la nube y en la pantalla.

Con las fichas del tamaño de hoy caben del orden de 70 personajes, 130 lugares y 150 objetos
compartidos, y unas 60 historias más en la temporada. Lo propio de cada serie no cuenta: vive en
el documento de esa serie. Si una parte se llena, la pantalla se niega a guardar y lo dice; se
resuelve acortando descripciones o quitando lo que ya no se usa (por ejemplo, las historias de
temporadas terminadas). Las imágenes anotadas por la nube (`v4:canon`) caben del orden de 300.

## Lo que cuesta

Una imagen de referencia cuesta alrededor de 4 centavos de dólar (tarifa publicada de
`gemini-2.5-flash-image`; no medida aquí) y se pinta una vez por personaje, lugar u objeto. Lo
limita el ajuste «imágenes de referencia por día» (de fábrica 6; en 0 no se pintan y la cara del
protagonista se toma del piloto). La reserva se anota antes de pedir la imagen y un fallo detiene
el paso. Sacar un retrato de un piloto y subir el índice no cuestan.

La simulación (botón «Sólo decir qué haría») pregunta además a Google si los modelos de guion, de
imágenes y de video siguen existiendo con esos nombres. Preguntar no cuesta, y avisa antes de
gastar si Google retiró o renombró alguno.

## Lo que NO está acreditado

- **Imágenes de referencia contra Google.** La guía oficial documenta referencias de personas,
  objetos y estilo, y que se pueden combinar con un primer cuadro. No se ha corrido en vivo. Si
  Google las rechaza, la toma baja un escalón (menos imágenes, y al final sólo texto) y lo avisa.
- **Pintar imágenes con esta llave.** El motor de imagen de Gemini ya existía en la Sala; con la
  llave de prepago no se ha usado.
- **Que el lugar salga igual con una imagen de referencia.** La guía no documenta referencias de
  lugar; va como una imagen más y puede no pesar. El texto del lugar y sus anclas sí viajan siempre.
- **La voz.** La guía dice que no se pueden subir referencias de audio ni elegir voz. La voz de un
  personaje se sostiene sólo describiéndola igual en cada toma. Es el punto más débil: hay que oír
  el piloto junto al episodio 2 antes de darlo por bueno.
- **Si Google rechaza las imágenes de personas.** Entonces cada toma sale sólo del texto y la cara
  puede variar de un episodio a otro. La toma lo avisa, pero el canon no lo puede arreglar: habría
  que encadenar episodios por su último cuadro («misma escena que el anterior») o buscar otra vía.
- **El guardado partido contra la hoja de verdad.** Probado con un backend simulado, incluido el
  caso de que una parte no llegue; no en vivo.
- Ninguna serie producida con el canon.
