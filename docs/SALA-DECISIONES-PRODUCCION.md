# Decisiones guardadas y producción

La mesa visual devuelve las tarjetas por contestar. Una tarjeta ya respondida de un día anterior puede desaparecer de esa lista sin que el productor haya recibido la aprobación o el rechazo.

`nube/sala_produccion.py` recupera la propuesta activa por su fecha original y aplica la decisión fusionada actual. Sólo se usan lecturas frescas del backend existente; una fuente retirada no se reconstruye desde archivos locales. Se informa cuántas fuentes se recuperaron y cuántas no siguen vigentes.

La toma elegida fija imagen, texto y huella del trabajo. Mesa conserva esas aprobaciones, aplica las notas actuales y genera las láminas restantes del guion como candidatas. Cada versión nueva tiene su propia carpeta. Un lote parcial mantiene visibles las candidatas aún sin responder del lote anterior. Las nuevas candidatas no heredan el rechazo de la imagen sustituida.

El Productor abre una rama aprobada aunque las demás sigan pendientes. El corte exige todas las láminas del guion producidas y aprobadas. Los carruseles permanecen como imágenes. Peticiones abiertas, editores y reglas conservan sus compuertas.

`Sala · decisiones guardadas a producción` encadena Mesa, Productor, Ejecutor y Revisión. Si hubo avance y trabajo limitado, solicita como máximo dos pasadas adicionales en runs independientes. Se dispara al publicar una corrección de este recorrido y conserva botón manual. Los horarios existentes continúan. Encolar, guardar un archivo durable y publicar una revisión se acreditan por separado; una prueba de motores aislados no acredita decisiones transferidas.

Verificaciones: `python3 nube/verificar.py` y regresiones sintéticas `tests/sala_produccion_test.py`, además de las suites existentes. La operación real sólo comienza con código integrado y decisiones ya existentes; no se inventan marcas, proyectos o correos para probar.

## Bloqueos observados y corregidos

La API rechazó los modelos Gemini2.5 configurados. Se consultó su catálogo y se verificaron por respuesta sintética el alias ligero vigente y un respaldo estable. La configuración de producción se actualizó y releió; los defaults ya no proponen modelos retirados. Pensamiento y texto final del modelo se separan.

Mesa prioriza las decisiones más recientes, incluyendo la continuación de sus versiones. El estado agregado `datos/mesa-estado.json` informa generación, fallos y límite pendiente. Un fallo total sale con error; un resultado parcial se declara parcial. El workflow conserva ese fallo aunque no exista un issue de aviso.

Dos llamadas a Mesa dentro del mismo run comparten su ID de publicación. Las pasadas adicionales ahora usan runs reales distintos, con contador acotado, y se solicitan sólo tras avance verificado de la pasada anterior. La revisión reconoce este recorrido y registra sus jobs reales.

## Montaje con snapshot privado

El montaje de Mesa y Arranque recibe GH_TOKEN del propio workflow para comprobar la versión publicada y los hashes del snapshot privado. Un comando que falla mantiene su código a través de tee. Error de lectura no se presenta como imagen inexistente ni como montaje exitoso.

Una versión generada pero todavía sin montar no sustituye la fuente activa del Sheet. Mesa selecciona esa fuente y puede reutilizar su generación existente si conserva las mismas referencias aprobadas. Si cambió una referencia, crea otra versión. No vuelve a gastar en las mismas imágenes ni modifica originales. El informe de Mesa se transporta como output por ruta exacta datos/mesa-estado.json; la continuación exige su run de origen y avance generado o reutilizado.
