# Lectura canónica de producción

La mesa del día sirve tarjetas y hereda marcas de los últimos catorce días. Esa ventana
no demuestra que una fuente antigua haya desaparecido o sido retirada. La producción
necesita consultar el historial completo y conservar el último estado firmado real.

## Contrato de lectura

El recurso `GET produccion` usa la clave de agente existente y las mismas pestañas
PROPUESTAS/DECISIONES. Una vez validada esa credencial, el handler no escribe filas,
decisiones, bitácora, reglas o correo, ni modifica ACL o scopes. La autenticación heredada
conserva su comportamiento, incluido su registro de rechazos. Los demás roles siguen sin
acceso a este recurso. Su contrato es
`produccion-historica-v1`, versión `produccion-historica-2026-10-15`, con alcance
`historial_completo`.

La respuesta contiene `ok`, `contrato`, `version`, `alcance`, `fecha`, `dias`, `propuestas`,
`decisiones` y `fuentes`. Cada propuesta conserva el formato existente y añade
`fecha_fuente` y `estado`. `fuentes` cuenta filas leídas, fuentes activas, retiradas y
decisiones leídas. No incluye un reloj generado por cada lectura: una lectura idéntica
debe producir datos idénticos para las comprobaciones de estabilidad.

PROPUESTAS se resuelve por ID exacto y la última fecha hasta hoy. Una última fila retirada
no revive una versión anterior activa. Dos filas contradictorias con el mismo ID en la
última fecha cierran la lectura; sin un sello adicional no se atribuye recencia al orden
físico. Una fuente posterior única sustituye un conflicto antiguo.

DECISIONES se resuelve sobre todo el historial por editor, ID y lámina, usando el sello
`guardado` real de cada fila. Ni la fecha de la tarjeta ni el sello de otra fila que reuse
un `envio_id` promueven una marca antigua. `pendiente` no borra; `borrar` revoca sólo la
marca de ese editor; un `no` vigente del otro mantiene el veto. Un empate contradictorio
en el sello máximo, incluso una nota de toma distinta, cierra la lectura. Un conflicto
antiguo ya sustituido por un sello posterior no bloquea la decisión vigente.

Cada decisión lleva `laminas`, `nota`, `notas`, `firmas` y `firmas_nota`. Las firmas de
lámina conservan rol, nombre, marca (`si`, `no` o `null` por borrado), nota y sello UTC.
`firmas_nota` acredita las notas generales de la propuesta. El cliente compara tanto
marcas como notas fusionadas con sus firmas, para no seleccionar una toma distinta de
la firmada. Dos selecciones de toma distintas en la nota efectiva bloquean el resolver;
no se elige la primera por orden de firmas. Las firmas no sustituyen la validación del
guion, snapshot, huellas o medios.

## Despliegue en dos pasos

`SALA_PRODUCCION_HISTORICA=0` es el valor predeterminado. Mantiene la lectura legada con
`alcance=legacy_ventana_limitada` y `cuenta_historial=no_confirmada`. Las fuentes que esa
lectura no puede encontrar se cuentan como `fuentes_sin_acreditar`; no se llaman retiradas
ni se afirma que el historial tenga cero pendientes.

Primero se debe instalar el helper y el bloque GET en el Apps Script original mediante
su propietario, conservar el deployment existente y comprobar por lectura su contrato,
versión y semántica. Editar este espejo no despliega el backend. Sólo después se puede
habilitar `SALA_PRODUCCION_HISTORICA=1` en los lectores autorizados. Sus allowlists GET, incluida la auditoría de fallos,
ya admiten `produccion`. Las variables de repositorio se conectan con valor
predeterminado `0`; ninguna activación forma parte de este cambio.

La instalación acotada crea un módulo `ProduccionHistorica20261015.gs` con estas seis
funciones: `fechaProduccionValida_`, `selloProduccion_`, `fusionProduccion_`,
`produccionHistorica_`, `leerProduccionHistorica_` y `respuestaProduccionHistorica_`.
En el `doGet` existente, después de validar `rolQuien`, se añade sólo esta ruta:

```javascript
if (p.recurso === 'produccion') return respuestaProduccionHistorica_(rolQuien);
```

El módulo reutiliza `fechaDe`, `selloDe`, `nombreDe`, `hoja`, `filas`, `PESTANAS`, `hoy`
y `json` existentes. No se renombra ningún handler ni se reemplaza el archivo completo.
Guardar el HEAD no cambia la versión que sirve el deployment existente. Sin identidad propietaria habilitada para actualizar esa versión, el cliente debe continuar con bandera `0`.

Con la bandera encendida, `cargar()` prefiere el contrato nuevo. Sólo reconoce fallback
si el backend declara recurso no disponible o si el GAS antiguo ignora el recurso y
devuelve un día de versión legada conocida. Error de red, acceso, JSON o contrato
incompatible detienen la lectura. Un fallback reconocido sigue declarando su límite.

## Límites y comprobación

Se validan fechas, sellos, roles, IDs de hasta 256 caracteres sin separadores de rutas,
fuentes únicas, marcas y notas firmadas. Los límites son 10.000 filas de PROPUESTAS,
50.000 de DECISIONES, 1.000 láminas por tarjeta y 4 MiB sobre el JSON reserializado UTF-8 en Python. No hay
nuevos reintentos ni aumento de presupuesto de red.

Las pruebas usan filas sintéticas, dobles de Sheet y transportes prohibidos. Incluyen
historia anterior a catorce días, veto posterior, borrado, sobres reutilizados, empates,
retiros, cabeceras ausentes, contrato falsificado y compatibilidad del JSON GAS con Python.
La auditoría real debe repetirse después del despliegue y de la activación: recuperar
una fuente antigua no prueba que un corte fallido pueda producirse.

Para revertir el lector se vuelve a la bandera `0`. Revertir el commit retira el recurso
del espejo; el backend requiere su propio despliegue. No se borran ni revierten decisiones,
estados, archivos o evidencias de negocio.
