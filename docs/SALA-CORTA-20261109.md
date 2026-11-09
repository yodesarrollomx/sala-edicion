# Sala corta · 9-nov-2026

Decisión de Dirección (Alejandro, 9-nov-2026, por chat) tras revisar por qué la Sala no estaba
dando publicaciones. Propuesta en el atlas: `CHG-SALA-CORTA-20261109` (yod-portal #347).
Este documento manda sobre las menciones anteriores a horarios y a la línea de video.

## Lo que se encontró (medido, no supuesto)

| Qué | Dato del 9-nov-2026 |
|---|---|
| Publicaciones salidas de la Sala | 3 en total: 29-ago, 2-sep y 14-sep. Ninguna después. |
| Últimas decisiones humanas | 31-oct. La hoja CONSEJO sólo tenía encabezado. |
| Video | Todos los cortes de nube rechazados el 20, 21 y 31-oct («son movimientos de zoom», «la voz está muy fea»). |
| Salida | No había etapa de copy ni publicador desde que se fue la Mac. |
| Láminas | 432 juzgadas: 244 sí y 188 no (44 % de rechazo). Motivo más repetido: «La imagen no cuadra con el texto». |
| Ideas | 641 guardadas, unas 26 elegidas, unas 11 nuevas al día. |
| Maquinaria | 46 workflows, unas 100 PR automáticas abiertas, 126 ramas de trabajo. |
| Aprobado sin publicar | 4 carruseles completos y unas 6 láminas sueltas. |

El cuello no era la aprobación. Era que el video gratuito no alcanza el estándar y que no había
salida, mientras la maquinaria seguía creciendo.

### Los horarios de GitHub no son un reloj

Sobre las 68 corridas programadas de «Sala · Cada hora» entre el 7 y el 9-nov (UTC):

| Proceso | Declarado al día | Corrió al día | Hueco medio | Hueco máximo |
|---|---|---|---|---|
| productor | 72 | 4.6 | 5.6 h | 10.2 h |
| mesa | 24 | 3.9 | 6.3 h | 10.7 h |
| arranque | 24 | 3.9 | 5.7 h | 8.6 h |
| chinches | 24 | 3.9 | 5.7 h | 9.2 h |
| ejecutor | 12 | 3.9 | 6.7 h | 10.9 h |
| semáforo | 12 | 3.9 | 6.7 h | 10.9 h |

GitHub entrega cada horario de esa puerta unas cuatro veces al día, diga lo que diga el cron.
La puerta «Sala · Diario» llega con 5 a 7 horas de retraso: la mesa «de las 5:40» sale pasadas
las 11. Declarar más frecuencia no la consigue y declarar menos no ordena nada. Lo que falta es
un reloj confiable que oprima los botones (`workflow_dispatch`), y ese reloj es la tarea
programada del consejo (parte 2).

## Lo que se decidió

1. **Publicar:** paquete ya, botón después. Publicar es siempre el clic de Dirección.
2. **Video:** en pausa. Primero láminas y carruseles; el video vuelve con un piloto de una pieza
   cuando un motor alcance el estándar.
3. **Roast Room:** al frente y en la nube. Aprueba guion y láminas con los candados y regresa a
   rehacer; Dirección sólo ve paquetes terminados. Un solo motor (Claude, con la suscripción de
   Dirección, como tarea programada). Sol contra Opus vuelve cuando Hermes tenga servidor 24/7.
4. **Pausas:** generador de ideas y video gratuito en pausa; las automatizaciones sobrantes se
   archivan. Nada se borra.

La línea única: **idea elegida → guion → láminas → paquete listo (imágenes + copy) → clic de
Dirección → métricas**. Se mide en publicaciones por semana.

## Lo que cambió

### En el Sheet (inmediato, reversible)

| Regla | Antes | Ahora | Efecto |
|---|---|---|---|
| `nube_ejecuta_etapas` | `voz,escena,corte,prospecto` | `prospecto` | El ejecutor no hace escena, voz ni corte. |
| `consejo_motores` | `sol,opus` | `sol` | Un solo motor mientras llega el consejo de nube. |
| `semillero_activo` | (no existía) | `0` | El generador de ideas calla. Se pone al fusionar este cambio. |

### En el repositorio (este cambio)

- `nube/sala_arranque.py`: el semillero respeta `semillero_activo`. Con `0`, `no`, `false` o
  `pausa` no lee hojas, no gasta motor y no escribe ideas ni premisas, lo lance quien lo lance
  (horario, botón o recuperación del día). Sin la regla, o con `1`, siembra como siempre. El
  arranque de ideas **ya elegidas** no depende de esa regla.
- `.github/workflows/sala-cada-hora.yml`: el productor y el ejecutor ya no tienen horario.
  Conservan su archivo y su botón (`proceso: productor` / `ejecutor`). Sirven a escena, voz y
  corte; las láminas rechazadas las rehace el montador de la mesa (`sala_mesa.py`). Los
  prospectos que abre el productor se guardan en Drive y ningún proceso de la nube los monta.
- `.github/workflows/sala-revision.yml`: se retiró la revisión de cada 15 minutos. Queda la
  diaria de las 07:05 y el botón. Alimenta sólo el panel Ajustes → Revisión diaria.
- `nube/revision_diaria.py` y `nube/sala_maquinas.py`: dicen los horarios que de verdad están
  escritos. Un proceso sin horario se anuncia «Sólo a mano».
- Mesa, arranque, chinches, relevo y semáforo **no se tocaron**.
- Aviso: `sala-cierre-online.yml` (comprobación manual del 15-oct) exige las cuatro etapas
  encendidas. Con el video en pausa contestará `etapas_no_habilitadas`; es lo esperado.

### En Drive

`YOD Editorial/_LISTAS PARA PUBLICAR`: una carpeta por pieza con `01.png`…`05.png` (las tomas
elegidas, en orden) y un documento `COPY · <título>` con el texto de Instagram, el primer
comentario con la liga, el texto de Facebook y la revisión contra candados. Nada se publica solo.

## Cómo se regresa

- Video: REGLAS `nube_ejecuta_etapas` = `voz,escena,corte,prospecto` y devolver sus dos horarios
  a `sala-cada-hora.yml` (revertir este cambio).
- Ideas: REGLAS `semillero_activo` = `1`, o borrar la fila.
- Consejo: REGLAS `consejo_motores` = `sol,opus`.
- Se conservan DECISIONES, CANDADOS, CONSEJO, IDEAS, medios y paquetes de Drive.

## Lo que sigue (cada uno con su propio cambio y su evidencia)

1. **Consejo de nube, que además es el reloj.** Tarea programada de Claude: lee la mesa, juzga
   con los candados y manda sus veredictos a `sala-consejo.yml`; la Action los valida y decide
   con la llave del consejo, que sigue viviendo sólo en los secretos de Actions. Al terminar
   lanza la mesa y el arranque para que la siguiente ronda salga enseguida.
2. **Paquete automático** al quedar completa una pieza, con su copy.
3. **Botón «Publicar»** en la Sala, accionado por Dirección.
4. **Archivo** de los workflows sobrantes y cierre de las PR automáticas viejas.

## Lo que este documento no acredita

Ninguna publicación nueva, ninguna corrida del consejo de nube y ninguna semana de latidos en
verde. Las cifras son lecturas del 9-nov-2026 y conservan esa fecha.
