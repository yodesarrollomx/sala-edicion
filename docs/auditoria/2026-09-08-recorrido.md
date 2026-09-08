# Auditoría instrumentada de la Sala · 8-sep-2026

Pedido de Alejandro: «quiero todo tipo de reacción registrada en la página con métricas… si le picas
a esto, en el segundo 1 pasa esto y luego esto hace que suceda esto… y así todo hasta que veas que
cada acción está bien realizada: que copie, pegue, escriba, borre, salte renglón».

Herramienta: `docs/auditoria/instrumento.js` (se carga en la consola de la Sala con `?vista=editor`).
Registra con milisegundos cada clic, tecla, pegado, borrado, salto de renglón, deslizamiento, cambio
del DOM, escritura en el navegador y **el sobre exacto** que se manda al Sheet. La red al Sheet queda
interceptada, así que la prueba no escribe en el Sheet real; el contraste con el Sheet se hace aparte
con `~/yod_audit/sala_sobre.py` sobre un día aislado.

## A1 · Clic en «Aprobar» (lámina 4)

| Tiempo | Qué pasa |
|---|---|
| 0 ms | clic en Aprobar |
| 1 ms | borrador del día guardado en el navegador |
| 12 ms | la zona de la carta se repinta |
| 30 ms | el título pasa a «Faltan 2 decisiones» y la píldora a «Guardando…» |
| 1 827 ms | sale el sobre al Sheet: `laminas:["si","pendiente"]` |
| 1 831 ms | la cola queda vacía |
| 1 833 ms | píldora «Guardado ✓ 07:30» |

La carta cambia en 30 ms; el envío espera el compás de 1.2 s para no mandar un sobre por clic.

## A2 · «Pedir cambio» → la hoja de nota

| Prueba | Resultado |
|---|---|
| Abrir la hoja | 2 ms, foco en el cuadro de texto, fondo bloqueado |
| Enviar vacía | no cierra; avisa «Sin una línea, Producción no sabe qué cambiar» y marca el borde |
| Escribir | 22 caracteres, tecla por tecla |
| Botón rápido | concatena con punto: «La luz de la izquierda. La imagen no cuadra con el texto» |
| Salto de renglón | segundo renglón correcto |
| Pegar | entra con comillas y acentos |
| Borrar | 112 → 107 caracteres |

## A3 · Enviar la nota

La nota llega al sobre **idéntica**, con su salto de renglón y sus comillas; marcas `["si","no"]`.
Título, píldora y guardado: 4 ms, 1 883 ms, 1 888 ms.

## A4 · Deshacer ×2 y deslizar

Deshacer devuelve la carta en 5 ms y el contador se corrige. **Hallazgo grave:** no salía ningún
sobre al Sheet, que conservaba la marca vieja mientras la píldora decía «Guardando…».
Corregido: la guarda de subida ahora contempla los borrados explícitos.

Deslizar a la derecha aprueba (26 ms); a la izquierda abre la nota. Ambos suben.

## A5 · Sin señal

| Momento | Estado |
|---|---|
| Elegir con la red caída | cola con 1 sobre, píldora «Sin conexión con el Sheet · se guarda al volver» |
| «Reintentar ahora» con red | sube, cola en 0, píldora «Guardado ✓» |

## A6 · Capas

Mis respuestas abre en 2 ms con sus filas. «Cambiar» pide confirmación («Sí, borrar mi respuesta»)
y al segundo toque manda `borrar` al Sheet. La tira abre y cierra con la ×, con Escape y con el
botón «atrás» del teléfono. El zoom abre y cierra sin dejar el fondo bloqueado.

## A7 · Ajustes

El recado acepta renglones, comillas y pegado; al enviarlo el campo se vacía y avisa con la hora.

## M1 · Teléfono 375 × 812

| Momento | Alto de la carta |
|---|---|
| Antes | 289 px |
| Tras deslizar (antes del arreglo) | 200 px, lámina diminuta |
| Tras el arreglo | 243 px, cabecera encogida por pasos |

También: el pie de la carta se cortaba; ahora se desliza dentro de la carta.

## Hallazgos y correcciones de esta auditoría

| # | Hallazgo | Corrección |
|---|---|---|
| 1 | Deshacer no viajaba al Sheet y la píldora mentía | la subida contempla borrados; el estado se recalcula |
| 2 | Una llave rechazada dejaba la Sala en «Abriendo la mesa…» | pantalla «El Sheet no reconoció tu entrada» con «Entrar otra vez» |
| 3 | El candado anti-doble-toque dependía de un temporizador (800 ms en pestaña oculta) | se suelta por reloj a 260 ms |
| 4 | Doble escritura del borrador por decisión | una sola |
| 5 | En teléfono la lámina bajaba a 200 px | cabecera por pasos, mínimo 240 px |
| 6 | El pie de la carta se cortaba en teléfono | se desliza |
| 7 | Un id reusado con otras opciones desplazaba la marca vieja | el publicador aborta; id nuevo por versión |
| 8 | El comparador decía «en tu mesa» en versiones ya rehechas | dice «se rehízo» |

## Cómo repetir esta auditoría

1. Abrir `https://yodesarrollomx.github.io/sala-edicion/?vista=editor`.
2. En la consola: `eval(await (await fetch('docs/auditoria/instrumento.js')).text())`.
3. Correr los pasos A1…A7 y M1 de este documento, leyendo `T.saca()` después de cada uno.
4. Contrastar contra el Sheet con `python3 ~/yod_audit/sala_sobre.py <fecha-aislada> '<sobre>'`.
5. Cerrar con `python3 ~/yod_audit/sala_verificar.py`.
