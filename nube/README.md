# El ciclo de la Sala, en la nube

Hasta ahora `/sala` sólo existía en la Mac: los scripts en `~/yod_audit/`, las llaves en
`~/.sala_gas_claves.json`, los disparadores en `launchd`. Si la Mac se dormía, la Sala
amanecía sin respaldo y nadie se enteraba.

Esto es el mismo ciclo hablándole al **mismo `/exec` de siempre**, desde GitHub Actions.
El Sheet sigue mandando. Nada de la arquitectura de datos cambió: sólo quién la empuja.

## Para encenderlo (dos cosas que sólo puede hacer Alejandro)

**1. Los dos secrets.** En `Settings → Secrets and variables → Actions → New repository secret`:

| Nombre | De dónde sale |
|---|---|
| `SALA_GAS_EXEC` | la liga `/exec`, primera línea de `~/.sala_gas` |
| `SALA_CLAVE_AGENTE` | el campo `clave_agente` de `~/.sala_gas_claves.json` |

**Sólo la del agente.** Las de `editor`, `editor2` y `lector` no suben a la nube, porque el
agente no decide (INVIOLABLE 3). Si un día rotas las llaves, hay que actualizar este secret:
el GAS da 72 h de gracia con la anterior, así que no urge al minuto, pero no se olvida.

**2. Pages por Actions.** `Settings → Pages → Source` = **GitHub Actions** (hoy está en
«Deploy from a branch»). Sin ese cambio, `publicar.yml` corre y no sirve de nada: Pages
seguiría sirviendo la rama directo, sin pasar por el verificador.

## Cómo probarlo, en este orden

1. **Sonda** (`Actions → Sonda de la Sala → Run workflow`). Sólo lee. Baja el artifact
   `sonda-forma` y confirma que el día trae las llaves que `gas/Code.gs` promete. Revisa el
   log crudo: **no debe aparecer la clave en ningún lado.**
2. **Relevo en simulación** (`Relevo de la Sala → Run workflow` con *simular* en `true`).
   Dice qué haría y no escribe.
3. **Relevo en vivo.** Después, dispáralo **dos veces seguidas**: la segunda debe decir «el
   respaldo espejo ya estaba al día». Si duplica algo, algo está mal y hay que parar.
4. **Productor en simulación.** Confirma que con `productor_ejecuta_etapas` vacía no ejecuta
   nada, y que en horario quieto (23→7) se calla.

## Qué corre y cuándo

| Workflow | Cuándo | Qué hace | Escribe |
|---|---|---|---|
| `verificar.yml` | cada push y cada PR | las reglas del repo, el sello, los datos | nada |
| `publicar.yml` | cada push a `main` | verifica y sube a Pages | GitHub Pages |
| `sala-sonda.yml` | a mano | le pregunta al `/exec` vivo | nada |
| `sala-relevo.yml` | 6, 9, 12, 15 y 18 h | rehace el respaldo espejo | `datos/manifiesto.json` |
| `sala-productor.yml` | cada hora | abre compuertas y encola | la hoja COLA |
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

## Lo que NO se movió, y por qué

- **La producción pesada.** Una escena cuesta ~17 min de GPU; un runner de GitHub no tiene.
  La nube **encola**; ejecutar sigue siendo de la Mac o de un motor de API de la hoja MOTORES.
  No es una degradación: es el estado de fábrica que fija la invariante 54.
- **`progreso.json`, `piezas.json` y `metricas.json`.** Se arman de los archivos de producción
  que viven en la Mac y de las métricas de Instagram. La nube no los puede regenerar fielmente,
  y escribir una versión peor sería justo la clase de silencio que este sistema no se puede
  permitir. Los sigue publicando la Mac.
- **El recorrido de botones.** `sala_verificar.py` recorre la Sala en un navegador. Eso no
  cabe en `verificar.py`; sigue siendo paso de mano antes de dar algo por cerrado
  (INVIOLABLE 14).

## Si algo falla

Cada workflow que falla comenta en el issue **🔎 Vigía · Sala de Edición** con la etiqueta
`atencion`. Los códigos de salida del relevo dicen qué pasó:

- **2** — el Sheet no contestó. **No se tocó el respaldo.** «No contestó» nunca es «no hay
  nada» (INVIOLABLE 4): un respaldo viejo sirve, uno vacío no.
- **3** — contestó, pero sin marcas. Tampoco se escribe: un respaldo sin marcas volvería a
  preguntar lo ya decidido.
