# Activación del histórico · 17-oct-2026

El comprobador de sólo lectura del proyecto original detectó duplicados heredados de PROPUESTAS con el mismo PID y fecha. Elegir la última fila física no acredita la versión vigente.

La lectura agrupa la última fecha de cada PID. Un retiro explícito en estado u origen excluye el grupo completo. Si siguen activas, todas las filas deben coincidir salvo origen descriptivo; sus textos únicos se conservan ordenados y separados por ` | `. Las diferencias de contenido, opciones, vídeo o estado siguen cerrando la lectura. No se modifican filas, fechas, marcas, notas o firmas.

Propuesta central: CHG-SALA-HISTORICO-RETIROS-20261017, modelo `2026-10-17.sala-historico-retiros.1`, commit `bc333f3072c647d57ff871d68e408372aa247c84` de yod-portal.

El proyecto original tiene respaldo privado. La comprobación del candidato a las 08:21 Hermosillo terminó correctamente: 288 filas de propuestas, 30 fuentes activas, 191 retiradas y 10654 filas de decisiones. Esto acredita la lectura desde el editor, todavía no el despliegue.

Orden de activación: pruebas y revisión del cambio; guardar y releer el módulo exacto; actualizar la implementación existente conservando URL y permisos; ejecutar `sala-historico.yml` con las credenciales existentes y el validador del consumidor. Sólo tras ese éxito se habilita `SALA_PRODUCCION_HISTORICA=1`. El diagnóstico no escribe ni imprime contenido privado. Después se ejecuta producción con sus compuertas editoriales y de motores existentes.

Reversión: desactivar el consumidor histórico y seleccionar versión72 en la misma implementación; restaurar el módulo respaldado si procede. Conservar decisiones, cola, medios y configuración. Cuatro recorridos vacíos no equivalen a cuatro producciones completas.
