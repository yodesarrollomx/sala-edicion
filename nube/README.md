# El ciclo de la Sala, en la nube

Hasta ahora `/sala` sólo existía en la Mac: los scripts en `~/yod_audit/`, las llaves en
`~/.sala_gas_claves.json`, los disparadores en `launchd`. Si la Mac se dormía, la Sala
amanecía sin respaldo y nadie se enteraba.

Esto es el mismo ciclo hablándole al **mismo `/exec` de siempre**, desde GitHub Actions.
El Sheet sigue mandando. Nada de la arquitectura de datos cambió: sólo quién la empuja.

## Para encenderlo (lo que sólo puede hacer Alejandro)

**1. Los cinco secrets.** En `Settings → Secrets and variables → Actions → New repository secret`:

| Nombre | De dónde sale |
|---|---|
| `SALA_GAS_EXEC` | la liga `/exec`, primera línea de `~/.sala_gas` |
| `SALA_CLAVE_AGENTE` | el campo `clave_agente` de `~/.sala_gas_claves.json` |
| `GDRIVE_SA_JSON` | el JSON completo de una cuenta de servicio de Google (ver abajo) |
| `HF_TOKEN` | huggingface.co → Settings → Access Tokens (lectura basta) |
| `GEMINI_API_KEY` | aistudio.google.com → API key (el respaldo de voz, si se usa) |

**Sólo la clave del agente**, nunca las de editor/editor2/lector: el agente no decide
(INVIOLABLE 3). Si rotas las llaves, actualiza `SALA_CLAVE_AGENTE` — el GAS da 72 h de gracia
con la anterior, así que no urge al minuto, pero no se olvida.

**2. La cuenta de servicio de Drive.** `console.cloud.google.com` → IAM → Cuentas de servicio
→ Crear → Claves → Crear clave → JSON. Ese archivo completo es `GDRIVE_SA_JSON`. Luego, en
Drive, comparte la carpeta **«YOD Editorial»** con el correo de esa cuenta
(termina en `.iam.gserviceaccount.com`) como **Editor** — una sola vez. Y siembra la REGLA
`drive_raiz` con el id de esa carpeta (`sembrar_reglas_nube.py` la deja vacía a propósito: sin
ella, la nube produce local pero no sube nada, y lo dice en cada corrida).

**3. Pages por Actions.** `Settings → Pages → Source` = **GitHub Actions** (hoy está en
«Deploy from a branch»). Sin ese cambio, `publicar.yml` corre y no sirve de nada.

## Cómo probarlo, en este orden — NINGUNO se salta

1. **Sonda** (`Actions → Sonda de la Sala → Run workflow`). Sólo lee. Confirma que el día
   trae las llaves que `gas/Code.gs` promete. Revisa el log crudo: **la clave nunca aparece.**
2. **Relevo en simulación**, luego en vivo **dos veces seguidas**: la segunda debe decir «el
   respaldo espejo ya estaba al día». Si duplica algo, algo está mal y hay que parar.
3. **Productor en simulación.** Con `productor_ejecuta_etapas` vacía no ejecuta nada, y en
   horario quieto (23→7) se calla.
4. **Ejecutor en simulación, con `nube_ejecuta_etapas` vacía.** Debe decir «el seguro de
   fábrica sigue puesto» y no tocar nada — es la prueba de que el seguro de verdad frena.
5. **Enciende `nube_ejecuta_etapas` con SÓLO `voz`** (`accion:regla` o a mano en el Sheet) y
   deja que el ejecutor produzca **una sola voz real**. Escúchala. Si Kokoro no cuaja (el
   runner tardó demasiado, la primera descarga del modelo falló), la cascada cae a
   `gemini_tts` — eso se reporta en el log, no se sustituye en silencio. No se agrega `escena`
   ni `corte` a la lista hasta haber escuchado una voz de verdad.
6. **Después, `escena`**: un corte de prueba con una sola lámina, revisando que la animación
   de `wan_hf` de verdad corresponda a la lámina.
7. **Al final, `corte`**: comparar el resultado contra el último corte real de la Mac —
   mismo encuadre (sin franjas), márgenes de audio correctos. **Ningún corte de la nube se
   publica sin que Alejandro lo vea primero.**

