# Activar historial de Sala en el Apps Script original

Estado: paquete preparado; **no desplegado**. No acredita producción ni autonomía integral.
Código fuente: commit `ee3e9a5b54b08fa59ed6d2d7df17c8550b102d68`.
El archivo [HistoricoSala.gs](HistoricoSala.gs) contiene exactamente las seis funciones ya probadas del espejo público; no contiene claves ni IDs privados.

## Prompt para el operador con Chrome conectado

```text
Completa únicamente la activación del historial de Sala en el proyecto Apps Script ORIGINAL vinculado al Sheet «Sala de Edición · YOD». Alejandro ya autorizó este trabajo.

1. Identifica el proyecto por el Sheet original y por el despliegue /exec que usa GAS_DEF en el index.html de yodesarrollomx/sala-edicion. No uses otro proyecto parecido.
2. Respalda privadamente el código actual y anota el deployment ID y versión vigente. Conserva las claves, IDs, CONFIG, URL y dueño.
3. Abre el paquete de esta carpeta HistoricoSala.gs. Compara las seis funciones con las del proyecto: fechaProduccionValida_, selloProduccion_, fusionProduccion_, produccionHistorica_, leerProduccionHistorica_, respuestaProduccionHistorica_. Si existen, reemplaza únicamente sus cuerpos por las versiones del paquete; si faltan, añádelas. Evita definiciones duplicadas. No pegues el Code.gs público completo.
4. En doGet(e), después de resolver rolQuien y rechazar una clave inválida, añade esta ruta si falta:
   if (p.recurso === 'produccion') return respuestaProduccionHistorica_(rolQuien);
   El recurso sólo permite al rol agente leer; no habilita decidir.
5. Añade la función de ComprobarHistorico.gs y ejecútala. Debe devolver ok=true, contrato produccion-historica-v1, version produccion-historica-2026-10-15, alcance historial_completo y conteos consistentes. No copies notas, nombres ni respuestas completas a chats o repositorios públicos.
6. Guarda, recarga el editor y verifica que permanecen los cambios. En Implementar → Gestionar implementaciones → editar la implementación web EXISTENTE → Nueva versión → Implementar. Conserva la misma URL /exec. No crees otra implementación.
7. Entrega únicamente: proyecto confirmado, funciones actualizadas, resultado agregado de la comprobación, versión desplegada y confirmación de que la URL no cambió. No compartas claves.
8. Detente antes de habilitar SALA_PRODUCCION_HISTORICA=1: GPT comprobará primero el contrato por el /exec real y luego podrá habilitarlo. El éxito de ejecutar una función en el editor NO demuestra que la versión web se haya actualizado.
9. Si hay un fallo, conserva su mensaje redactado y revierte sólo las funciones/versión exactas respaldadas; no borres ni restaures filas editoriales. No apruebes láminas ni elimines vetos.
```

## Verificación posterior

La sonda autenticada usa `validar_historica(sala.get("produccion", fresco="1"))`, sin aceptar el fallback del día. El último diagnóstico real fue `sala_recurso_no_disponible`.
Tras confirmar la respuesta web y contrastar fuentes, habilitar el flag; ejecutar Mesa, Productor, Ejecutor y Revisión. La aceptación exige cuatro producciones completas consecutivas con recibos y capturas. Los recorridos de sólo lectura y las ejecuciones sin trabajo no cuentan.

Persisten por separado los vetos editoriales, cuatro láminas pendientes sin revisión activa y la sustitución del mantenimiento de suscripción. Este despliegue no los declara resueltos.
