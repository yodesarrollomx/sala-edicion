# Sala de Edición — *el portal diario donde Alejandro decide qué se produce*

Contexto para Claude Code. **Lee este archivo completo antes de tocar nada.**

## Qué es esto

El portal diario de producción de contenido de **Yo Desarrollo**. Cada mañana llega un correo con la
liga; el editor entra, palomea o tacha lo que se le propone, escribe su nota al margen y manda su
revisión. De ahí sale lo que la Mac produce ese día, y todo queda registrado día por día.

- **Quién lo usa:** Alejandro (`editor`) y **Sayri** (`editor2`) — los dos deciden por igual desde
  el 3-sep-2026 ([[sala-dos-editores]]). Clientes/socios entran como `lector` (solo miran). La Mac
  entra como `agente`: propone y reporta, **no decide**.
- **Dirección en vivo:** `https://yodesarrollomx.github.io/sala-edicion/` — **HTTP 200,
  comprobado con curl el 2026-09-04.**
- **Dirección vieja:** `https://alexpueblag.github.io/sala-edicion/` — **HTTP 200 (4-sep)**, pero
  ya NO es la Sala: es un cascarón que reenvía al dominio nuevo **y hace el puente de sesión**.
- **`tableros.yodesarrollo.mx/sala-edicion/` NO existe todavía** (curl 4-sep: código `000`, sin
  DNS). Si una memoria vieja usa esa liga, no la "arregles": el corte no ha pasado.
- El ciclo se gira con la frase **«corre la sala»** / `/sala` ([[sala-corre-la-sala]]).

## Reglas INVIOLABLES

1. **El repo es ESPEJO del Apps Script: lo que corre es lo pegado en el editor.** `gas/Code.gs` es
   una copia pública sin claves; cambiarlo aquí no cambia nada en vivo. (Hoy divergen: ver «Por
   confirmar».)
2. **Nunca subir claves al repo:** es público. Las 4 claves viven en `~/.sala_gas_claves.json` y la
   liga /exec en `~/.sala_gas` (ambos 600, 4-sep); el .gs público trae `'…'` (`gas/Code.gs:47`).
3. **Decidir es de los editores; el `agente` no marca.** El GAS contesta *«tu rol solo lee»* a un
   `accion:"decidir"` con `clave_agente` ([[sala-decisiones-viajan]]). Cualquier arrastre de marcas
   se hace del lado del cliente, en lectura.
4. **«No contestó» nunca es «no hay nada».** El 2-sep la Sala amaneció vacía por un
   `except: continue`; hoy `sala_relevo_diario.py` avisa y sale con código 2.
5. **Una carta re-presentada lleva id NUEVO + `origen: "rehecha-de <id viejo>"`.** Si reusa el id,
   la marca vieja cierra la carta nueva sin que el editor la vea (`normalizarDia`, `index.html:561`).
6. **Nunca montar una rehecha sin su tira.** La lámina 4 sola confunde; van las 9 con su guía
   (`datos/tiras/<pid>.json`, `cargarTira` en `index.html:695`).
7. **Un eje se cierra con un solo sí.** Un eje es «elige una»: exigir marca en todas las opciones
   hacía reaparecer lo ya decidido. Las tiras de láminas sí exigen todas.
8. **Cada compuerta se decide en su propio formato** — guion se lee, láminas se ven, voces se oyen,
   video se ve; `medio(src)` juega según extensión ([[sala-formatos-y-tarjetas]]).
9. **El correo de las 7:00 sale del GAS y va sólo a `CORREO` de CONFIG** (`gas/Code.gs:24` =
   `direccion@aurumarquitectos.com`). No cablear otro destinatario.
10. **Nada avanza sobre una pieza con petición abierta** (PASO 0 del ciclo: revisar
    `manifiesto.peticiones` antes de producir).

## Archivos

| Archivo | Qué hace |
|---|---|
| `index.html` (1,248 líneas) | La Sala completa, un solo archivo sin build. **Sala 3.0 «tres puertas»**: Hoy · Publicaciones · Ajustes (commit `c09b2c6`, 3-sep-2026). |
| `gas/Code.gs` (352 líneas) | Copia pública del backend. **Espejo, no fuente.** Instrucciones de instalación adentro. |
| `gas/appsscript.json` | Lleva `webapp: {executeAs: USER_DEPLOYING, access: ANYONE_ANONYMOUS}` — sin eso, cada versión nueva nacía cerrada y el /exec daba 404 ([[sala-dos-editores]]). |
| `datos/manifiesto.json` | **Respaldo espejo**: el relevo lo reescribe en cada corrida con sólo lo pendiente y las marcas horneadas. La Sala cae aquí si el Sheet no contesta. |
| `datos/tiras/<pid>.json` | La tira completa de una pieza (dice/ve/entiende, estado y nota por lámina). |
| `datos/piezas.json` · `progreso.json` · `maquinas.json` · `metricas.json` · `expedientes/*.json` | Estado vivo que publica la Mac: etapa de cada pieza, avance con «vuelve en ~X», semáforo de centinelas, números de las publicaciones, un expediente por pieza. |
| `laminas/<slug>/L*.png` + `.jpg` · `muestras/` · `video/` | Las láminas (el `.jpg` ligero es para la carta, el `.png` para zoom y publicación) y las escenas/voces de «Ver lo que ya salió». |
| `index-v1.html`, `index-v2.html`, `nueva.html` | Versiones anteriores que siguen en el repo. **No son la Sala.** No editarlas creyendo que sí. |

