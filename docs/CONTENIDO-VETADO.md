# Ubicaciones vetadas en contenido nuevo

La chinche #49 prohíbe **Hermosillo, Sonora y México** durante la producción. La regla compara palabras completas sin distinguir mayúsculas o acentos; incluye `MEXICO` y `México`.

`nube/contenido_reglas.py` aplica el mismo veto a ideas, premisas, promesas, guiones, textos y explicaciones de candidatas, descripciones y recetas. La estrategia común lo comunica a todos los motores de texto. Una respuesta que incumple se rechaza y se prueba la siguiente vía; nunca se elimina una palabra de un texto para fingir que ya quedó corregido.

Hay compuertas antes de pedir una imagen, componer una lámina, sintetizar cualquier parte de voz y montar una tira. El cliente de nube rechaza lotes inválidos de `proponer`, `ideas` y `arbol` antes de la red. La recepción GAS rechaza esos lotes completos antes de sus operaciones de escritura. **El archivo GAS versionado no acredita despliegue:** comparar el proyecto activo, conservar sus operaciones actuales y publicar la revisión en el mismo deployment. El espejo no contiene todos los handlers de la fuente activa; no reemplazarla completa a partir del repo.

La regla `contenido_ubicaciones_vetadas` usa el contrato existente de REGLAS (nombre, valor, descripción); su valor es una lista separada por comas. Puede añadir términos. Un valor vacío o una configuración distinta conserva los tres vetos obligatorios. El valor de fábrica se siembra mediante la operación existente `hojas`; una instalación actual puede usar la operación `regla` para agregarlo sin modificar otras reglas.

No se modifican decisiones ni contenido histórico. Las notas editoriales, versiones anteriores, IDs, rutas, URLs y la zona horaria conservan su significado. Una tira actual que contiene palabras vetadas espera a ser rehecha; no se vuelve válida por estar aprobada o por traer una imagen ya producida.

Verificación sin red: `python3 nube/verificar.py`, que incluye los casos sintéticos Python y Node de esta regla. Revertir mediante PR; no borrar ni restaurar registros operativos.
