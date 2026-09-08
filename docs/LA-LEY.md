# La ley de la Sala — qué hago y qué dejo de hacer

*8-sep-2026. Escrito a petición de Alejandro: «revisa mis quejas por aquí y por las revisiones
de sala y llega a un conjunto de cosas que tienes que realizar y dejar de hacer, y oriéntate
para que tu código y sistema esté ordenado a esto antes de seguir adelante».*

No es un resumen de buenas intenciones. Cada línea sale de una queja fechada, y al lado dice
**qué pedazo de código la hace cumplir**. Lo que no tiene código al lado, todavía no es ley.

---

## 1. La queja que se repitió cinco veces

| Fecha | Sus palabras |
|---|---|
| 4-ago | «Me vuelve a aparecer lo que ya decidí — no corrió mis selecciones pasadas» |
| 27-ago | «Lo ya decidido vuelve a la mesa al día siguiente» |
| 29-ago | «ME SIGUES MOSTRANDO COSAS QUE YA REVISÉ» |
| 1-sep | «Puros fallos repetidos: me mandas a revisión los mismos y lo corregido no llega» |
| 8-sep | «Me pones cosas que ya habíamos modificado» |

Las cinco se cerraron como «cumplida». Las cinco volvieron. Eso quiere decir que **las cinco
veces se arregló el síntoma**: la lógica de la Sala, la fusión del GAS, el relevo, el md5 dentro
de una carpeta. Ninguna tocó la causa.

**La causa:** una lámina no tenía identidad. Para el Sheet era una fila, para la Sala una ruta,
para el publicador un md5. Nadie sabía que `apodo-g1/L4.png` y `apodo-g3/L4.png` eran **la misma
lámina en dos momentos**. Sin identidad no hay historia, y sin historia todo parece nuevo.

La prueba, medida el 8-sep sobre las carpetas reales:

| Grupo montado | Láminas que se le mandaron | Nuevas de verdad |
|---|---|---|
| apodo-g2 | 9 | 5 |
| **apodo-g3** | **9** | **2** |
| apodo-g4 | 9 | 3 |

**49 láminas · 115 revisiones reales · 27 copias que se hacían pasar por versión nueva.**

**Ley:** cada lámina nace con un serial que no cambia nunca (`APODO-L04`) y una revisión que
sube **sólo cuando el contenido cambia de verdad** (`r1`…`r5`).
→ `sala_catalogo.py`, `datos/catalogo.json`, pestaña `CATALOGO` del Sheet.

---

## 2. La queja que él tuvo que escribir tres veces

Palabra por palabra, en tres revisiones distintas:

> «creo que se vería mejor si le damos entonación de pregunta, puede ser que así se sienta más
> leído por el cliente»

Y la tercera vez ya venía con reclamo: *«…ya también este lo hemos cambiado, revisa bien»*.

**Causa:** una nota vivía en la fila del día en que la escribió. Al día siguiente esa fila ya no
se leía, y la instrucción se evaporaba.

**Ley:** una nota se pega al **serial**, no al día. Mientras esa lámina viva, la nota sigue
puesta, y toda revisión nueva tiene que decir cómo la atendió.
→ columna `nota_que_lo_pidio` del `CATALOGO`; la tira muestra `nota_previa`.

**Dejo de hacer:** pedirle que repita una instrucción. Si no la atendí, se dice «no la atendí»,
no se vuelve a preguntar.

---

## 3. Lo que le hacía lento el portal

Su queja: *«en verdad me estás descargando, subiendo y bajando cosas pesadas y por eso se
vuelve muy lento»*. Medido el 8-sep:

- De 142 láminas, **73 no tenían versión ligera**: su teléfono bajaba el PNG de obra (1.3 MB)
  en vez de los 120 KB. **153 MB contra 17 MB.**
- El Sheet **nunca** guardó imágenes — sólo rutas. La lentitud de *guardar* era el Apps Script.

**Ley:** al teléfono jamás le viaja un original. La Sala carga **sólo letras** (~28 KB) y pide
la foto a Drive apenas cuando se le pica.
→ `ligera()` en `index.html`; `recurso=catalogo` devuelve texto; `drive_api.liga()`.

---

## 4. Dónde vive cada cosa (y quién manda)

| Cosa | Dónde | Quién manda |
|---|---|---|
| El proceso (marcas, notas, estados) | Sheet | **el Sheet** |
| El registro de láminas y revisiones | Sheet, pestaña `CATALOGO` | se **deriva** de las huellas, no se edita a mano |
| Las imágenes, todas sus revisiones | Drive, `YOD Editorial/` | **Drive es el archivo** |
| El portal | GitHub Pages, un archivo | el repo |

En Drive, una carpeta por lámina y un archivo por revisión:

```
YOD Editorial/
  APODO · El Apodo del Terreno/
    APODO-L04/
      APODO-L04-r1-original.png    ← maestro limpio: esto se publica
      APODO-L04-r1-prueba.jpg      ← ligera y SELLADA con el serial: esto se revisa
      APODO-L04-r5-original.png
      APODO-L04-r5-prueba.jpg
```

**Dos copias a propósito**, como en cualquier taller editorial: el original nunca lleva sello;
la prueba lleva el serial impreso en la esquina para que de un vistazo se sepa si es la r1 o la
r5. **Una prueba nunca se publica.**

---

## 5. Lo que dejo de hacer

1. **Dejo de copiar carpetas.** Duplicar una lámina a una carpeta nueva no la vuelve versión
   nueva. Si la huella no cambió, es la misma `r`.
2. **Dejo de mandarle a decidir una lámina que ya vio.** De contexto en la tira sí; como carta
   nunca. → `regla_no_repetir_lo_visto`.
3. **Dejo de cerrar peticiones como «cumplida» sin evidencia que se pueda volver a correr.**
   28 peticiones marcadas cumplidas y cinco de ellas revivieron. Una petición se cierra con el
   nombre del archivo y la comprobación que lo demuestra.
4. **Dejo de arreglar el síntoma.** Si una queja ya apareció antes con otra cara, el arreglo va
   a la causa o no va.
5. **Dejo de mandarle originales al teléfono.**
6. **Dejo de inventar el estado.** Si el Sheet no contesta, se dice; no se sirve una copia.

## 6. Lo que hago siempre

1. **Serial primero.** Ninguna lámina entra al sistema sin serial y sin revisión calculada por
   huella.
2. **Registro antes que archivo.** Primero la fila del `CATALOGO`, luego la subida a Drive; así
   nunca hay un archivo que nadie sabe qué es.
3. **La nota persigue al serial**, no al día.
4. **La guardia bloquea.** Si una regla se puede comprobar, es código que detiene el montaje;
   si hay que juzgarla, vive escrita y se lee. → `sala_guardia.py`.
5. **Nada se reporta hecho sin abrir la pantalla.** → auditor de pantallas.
6. **Cero cifras de dinero, nada de «gratis», sin plazos, áreas en m².**

---

## 7. Cómo comprobar que esto es cierto

```bash
python3 ~/yod_audit/sala_catalogo.py     # los seriales y sus revisiones reales
python3 ~/yod_audit/sala_verificar.py    # las 15 comprobaciones del portal vivo
python3 ~/yod_audit/sala_guardia.py --help
```
