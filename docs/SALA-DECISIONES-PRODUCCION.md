# Decisiones guardadas y producción

La mesa visual devuelve las tarjetas por contestar. Una tarjeta ya respondida de un día anterior puede desaparecer de esa lista sin que el productor haya recibido la aprobación o el rechazo.

`nube/sala_produccion.py` recupera la propuesta activa por su fecha original y aplica la decisión fusionada actual. Sólo se usan lecturas frescas del backend existente; una fuente retirada no se reconstruye desde archivos locales. Se informa cuántas fuentes se recuperaron y cuántas no siguen vigentes.

La toma elegida fija imagen, texto y huella del trabajo. Mesa conserva esas aprobaciones, aplica las notas actuales y genera las láminas restantes del guion como candidatas. Cada versión nueva tiene su propia carpeta. Un lote parcial mantiene visibles las candidatas aún sin responder del lote anterior. Las nuevas candidatas no heredan el rechazo de la imagen sustituida.

El Productor abre una rama aprobada aunque las demás sigan pendientes. El corte exige todas las láminas del guion producidas y aprobadas. Los carruseles permanecen como imágenes. Peticiones abiertas, editores y reglas conservan sus compuertas.

`Sala · decisiones guardadas a producción` encadena dos pasadas de Mesa respetando el límite por corrida, Productor, Ejecutor y Revisión. Se dispara al publicar una corrección de este recorrido y conserva botón manual. Los horarios existentes continúan. Encolar, guardar un archivo durable y publicar una revisión se acreditan por separado; una prueba de motores aislados no acredita decisiones transferidas.

Verificaciones: `python3 nube/verificar.py` y regresiones sintéticas `tests/sala_produccion_test.py`, además de las suites existentes. La operación real sólo comienza con código integrado y decisiones ya existentes; no se inventan marcas, proyectos o correos para probar.
