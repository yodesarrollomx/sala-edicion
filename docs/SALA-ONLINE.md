# Sala existente ejecutada en la nube

Cambio CHG-SALA-ONLINE-20261011, aprobado en el atlas 93afbea366c19872bfb855463afece2ac73eeb08.

Sheets conserva catálogo, reglas, cola y decisiones. GitHub Actions ejecuta los procesos con las claves existentes. No hace falta una sesión de Claude o ChatGPT ni una Mac encendida. El código se integra por PR y CI.

## Medios

Gemini/Cloudflare/HF conservan su orden configurado. Si fallan y imagen_respaldo_cpu no es 0, segmind/tiny-sd produce una imagen real en CPU. Modelo OpenRAIL-M, revisión cad0bd7, pesos con carga restringida weights_only; sin código remoto. Su calidad se revisa en la misma mesa editorial. Modal es opcional y queda desactivado por omisión; escena_modal=1 lo solicita explícitamente. No se acreditó su GPU por falta de método de pago.

Wan sigue cuando está disponible; parallax y cámara conservan la lámina completa. La evidencia identifica profundidad real o aproximada y si la escena es generativa. Kokoro y ffmpeg corren en CPU. Se exige persistencia de archivos en Drive antes de HECHO.

Prueba real 38137779743: imagen, lámina, voz y corte de 10.17 segundos, H264/AAC 1080x1920, seis archivos privados recuperados por SHA256, profundidad Depth Anything V2. Cero filas de negocio y cero decisiones.

## Publicación de datos

bootstrap recupera el último snapshot confirmado. Antes de generar, el productor adquiere un mutex en runtime/online-data-lease, mediante commits mínimos de metadatos y fast-forward. Contiene sólo run_id, proceso, estado y caducidad; nunca contenido ni credenciales. Los escritores esperan sin cancelar procesos diferentes. No se roba un mutex activo; el mismo token se verifica antes de publicar y confirmar.

El productor sólo puede cambiar las rutas de su contrato. Se genera un ZIP acumulativo de outputs públicos y se conserva como release en BORRADOR privado; nunca se publica el release. ZIP, archivos y manifiesto se verifican por hash, tamaño, tipo, paths y extracción segura. La rama main sigue protegida y los PR anteriores del bot no se integran omitiendo sus checks.

Pages construye desde archivos del código aprobado y outputs públicos allowlisted. Los logs y temporales privados del runner quedan fuera. version-online.json acredita code_sha, data_sha, snapshot_id y run_id exactos. Un HTTP 200 sin ese recibo no confirma publicación. Sólo después se monta la mesa, comprobando también el hash de cada lámina y tira. Proponer sigue sin aprobar por el editor.

Un error conserva el snapshot y las decisiones. Las fuentes de Apps Script originales no están localizadas; el espejo gas/Code.gs no se publica como supuesto código vivo.

## Rutinas

Los cron existentes mantienen sus frecuencias y Hermosillo (UTC-7):
productor cada 20 minutos; ejecutor y semáforo cada dos horas; mesa, arranque y chinches cada hora; relevo 06, 09, 12, 15 y 18. Las corridas encadenadas son adicionales. GitHub puede retrasar sus horarios.

Revisión diaria 07:05: cola agregada, etapas habilitadas y última ejecución observada por rutina. Ajustes → Revisión diaria. Lecturas rechazadas conservan el último valor y su fecha; si no hay un valor confirmado muestran desconocido. No se publican filas, nombres, notas, correos ni credenciales. El inventario del disparador de correo de Apps Script permanece pendiente; no se inventa su número o frecuencia.

## Operación y rollback

Los botones workflow_dispatch conservan simulación y ejecución real. Los procesos sólo ejecutan código de main. Los secretos permanecen en sus repositorios; no se exportan tokens del conector ni se añade una identidad de bot externa.

Verificar: nube/verificar.py, tests *_test.py, pruebas UI de carga/fotos, contratos de ZIP, mutex, versión y montaje, CI de arquitectura fija.

Rollback por PR: revertir infraestructura y restaurar último snapshot confirmado. Mantener cola, medios, notas e histórico. La ruta anterior de publicación Git requiere resolver su identidad y CI antes de reactivarla. No volver a encender planes cancelados de otros agentes o servidores.