## Qué corre y cuándo

| Workflow | Cuándo | Qué hace | Escribe |
|---|---|---|---|
| `verificar.yml` | cada push y cada PR | las reglas del repo, el sello, los datos | nada |
| `publicar.yml` | cada push a `main` | verifica y sube a Pages | GitHub Pages |
| `sala-sonda.yml` | a mano | le pregunta al `/exec` vivo | nada |
| `sala-relevo.yml` | 6, 9, 12, 15 y 18 h | rehace el respaldo espejo | `datos/manifiesto.json` |
| `sala-productor.yml` | cada hora | abre compuertas y encola | la hoja COLA |
| `sala-ejecutor.yml` | cada 2 h | produce escena/voz/corte (si están encendidas) | Drive + la COLA |
| `sala-maquinas.yml` | cada 2 h | salud de los centinelas | `datos/maquinas.json` |

Los crons van en **UTC-7 fijo** (America/Hermosillo, sin horario de verano).

## Tres cosas que hay que saber y que no son obvias

**Los crons de Actions no son puntuales.** Se retrasan de 5 a 30+ minutos en horas pico. El
único horario que tiene que ser exacto —el correo de las 7:00— lo manda Google desde el propio
Apps Script, no nosotros, y eso no se tocó.

**GitHub apaga los crons de un repo que lleva 60 días sin actividad.** Los commits del propio
ciclo lo mantienen despierto. Si algún día se apagan, el semáforo lo delata antes que nadie.

**Un commit hecho por un workflow no dispara otros workflows.** GitHub lo bloquea para evitar
bucles. Por eso el relevo y el semáforo llaman a `publicar.yml` a mano (`gh workflow run`)
después de commitear: sin eso, el respaldo se guardaría en `main` y nunca llegaría a la Sala
en vivo.

## Lo que la nube SÍ ejecuta ahora, y lo que sigue sin ejecutar

Corrección sobre la fase anterior: aquí se dijo que «ejecutar sigue siendo de la Mac». Ya no
del todo — `wan_hf` (escena) y `gemini_tts`/Kokoro (voz) son APIs o CPU pura, y el corte es
ffmpeg. Los tres corren en un runner sin GPU. Lo que sigue siendo **sólo de la Mac**, porque
de verdad necesita GPU local: `mflux` (la imagen) y `ltx_local` (el respaldo de escena). La
nube los ve encendidos en MOTORES y los salta siempre — no los apaga en el Sheet, porque la
Mac los sigue necesitando.

El seguro de la invariante 54 sigue intacto: `nube_ejecuta_etapas` nace vacía. Nada de esto
ejecuta un gramo hasta que Alejandro la enciende.

- **`progreso.json`, `piezas.json` y `metricas.json`** se arman de archivos de producción de
  la Mac y de métricas de Instagram. La nube no los puede regenerar fielmente. Los sigue
  publicando la Mac.
- **El recorrido de botones** (`sala_verificar.py`, en un navegador) sigue siendo paso de
  mano antes de dar algo por cerrado (INVIOLABLE 14).

## Límites honestos de esta fase (léelos antes de encender nada)

- **`escena_wan_hf.py` es el menos probado de los tres motores.** La política de red de donde
  se escribió esto bloquea huggingface.co por completo — ni siquiera se pudo ver la forma de
  un error real, a diferencia de Drive y Gemini (esos sí se probaron contra Google en vivo,
  con credenciales falsas). Tampoco adivina un modelo de HuggingFace: la REGLA
  `escena_wan_hf_modelo` nace vacía, y sin ella el trabajo se queda `pendiente` — nunca
  intenta una llamada a ciegas a un modelo que nadie confirmó.
- **Los pesos de Kokoro (~300 MB) tampoco se pudieron descargar** en ese mismo entorno — se
  confirmaron las ligas reales (vienen del propio paquete `kokoro-onnx`, verificado con `pip
  show`), pero la primera síntesis de verdad sólo se puede escuchar en el workflow, con
  internet normal. Por eso el paso 5 de arriba no es opcional.