**Fuera del repo (`~/yod_audit/`):** `sala_publicar.py` (sube láminas/video, monta propuestas),
`sala_relevo_diario.py` (el relevo), `maquinas.py`, `progreso.py`, `encargos.py`. Centinelas
launchd verificados el 4-sep: `mx.yodesarrollo.relevo` (6, 9, 12, 15 y 18 h),
`mx.yodesarrollo.maquinas` (cada 1,800 s con `RunAtLoad`), `mx.yodesarrollo.sala`.

## Arquitectura de datos

El **Sheet manda**. El repo es superficie y respaldo.

```
Mac (~/yod_audit)                    Apps Script /exec (el Sheet)      La Sala (GitHub Pages)
sala_publicar.py ─ láminas/video ───────────────────────────────────▶ repo (imágenes, tiras)
                 ─ accion:proponer ────▶ pestaña PROPUESTAS
                 ─ accion:produccion ──▶ PRODUCCION + BITACORA
sala_relevo_diario.py ─ pendientes ───▶ PROPUESTAS (día vivo)
                      └─ respaldo espejo ──────────────────────────▶ datos/manifiesto.json

                        GET ?recurso=dia&clave=… ─────────────────▶ index.html (traer(): 3 intentos / 12 s)
                        (si no contesta) ─────────────────────────▶ datos/manifiesto.json (index.html:534)

editor (Alejandro / Sayri) ─ accion:decidir ─▶ DECISIONES ── el GAS toma el ÚLTIMO ENVÍO DE CADA
                                                             EDITOR y los fusiona (vigentePorEditor,
                                                             Code.gs:115). **El «no» manda.** v16.
GAS ─ trigger diario 7:00 (TZ America/Hermosillo) ─ correo con la liga ─▶ direccion@aurumarquitectos.com
```

- **/exec en vivo:** `https://script.google.com/macros/s/AKfycbx61UWsEYCL_dHzi0JrUv3GuAUFSDWW4iCmlNmbDDvWBIYY4Hhqkf6sYmt4d8UGIlk7MA/exec`
  (`index.html:442`, `GAS_DEF`). **La dirección no es secreta; sin clave no entrega nada** —
  comprobado con curl el 4-sep: HTTP 200 con cuerpo `{"error":"clave incorrecta"}`.
- **Pestañas que crea `instalar()`** (`gas/Code.gs:27`): CONFIG · PROPUESTAS · DECISIONES ·
  PARRILLA · CONTROL · PRODUCCION · BITACORA.
- **Acciones que acepta la copia del repo:** `decidir`, `parrilla_decision`, `proponer`,
  `parrilla`, `produccion`. Los botones «Mandar retro» y «Pedir /sala» reusan `produccion`
  **a propósito**, para no republicar el Apps Script ([[sala-maquinas-franja]]).
- **⚠️ EL REPO ES ESPEJO.** Para subir código: `clasp push` → *Manage deployments* → lápiz → **New
  version** → Deploy (la URL no cambia). `clasp create-deployment`/`update-deployment` rompen la
  entrada web. Hay ~40 s de propagación con 404: verificar con varios curl antes de cantar
  victoria. Y para POST al GAS desde la Mac, **`curl -L`**: `urllib` dio 404 una vez.

### El puente ORIGEN_VIEJO (la mudanza de dominio)

El navegador guarda la sesión **por dominio**. Al mudarse de `alexpueblag.github.io` a
`yodesarrollomx.github.io` el editor llegaba SIN llave y la Sala se quedaba en «buscando el
Sheet…». Arreglado por dos lados: (1) el **cascarón viejo** (verificado con curl 4-sep) lee su
propio `sala_gas`/`sala_clave`/`sala_rol` de localStorage y los manda en el `#hash` al dominio
nuevo antes de redirigir; (2) la Sala nueva declara `ORIGEN_VIEJO` (`index.html:443`) y pinta
**«Recuperar mi entrada»** → `<ORIGEN_VIEJO>#puente=1` (`index.html:1130`), que fuerza ese viaje.

**Una sola llave (3-sep):** si no hay `sala_clave` propia, vale la credencial del YOD OS
(`pyod_clave_v1`, mismo origen). **No se copia: se lee viva**, para que siga valiendo cuando el
Portero la renueve (commit `a026510`). Llaves en localStorage: `sala_gas`, `sala_clave`, `sala_rol`,
`sala_cola` (envíos pendientes), `sala2-<fecha>` (borrador del día).

