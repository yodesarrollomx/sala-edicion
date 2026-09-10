# El Apodo · corte v7 — lo que falta y cómo se cierra
9-sep-2026, tarde. Escrito aquí y no en mi cabeza: Alejandro, 9-sep — «creo que sí tienes
todo en tu lógica interna».

## Estado
| paso | estado |
|---|---|
| Las 6 láminas | **aprobadas por Alejandro** (`apodo-g7-c7faea`, seis «sí») |
| Guion del video con roles de voz | hecho · `datos/guiones/APODO-VIDEO.json` |
| Recortes sin cabecera ni banda de texto | hecho · `apodo/recortes_v7.py` |
| Las 6 escenas animadas | **corriendo** con `ltx_local` (~17 min c/u) |
| Voces | **2 de 6.** Cuota diaria de Gemini TTS agotada (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`). Se repone mañana. |
| Corte junto | **no** — y no se junta hasta tener las 6 voces |

## Cómo se cierra (mañana, en este orden)
```
python3 ~/yod_audit/apodo/voces_v7.py      # las 4 que faltan; es idempotente
python3 ~/yod_audit/apodo/montar_v7.py     # pasa por la compuerta; deja CORTE_ y REEL_APODO_v7.mp4
python3 ~/yod_audit/sala_publicar.py --pub <carpeta> --titulo "…" --slug apodo-v7 \
        --video ".../REEL_APODO_v7.mp4" --origen "del guion · las 6 láminas aprobadas" --tira <tira>
```

## Por qué no se reusó NADA del v6
Los clips del v6 no correspondían a sus láminas: el del cierre mostraba un skyline en vez de
la pareja con el plano, dos eran de otra pieza, y tres traían el texto viejo quemado. Reusarlos
habría metido doble texto y escenas que no son las que él aprobó.

## Por qué no se reusaron las voces del v6
Porque el v6 alternaba dos narradores sin razón — que es exactamente lo que él marcó. En el v7
el narrador es UNO en toda la pieza y el vecino sólo dice lo entrecomillado. Rellenar con las
viejas sería volver al error que se está corrigiendo.

## Lo que quedó anotado y no se ha resuelto
- Los `concept/AP*_src.png` están DESALINEADOS con las láminas montadas: `AP2e_src` y `AP3_src`
  son el mismo archivo (md5 idéntico) y `AP6_src` no es la lámina del cierre. El nombre del src
  se deriva del basename del `out`, así que dos láminas distintas pueden pisarse. Por eso los
  recortes salen ahora de la lámina montada, no del src. **La causa sigue en pie.**
- Motores de video de nube: pollinations pide pago (402), minimax sin saldo, gemini 429.
  Sólo queda el local. Si urge velocidad, hay que resolver eso.