- **`sala_montador.py` se reconstruyó desde el manual**, no desde `apodo/montar_v2.py` (que
  vive sólo en la Mac). SÍ se probó de verdad con ffmpeg real — escena de 640×480 cubriendo un
  cuadro de 1080×1920 sin franjas, audio con sus márgenes, y que se niega a armar un corte si
  a una lámina le falta su escena o su voz — pero un ffmpeg que corre bien no es lo mismo que
  un corte que se ve como el de Alejandro. El paso 7 de arriba existe por eso.
- **El corte busca la escena/voz de cada lámina por su id exacto en la COLA**
  (`pieza:etapa:item:huella`), nunca por un archivo que haya quedado tirado en el runner —
  porque el corte puede correr en una invocación distinta (o mucho después) de la que produjo
  cada lámina. Si a una lámina le falta una pieza, el corte se niega a armarse incompleto.

## Si algo falla

Cada workflow que falla comenta en el issue **🔎 Vigía · Sala de Edición** con la etiqueta
`atencion`. Los códigos de salida del relevo dicen qué pasó:

- **2** — el Sheet no contestó. **No se tocó el respaldo.** «No contestó» nunca es «no hay
  nada» (INVIOLABLE 4): un respaldo viejo sirve, uno vacío no.
- **3** — contestó, pero sin marcas. Tampoco se escribe: un respaldo sin marcas volvería a
  preguntar lo ya decidido.

**El ejecutor es distinto a propósito:** que UN trabajo salga `fallo` no abre un issue ni
tumba la corrida — ya queda escrito en su propia fila de COLA (visible desde Ajustes de la
Sala), y uno intermitente se reintenta solo. El issue sólo se abre cuando la corrida ENTERA
no pudo trabajar (REGLAS, COLA o el catálogo no contestaron) — ahí sí nadie más se entera si
esto no avisa.

## 23-sep · Los dos eslabones que faltaban (gratis primero)

La nube ya no se queda sin nada que hacer por falta de la Mac:

| Etapa | Motores, en orden | Costo |
|---|---|---|
| `escena` | `wan_hf` (animación real) → **`camara`**: movimiento lento sobre la lámina entera, ffmpeg en el runner | 0 |
| `prospecto` (candidata nueva tras un «no») | cerebro: Gemini `cerebro_modelo` → OpenAI con tope `cerebro_pago_tope_dia`; imagen: Cloudflare FLUX schnell → Gemini imagen (`imagen_motores`) | 0; el respaldo OpenAI queda muy por debajo de 1 USD/día |

**Bug corregido:** el productor encolaba escena/voz/prospecto sin `src` de la lámina, y el
motor de escena no podía encontrarla nunca («sin id de Drive» → `pendiente` para siempre).
Ahora la evidencia lleva `src`, `dice`, `ve` y la nota del «no»; los trabajos viejos la
recuperan de su tira (`motores/_comun.lamina_de`). La imagen se toma del repo si está en el
checkout y, si no, de Drive.

**Para encenderlo:** secrets `CF_ACCOUNT_ID` y `CF_API_TOKEN` (cuenta gratis de Cloudflare →
Workers AI → REST API); `OPENAI_API_KEY` es opcional. Luego, en la REGLA
`nube_ejecuta_etapas`, agrega `escena,prospecto` (el seguro de fábrica sigue siendo tuyo).

**Aún no:** montar el prospecto en la mesa del editor. Hoy queda producido y subido a Drive
con su receta en la evidencia de la COLA; montarlo (accion:proponer) es el siguiente paso.


## Rotar la clave del agente sin Mac (23-sep)

La clave del agente estuvo pública (fuga del 23-sep) y ya no hay Mac para `rotar_claves`.
Se rota **sólo la del agente**; las de editor/editor2/lector no se tocan (son de las personas).

1. Genera una cadena nueva de 16 caracteres hex (cualquier generador; no la escribas en chats).
2. En el Sheet «Sala de Edición · YOD», hoja **CONFIG**: en la fila `clave_agente` cambia el
   valor por la nueva. (Si hay filas repetidas de `clave_agente`, cámbialas todas.)
3. En el repo → Settings → Secrets → Actions → `SALA_CLAVE_AGENTE` → pega la misma.
4. Corre «Sonda de la Sala»: debe contestar sin «clave incorrecta».

Entre el paso 2 y el 3 los workflows fallan con «clave»: hazlos seguidos.
