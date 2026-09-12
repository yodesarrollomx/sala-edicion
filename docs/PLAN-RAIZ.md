# Plan «proceso de raíz» — producción en ramas, nunca detenida (12-sep-2026, borrador para su OK)

## Lo que pidió (textual, ordenado)
- Que la producción NO sea lineal (lámina → sí → animar → voz → corte → sí): que cada etapa
  tenga VARIOS prospectos corriendo solos, y que lo aprobado en una rama dispare la siguiente
  sin esperar a que todo lo demás esté decidido.
- Todo configurable en Sheets, nada hardcodeado. Auditado, registrado, documentado.
- Un solo run, con pruebas de proceso (incluidas las acciones raras que rompen).
- Sonnet la talacha, Opus lo delicado, Fable planea. Probado desde su Chrome al final.

## Diagnóstico corto del sistema (qué frena)
| recurso | costo | estado real hoy | uso en el plan |
|---|---|---|---|
| imágenes mflux (Mac) | 0 | ~6.5 min c/u, ilimitado | motor #1 de láminas y prospectos |
| video LTX local (Mac) | 0 | ~17 min/escena, a veces zoom-reversa | respaldo; wan_hf primero cuando responde |
| wan_hf (nube) | 0 | intermitente (hoy sí, 88 s) | motor #1 de escenas |
| Gemini TTS | 0 con tope diario | ~10–15 voces/día; a veces repite la frase | voces, con candado de duración |
| pollinations / minimax | pago / sin saldo | 402 / saldo 0 | apagados; se leen de la hoja MOTORES |
| OpenAI (llave existe) | pago | no autorizado | apagado salvo que él lo prenda en la hoja |
| GAS + Sheets + Pages + Drive | 0 | estables (gas.py única puerta) | columna vertebral |
| decisiones del editor | — | EL cuello: una rama espera a otra | se rompe con ramas paralelas |

## Arquitectura propuesta
1. **Hoja COLA** (una fila por trabajo): pieza · etapa · lámina/escena · motor · estado ·
   prioridad · evidencia (hash, duración, motor, hora) · quién lo pidió · bloqueado_por.
2. **Hoja MOTORES**: orden de cascada por etapa, encendido/apagado, tope diario, costo (0/pago).
3. **Hoja REGLAS**: los umbrales que hoy viven en código (piso de letra, MARGEN de audio,
   tope de duración de voz por palabra, cabecera, máx. renglones, N prospectos por rechazo).
4. **Productor** (`sala_productor.py`, launchd cada 20 min, con log obligatorio): lee COLA,
   abre las compuertas POR LÁMINA y POR PIEZA (no por «todo o nada»), corre lo que tenga
   motor gratis disponible, escribe evidencia en COLA y BITÁCORA, y monta en la Sala lo que
   ya está listo. Nunca dos productores a la vez (candado con md5, no `hash()`).
5. **Prospectos**: cada «no» genera 2–3 candidatas (eje), no una sola rehecha; cada opción
   del eje de casos elegida abre su propia rama (guion → láminas) sin esperar a las demás.
6. **Simulacro** (`sala_simulacro.py`, día aislado < 2026-06): retirar, reabrir, dos
   editores en conflicto, borrar explícito, cuota agotada, GAS 404/405, Drive caído,
   imagen idéntica, relevo virtual, contador tras «Ir», móvil 375, eje decidido dos veces.

## Reparto
- Fable: este plan, revisión de diseño de compuertas y del contrato de la hoja COLA.
- Opus: `sala_productor.py` (concurrencia, candados, compuertas por rama) y cambios al GAS.
- Sonnet: hojas, `sala_simulacro.py`, migrar constantes a REGLAS, docs, pruebas en Chrome.