## Decisiones

- **2026-08-01 · Alejandro + panel (Duolingo/Lingokids/Editor/Ingeniero)** — el ritual: UMBRAL →
  TURNO (una decisión por pantalla) → FIRMA → CIERRE → LA MESA. Porqué: tenía que caber en pocos
  taps; medido en 12 (límite 25).
- **2026-08-04 · conectada al Sheet** («Sala de Edición · YOD», Gmail personal). Porqué: ese día
  Alejandro revisó, su revisión quedó atrapada en el navegador y el día amaneció como si no hubiera
  decidido.
- **2026-08-05 · Alejandro (reclamo justo)** — nace el **registro de peticiones**: toda nota suya
  que pida un cambio al sistema se rastrea y no se cierra sin evidencia verificable.
- **2026-08-28 · Alejandro** — franja «Las máquinas» dentro de la misma Sala: «así puedo editar
  desde ahí o mandar retro y hacer /sala directamente».
- **2026-08-29 · respaldo espejo** — la Sala servía tarjetas viejas porque caía al manifiesto
  congelado; ahora el relevo lo reescribe cada corrida. Porqué: los arreglos «no llegaban».
- **2026-09-02 · Alejandro (desde el iPhone)** — un **borrador más nuevo que el Sheet manda**: no
  se filtra, no se canda, se restaura y sube solo. Porqué: sus 4 respuestas de las 14:00 casi se
  pierden contra un envío del Sheet de las 08:04 del mismo día.
- **2026-09-03 · Alejandro** — *«los dos somos editores… contempla ambas y cumple los criterios de
  ambos»*: GAS **v16** fusiona el último envío de cada uno, **el «no» manda**, notas firmadas. La
  marca del OTRO editor **no canda** tu carta (llega con franja azul).
- **2026-09-03 · Sala 3.0 «tres puertas»** (commit `c09b2c6`) tras la auditoría UX de la demo a
  Sayri: un solo orden, retorno consistente, solo-lectura honesta, textos en llano. Mismo día,
  **una sola llave** (commits `891215b` → `a026510`): la credencial del YOD OS vale en la Sala.
- ~~El repo se migra a la cuenta de usuario `yodesarrollo`.~~ **OBSOLETO desde 2026-08-27:**
  `sala-edicion` se transfiere a la organización **`yodesarrollomx`**. Ya está hecho (remote:
  `github.com/yodesarrollomx/sala-edicion.git`).
- ~~`tableros.yodesarrollo.mx/sala-edicion/` es la casa canónica.~~ **NO todavía (4-sep-2026):**
  el DNS no existe. La casa que responde es `yodesarrollomx.github.io/sala-edicion/`.

## Por confirmar (no afirmar sin preguntar)

- **La copia del repo va atrás del script desplegado.** `gas/Code.gs` NO contiene las acciones
  `entrada` (mandar la liga al correo) ni `canje_os` (entrar con Google vía Portero) que
  [[sala-dos-editores]] describe como desplegadas el 3-sep; y la cabecera aún dice «v3, espec de
  la mesa 1-ago» aunque el `version:` de la línea 230 ya diga `dos-editores-2026-09-03b`.
  **Pregunta: ¿bajamos la copia pública del editor para que el repo vuelva a ser espejo fiel?**
- **El id del Sheet «Sala de Edición · YOD»** no está en el repo (correcto: es privado); vive en el
  Gmail personal según memoria, no verificable desde aquí. Y **la rama local `dominio-propio`**
  existe sin remoto: ¿sigue viva o se borra?

## Pendientes

| Tema | Dueño | Evidencia para darlo por cerrado |
|---|---|---|
| DNS de `tableros.yodesarrollo.mx` | Alejandro (con Miguel Reina / cPanel) | `curl -I https://tableros.yodesarrollo.mx/sala-edicion/` → 200 (hoy `000`). Al cortar: cambiar `PORTAL` en `gas/Code.gs:23` **a mano en el editor** y la liga de `sala_publicar.py:127`. |
| Bajar la copia pública del .gs desplegado al repo | Claude / agente | `diff` del contenido del editor contra `gas/Code.gs` sin diferencias de funciones (hoy faltan `entrada` y `canje_os`). |
| `~/yod_audit/sala_publicar.py.nuevo` está **desactualizado**, no adelantado | Claude / agente | Le faltan `origen`, `tira` y el .jpg ligero que sí trae el vivo (`diff` 4-sep). O se regenera o se borra. |
| `gas/appsscript.json` declara `timeZone: America/New_York` mientras `Code.gs:22` usa `America/Hermosillo` | Alejandro decide (tocarlo obliga a redesplegar) | Ver si algún cálculo de fecha se corre; si no, dejarlo documentado y no moverlo. |
