/**
 * Sala de Edición · YOD — el conector con el Sheet.  (v3, espec de la mesa 1-ago-2026)
 *
 * Qué hace: recibe la revisión diaria del editor en UN envío consolidado e idempotente,
 * la guarda sin pisar nada, sirve el día al portal, registra las decisiones de parrilla
 * (andón), y manda el correo de las 7:00 con la liga que trae la sesión resuelta.
 *
 * CÓMO SE INSTALA (una sola vez, ~3 minutos):
 *   1. Google Sheet nuevo → "Sala de Edición · YOD".
 *   2. Extensiones → Apps Script → pegar ESTE archivo completo.
 *   3. Correr  instalar  (▶) y autorizar. Crea pestañas, 4 claves por rol y el correo 7:00.
 *   4. Implementar → Aplicación web (Ejecutar como TÚ · Acceso: cualquier persona) → copiar /exec.
 *   5. La liga del correo diario ya lleva la sesión; para la primera vez, en el portal:
 *      «conexión: … toca para conectar» y pegar /exec + la clave de CONFIG (fila clave).
 *
 * ROLES (patrón de la casa: clave suave por rol, en CONFIG):
 *   clave          → editor  (Alejandro: lee y decide)
 *   clave_editor2  → editor2 (Sayri: lee y decide; queda su autoría en 'quien')
 *   clave_lector   → lector  (clientes/socios: solo lectura)
 *   clave_agente   → agente  (la Mac: propone, reporta producción, acusa cosecha)
 */

var TZ = 'America/Hermosillo';
var PORTAL = 'https://yodesarrollomx.github.io/sala-edicion/';  // al migrar: yodesarrollo.github.io/sala-edicion
var CORREO = 'direccion@aurumarquitectos.com';

var PESTANAS = {
  CONFIG:     ['clave', 'valor'],
  PROPUESTAS: ['fecha', 'prop_id', 'titulo', 'tipo', 'laminas_json', 'opciones_json', 'video', 'estado', 'origen'],
  DECISIONES: ['envio_id', 'quien', 'guardado', 'fecha', 'prop_id', 'lamina', 'marca', 'nota_propuesta', 'nota_dia', 'nota_estrategia'],
  PARRILLA:   ['fecha', 'pieza', 'gate', 'desde', 'decision_editor', 'decidido'],
  CONTROL:    ['pieza', 'desde', 'formula', 'alcance', 'clics', 'leads', 'nota'],
  PRODUCCION: ['fecha', 'pieza', 'estado', 'detalle', 'enlace'],
  BITACORA:   ['fecha_hora', 'evento', 'detalle'],
  EXPEDIENTES:['pieza', 'actualizado', 'json'],  // la historia con sus palabras: privada, tras la clave
  // 8-sep: EL CATÁLOGO. Cada lámina tiene un serial que no cambia nunca y una revisión que sube
  // sólo cuando el contenido cambia de verdad. Aquí vive el registro; las imágenes viven en Drive.
  // Con esto la Sala carga SÓLO letras y pide la foto a Drive apenas cuando se le pica.
  CATALOGO:   ['serial', 'pieza', 'lamina', 'revision', 'de', 'estado', 'fecha',
               'drive_prueba', 'drive_original', 'ruta', 'rutas', 'nota_que_lo_pidio', 'huella'],
  // 12-sep, plan «de raíz» (PLAN-RAIZ.md). Alejandro: «todo configurable en Sheets, nada
  // hardcodeado». Tres pestañas nuevas y ningún número más escondido en el código:
  //   REGLAS  → los umbrales (piso de letra, margen de audio, tope de voz, cada cuánto corre…)
  //   MOTORES → qué motor se usa en cada etapa, en qué orden, prendido o apagado, tope diario
  //   COLA    → una fila por trabajo: el productor la lee, la marca y deja su evidencia ahí
  REGLAS:     ['nombre', 'valor', 'descripcion'],
  MOTORES:    ['etapa', 'motor', 'encendido', 'tope_dia', 'costo', 'orden', 'nota'],
  COLA:       ['id', 'pieza', 'etapa', 'item', 'motor', 'estado', 'prioridad',
               'bloqueado_por', 'evidencia', 'pidio', 'creado', 'actualizado'],
  // 12-sep (tarde): PROMPTS. Hasta hoy, cuando el editor decía «no» a una lámina, las
  // candidatas se escribían A MANO (las recetas /tmp/spec_AP*.json del run anterior). Un «no»
  // no puede depender de que yo esté despierto: aquí vive la receta base de cada lámina, y el
  // productor la combina con la nota del rechazo para generar solo las candidatas.
  PROMPTS:    ['pieza', 'lamina', 'prompt_base', 'acento', 'notas']
};

/* Valores de fábrica de REGLAS y MOTORES (12-sep). Se siembran UNA vez con accion:'hojas';
   después mandan los del Sheet, aunque alguien los cambie a mano — que es justo la idea.
   Nunca se pisan ni se borran: sembrar es «agrega lo que falte», jamás «deja como estaba». */
var REGLAS_DEFAULT = [
  ['tipografia_piso', 66, 'tamaño mínimo de letra en las láminas (px)'],
  ['tipografia_techo', 78, 'tamaño máximo de letra en las láminas (px)'],
  ['tipografia_max_renglones', 3, 'renglones máximos de un bloque de texto'],
  ['cabecera_px', 122, 'alto de la cabecera de la lámina (px)'],
  ['audio_margen_s', 6, 'margen de audio al inicio/fin del corte (s)'],
  ['audio_cola_s', 2.2, 'cola de audio tras la última palabra (s)'],
  ['audio_xfade_s', 0.28, 'cruce entre pistas de audio (s)'],
  ['fondo_volumen', 0.14, 'volumen de la cama sonora (0-1)'],
  ['voz_tope_seg_por_palabra', 0.62, 'segundos por palabra: arriba de esto la voz se repitió'],
  ['voz_tope_base', 1.3, 'base del candado de duración de voz (s)'],
  ['voz_tope_factor', 1.7, 'factor del candado de duración de voz'],
  ['prospectos_por_rechazo', 2, 'cuántas candidatas nacen de cada «no» del editor'],
  ['productor_cada_min', 20, 'cada cuántos minutos despierta el productor (launchd)'],
  ['productor_silencio_desde', 23, 'hora en que el productor se calla (24 h)'],
  ['productor_silencio_hasta', 7, 'hora en que el productor vuelve a trabajar (24 h)'],
  // Estas dos no venían en la lista original, pero un interruptor que Alejandro no puede VER
  // en el Sheet no es configurable: es un default escondido con otro nombre. Van aquí.
  ['productor_ejecuta_etapas', '', 'qué etapas corre de verdad el productor (escena,voz,corte,prospectos); vacío = sólo encola'],
  ['productor_piezas', 'apodo', 'qué piezas vigila el productor, separadas por coma'],
  // 12-sep (tarde), reclamo textual de Alejandro: «estuve editando la misma publicación en
  // varias etapas… no quiero cosas a medias… que no me dejes duplicados». El Apodo se le
  // preguntó SEIS veces (g5, g5e, g7, g8, apodo-g9-l3/l5, apodo-g10-l3) porque cada rehecha
  // montaba una carta NUEVA sin retirar la anterior. Con esto en 1, una familia de pieza
  // tiene como máximo UNA carta viva en la mesa: proponer otra retira las ya decididas y,
  // si hay una sin decidir, la nueva ni siquiera se monta (se encola bloqueada).
  ['una_carta_por_pieza', 1, 'máximo UNA carta viva por familia de pieza en la mesa (1=sí)']
];
var MOTORES_DEFAULT = [
  // etapa, motor, encendido, tope_dia, costo, orden, nota
  ['imagen', 'mflux',        1, 0, 0,       1, 'local en la Mac, gratis, ~6.5 min por lámina'],
  ['escena', 'wan_hf',       1, 0, 0,       1, 'nube gratis, intermitente; se intenta primero'],
  ['escena', 'ltx_local',    1, 0, 0,       2, 'local, ~17 min por escena; respaldo de wan_hf'],
  ['escena', 'pollinations', 0, 0, 'pago',  3, 'apagado: 402, sin saldo'],
  ['escena', 'minimax',      0, 0, 'pago',  4, 'apagado: saldo 0'],
  ['escena', 'gemini',       0, 0, 'cuota', 5, 'apagado: se reserva la cuota para las voces'],
  ['voz',    'gemini_tts',   1, 12, 0,      1, 'gratis con tope diario; a veces repite la frase']
];

function instalar() {
  var ss = SpreadsheetApp.getActive();
  Object.keys(PESTANAS).forEach(function (n) {
    var h = ss.getSheetByName(n) || ss.insertSheet(n);
    if (h.getLastRow() === 0) { h.appendRow(PESTANAS[n]); h.setFrozenRows(1); }
  });
  // 4 claves por rol; si ya existe la del editor se conserva (migración sin dolor)
  var cfg = ss.getSheetByName('CONFIG');
  // claves sembradas desde la Mac al conectar (este script es privado de la cuenta;
  // la copia publica del repo NO las lleva). Cambiarlas aqui y en ~/.sala_gas si un dia rotan.
  var SEMILLA = {'clave':'', 'clave_editor2':'', 'clave_lector':'', 'clave_agente':''};  // vacías a propósito en la copia pública: las claves reales viven en el proyecto privado
  Object.keys(SEMILLA).forEach(function (k) {
    if (!leerConfig(k)) cfg.appendRow([k, SEMILLA[k]]);
  });
  // sin estas filas, quien entra por Google nunca puede ser editor2 (Sayri): el canje
  // compara el correo contra CONFIG y, vacío, la degrada a lectora.
  ['correo_editor', 'correo_editor2', 'nombre_editor', 'nombre_editor2'].forEach(function (k) {
    if (!leerConfig(k)) cfg.appendRow([k, k === 'correo_editor'  ? CORREO :
                                          k === 'correo_editor2' ? 'proyectos@aurumarquitectos.com' :
                                          k === 'nombre_editor'  ? 'Alejandro' : 'Sayri']);
  });
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'correoDiario') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('correoDiario').timeBased().everyDays(1).atHour(7).inTimezone(TZ).create();
  bitacora('Sala instalada; roles creados; correo diario 7:00 programado');
}

/* ------------------------------------------------ utilería */
function hoja(n) { return SpreadsheetApp.getActive().getSheetByName(n); }
function hoy() { return Utilities.formatDate(new Date(), TZ, 'yyyy-MM-dd'); }
function ahora() { return Utilities.formatDate(new Date(), TZ, "yyyy-MM-dd'T'HH:mm:ss"); }
function leerConfig(k) {
  var v = hoja('CONFIG'); if (!v || v.getLastRow() < 1) return '';
  var datos = v.getDataRange().getValues();
  // i=1: la fila 0 es el encabezado 'clave|valor' (leerConfig('clave') devolvia 'valor')
  for (var i = 1; i < datos.length; i++) if (String(datos[i][0]) === k) return String(datos[i][1]);
  return '';
}
function escribirConfig_(k, v) {
  var h = hoja('CONFIG'), d = h.getDataRange().getValues(), fila = -1;
  for (var i = 1; i < d.length; i++) if (String(d[i][0]) === k) { fila = i + 1; break; }
  if (fila > 0) h.getRange(fila, 2).setValue(v); else h.appendRow([k, v]);
}
function rolDe(clave) {
  if (!clave) return null;
  if (clave === leerConfig('clave')) return 'editor';
  if (clave === leerConfig('clave_editor2')) return 'editor2';
  if (clave === leerConfig('clave_lector')) return 'lector';
  if (clave === leerConfig('clave_agente')) return 'agente';
  var g = rolPorGracia_(clave); if (g) return g;   // 8-sep: la llave recién rotada sigue valiendo unas horas
  return rolPorPortero_(clave);          // UNA SOLA LLAVE: la sesión del YOD OS también entra
}

/* ROTACIÓN SIN DEJAR A NADIE FUERA (8-sep-2026). El 7-sep por la noche el agente rotó las 4 claves
   y solo actualizó los archivos de la Mac: el navegador de Alejandro se quedó con la clave vieja y
   por la mañana la Sala le dijo «no reconocí tu entrada». Desde hoy, al rotar se guarda la clave
   anterior con su fecha y se acepta durante GRACIA_HORAS; quien entra con ella ES el dueño legítimo,
   así que la respuesta le manda la clave nueva para que su navegador se renueve solo y en silencio. */
var GRACIA_HORAS = 72;
function rolPorGracia_(clave) {
  var pares = [['clave', 'editor'], ['clave_editor2', 'editor2'], ['clave_lector', 'lector'], ['clave_agente', 'agente']];
  for (var i = 0; i < pares.length; i++) {
    var vieja = leerConfig(pares[i][0] + '_anterior');
    if (!vieja || vieja !== clave) continue;
    var desde = leerConfig(pares[i][0] + '_rotada_en');
    if (!desde) continue;
    var horas = (new Date().getTime() - new Date(desde).getTime()) / 3600000;
    if (horas >= 0 && horas <= GRACIA_HORAS) return pares[i][1];
  }
  return null;
}
function claveNuevaPara_(clave) {         // solo a quien ya demostró ser el dueño con la clave anterior
  var pares = ['clave', 'clave_editor2', 'clave_lector', 'clave_agente'];
  for (var i = 0; i < pares.length; i++) {
    if (leerConfig(pares[i] + '_anterior') === clave) {
      var desde = leerConfig(pares[i] + '_rotada_en');
      if (!desde) return null;
      var horas = (new Date().getTime() - new Date(desde).getTime()) / 3600000;
      if (horas >= 0 && horas <= GRACIA_HORAS) return leerConfig(pares[i]);
    }
  }
  return null;
}

/* UNA SOLA LLAVE (3-sep-2026, pedido de Alejandro: «la misma clave del portero me debe dar
   acceso a todo, incluida la Sala»). Patrón de la casa (ver board-aurum/apps-script/
   portero-auth.gs): el backend le pregunta al Portero por la credencial —liga mágica de 90
   días, clave de equipo o Google— y decide él mismo la autorización. Se canjea SIN &board=
   para no depender del filtro del Portero. Caché por hash: 10 min si vale, 1 min si no.
   Portero caído = nadie entra por esta vía (fail-closed), pero las claves suaves siguen. */
var PORTERO_EXEC = 'https://script.google.com/macros/s/AKfycbwlDDCWWzOWYZsUpBU9uqsQ7aenQ469PF6s6FkNlBFS1_cJSU5njG9oQmuyELy5zlqzFg/exec';
var PORTERO_RESPALDO = 'https://script.google.com/macros/s/AKfycbyrhqMb70Qh8BljAOYnSYBZ8IXUuEclFWPg10NWIv3GJ-nAR597OTsGB4IL-xyUl7Ms/exec';
var CODIGO_SALA  = 'MK';               // la Sala vive en el Embudo, junto a Métricas/Marketing
function rolPorPortero_(k) {
  k = String(k || '').trim();
  if (k.length < 8) return null;
  var cache = CacheService.getScriptCache();
  var ck = 'sala_auth_' + Utilities.base64EncodeWebSafe(
    Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, k)).slice(0, 24);
  var hit = cache.get(ck);
  if (hit) return hit === 'no' ? null : hit;
  var rol = null, nombre = '', porque = '';
  /* 4-sep-2026: el permiso de HTTP (UrlFetchApp) quedó autorizado desde el editor. El camino
     principal es preguntarle al Portero, como hacen los demás tableros; leer su hoja queda de
     respaldo por si el Portero no contesta. */
  function decidirRol_(correo, nom) {
    correo = String(correo || '').toLowerCase().trim(); nombre = String(nom || '');
    if (correo && correo === String(leerConfig('correo_editor') || CORREO).toLowerCase()) return 'editor';
    if (correo && correo === String(leerConfig('correo_editor2') || '').toLowerCase()) return 'editor2';
    return 'lector';
  }
  try {
    var j = null, ultimo = '';
    var porteros = [PORTERO_EXEC, PORTERO_RESPALDO];
    for (var i = 0; i < porteros.length && !(j && j.ok); i++) {
      try {
        var r = UrlFetchApp.fetch(porteros[i] + '?recurso=canje&t=' + encodeURIComponent(k), { muteHttpExceptions: true, followRedirects: true });
        ultimo = String(r.getResponseCode()) + ' ' + r.getContentText().slice(0, 120);
        j = JSON.parse(r.getContentText());
      } catch (e1) { ultimo = 'excepción: ' + e1; }
    }
    if (j && j.ok) {
      var role = String(j.rol || '').toLowerCase(), boards = String(j.boards || '');
      var puede = role === 'admin' || boards.trim() === '*' ||
        boards.split(',').map(function (x) { return x.trim().toUpperCase(); }).indexOf(CODIGO_SALA) >= 0;
      if (puede) rol = decidirRol_(j.correo, j.nombre);
      else porque = 'sin el tablero ' + CODIGO_SALA + ' en sus accesos (' + boards + ')';
    } else porque = 'Portero: ' + ultimo;
  } catch (err) { porque = 'Portero HTTP: ' + err; }
  if (!rol && !/sin el tablero/.test(porque)) {
    try {                                           // respaldo: leer la hoja del Portero
      var v = validarEnHojaDelPortero_(k);
      if (v.ok) { rol = decidirRol_(v.correo, v.nombre); porque = ''; }
      else porque += ' · hoja: ' + (v.porque || 'sin acceso');
    } catch (err2) { porque += ' · hoja: ' + String(err2).slice(0, 100); }
  }
  if (rol && nombre) cache.put(ck + '_n', nombre, 300);
  if (!rol) { try { bitacora('Portero no autorizó una credencial', porque.replace(/[A-Za-z0-9_-]{24,}/g, '…')); } catch (e2) {} }
  cache.put(ck, rol || 'no', rol ? 300 : 60);
  return rol;
}
/* Lee SESIONES y ACCESOS del Sheet del Portero («YOD - POTENCIALES», hoja de accesos). */
var PORTERO_SHEET_ID = '1Ld2ytzwYniIXmxu_TuLViN4hPILSg-xMbFpFgPnqf7Y';
function filasDe_(ss, nombre) {
  var h = ss.getSheetByName(nombre); if (!h) return null;
  var v = h.getDataRange().getValues(); if (v.length < 2) return [];
  var hdr = v[0].map(function (x) { return String(x).trim(); });
  return v.slice(1).map(function (r) { var o = {}; hdr.forEach(function (c, i) { o[c] = r[i]; }); return o; });
}
function validarEnHojaDelPortero_(k) {
  if (k.indexOf('sy') !== 0 || k.length < 20) return { ok: false, porque: 'no es un token de sesión del Portero' };
  var ss = SpreadsheetApp.openById(PORTERO_SHEET_ID);
  var ses = filasDe_(ss, 'SESIONES'); if (!ses) return { ok: false, porque: 'la hoja SESIONES no existe en ' + PORTERO_SHEET_ID };
  var s = null;
  for (var i = ses.length - 1; i >= 0; i--) if (String(ses[i].token || '').trim() === k) { s = ses[i]; break; }
  if (!s) return { ok: false, porque: 'sesión no encontrada' };
  if (String(s.revocada || '').toLowerCase() === 'si') return { ok: false, porque: 'sesión revocada' };
  var exp = selloDe(s.expira); if (exp && exp < Date.now()) return { ok: false, porque: 'sesión vencida' };
  var correo = String(s.correo || '').toLowerCase().trim();
  if (correo === String(CORREO).toLowerCase()) return { ok: true, correo: correo, nombre: 'Alejandro', rol: 'admin' };
  var acc = (filasDe_(ss, 'ACCESOS') || []).filter(function (a) { return String(a.correo || '').toLowerCase().trim() === correo; })[0];
  if (!acc) return { ok: false, porque: 'correo sin fila en ACCESOS: ' + correo };
  if (String(acc.estado || '').toLowerCase() !== 'activo') return { ok: false, porque: 'acceso no activo: ' + acc.estado };
  var role = String(acc.rol || '').toLowerCase(), boards = String(acc.boards || '');
  var puede = role === 'admin' || boards.trim() === '*' ||
    boards.split(',').map(function (x) { return x.trim().toUpperCase(); }).indexOf(CODIGO_SALA) >= 0;
  if (!puede) return { ok: false, porque: 'sin el tablero ' + CODIGO_SALA + ' en sus accesos (' + boards + ')' };
  return { ok: true, correo: correo, nombre: String(acc.nombre || ''), rol: role };
}
function nombrePortero_(k) {
  try {
    var ck = 'sala_auth_' + Utilities.base64EncodeWebSafe(
      Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, String(k || ''))).slice(0, 24);
    return CacheService.getScriptCache().get(ck + '_n') || '';
  } catch (e) { return '' }
}
function filas(n) {
  var h = hoja(n); if (!h || h.getLastRow() < 2) return [];
  var cab = PESTANAS[n];
  return h.getRange(2, 1, h.getLastRow() - 1, cab.length).getValues().map(function (r) {
    var o = {}; cab.forEach(function (c, i) { o[c] = r[i]; }); return o;
  });
}
function bitacora(evento, detalle) { hoja('BITACORA').appendRow([ahora(), evento, detalle || '']); }
/* Lee una regla de la hoja REGLAS desde el propio GAS. La usa la puerta de `proponer` para
   respetar `una_carta_por_pieza` sin depender de que el productor se acuerde: la regla vive
   en el Sheet, así que quien la aplica también tiene que leerla del Sheet. */
function reglaGas_(nombre, porDefecto) {
  var h = hoja('REGLAS'); if (!h || h.getLastRow() < 2) return porDefecto;
  var v = h.getRange(2, 1, h.getLastRow() - 1, 2).getValues();
  for (var i = 0; i < v.length; i++) if (String(v[i][0]).trim() === nombre) {
    var x = v[i][1]; return (x === '' || x === null) ? porDefecto : x;
  }
  return porDefecto;
}
function json(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
var _FECHAS = {}; var _RECALENTAR = null;
function fechaDe(v) {
  // a prueba de zonas: medianoche de CUALQUIER zona +12 h cae en la fecha correcta en UTC
  // 7-sep: memoizada por valor. Un día frío tardaba 48 s porque formatDate corría por fila, por día y por pasada.
  if (v instanceof Date) { var t = v.getTime(); if (_FECHAS[t] === undefined) _FECHAS[t] = Utilities.formatDate(new Date(t + 43200000), 'Etc/UTC', 'yyyy-MM-dd'); return _FECHAS[t]; }
  return String(v).slice(0, 10);
}

/* El envio vigente de un dia = el del sello 'guardado' mas alto QUE PUSO EL GAS al
   recibir (nunca el reloj del telefono — objecion firmada del ingeniero). */
function selloDe(v) {            // los sellos se guardan como Date: comparar como texto ordenaba por dia de la semana
  if (v instanceof Date) return v.getTime();
  var t = Date.parse(String(v)); return isNaN(t) ? 0 : t;
}
function envioVigente(decRows, f) {   // compatibilidad: el ultimo envio del dia, de quien sea
  var mejor = 0, id = '';
  decRows.forEach(function (d) {
    if (fechaDe(d.fecha) !== f) return;
    var t = selloDe(d.guardado);
    if (t >= mejor) { mejor = t; id = String(d.envio_id); }
  });
  return id;
}
/* DOS EDITORES, UNA MESA (3-sep-2026, pedido de Alejandro):
   Alejandro y Sayri son editores por igual. Antes solo contaba el ultimo envio del dia,
   asi que quien guardaba despues borraba la revision del otro. Ahora se toma el ULTIMO
   envio DE CADA EDITOR y se fusionan: si alguno pide cambio, la lamina se rehace, y las
   notas de ambos viajan firmadas para que Produccion cumpla las dos. */
function vigentePorEditor(decRows, f) {
  var mejor = {}, id = {};
  decRows.forEach(function (d) {
    if (fechaDe(d.fecha) !== f) return;
    var q = String(d.quien || 'editor'); var t = selloDe(d.guardado);
    if (!(q in mejor) || t >= mejor[q]) { mejor[q] = t; id[q] = String(d.envio_id); }
  });
  return id;                                   // { editor: envio_id, editor2: envio_id }
}
function nombreDe(rol) {
  var n = leerConfig(rol === 'editor2' ? 'nombre_editor2' : 'nombre_editor');
  return n || (rol === 'editor2' ? 'Sayri' : 'Alejandro');
}


/* Un dia fusionado: el ultimo envio DE CADA EDITOR de ese dia (el "no" manda, notas firmadas). */
function fusionDia_(DE, f) {
  // decisiones: el ultimo envio DE CADA EDITOR, fusionados (ver vigentePorEditor)
  // 7-sep: ya NO manda «el último sobre» completo. Cada editor decide en varios sobres al día
  // (uno por carta, desde el teléfono o la laptop); si el último no traía una pieza, esa pieza
  // perdía sus marcas y la mesa la volvía a preguntar (Alejandro: «¿por qué me hablas de lo mismo?»).
  // Ahora, por editor y por PIEZA, manda el sobre más reciente que la mencione.
  var vigE = vigentePorEditor(DE, f);
  var selloEnvio = {}, rolEnvio = {};
  DE.forEach(function (d) {
    if (fechaDe(d.fecha) !== f) return;
    var eid = String(d.envio_id), t = selloDe(d.guardado);
    if (!(eid in selloEnvio) || t > selloEnvio[eid]) selloEnvio[eid] = t;
    rolEnvio[eid] = String(d.quien || 'editor');
  });
  // 7-sep (noche): granularidad LÁMINA. Por editor, pieza y lámina manda la fila más reciente con marca
  // real (si/no/borrar). Una fila «pendiente» NUNCA borra una marca anterior (un cliente que abrió una copia
  // sin marcas mandaba «pendiente» y se perdían decisiones). «borrar» es el deshacer explícito.
  var mejorFila = {};   // rol|pid|lamina -> fila ganadora
  DE.forEach(function (d) {
    if (fechaDe(d.fecha) !== f) return;
    var eid = String(d.envio_id), rol0 = rolEnvio[eid], pid0 = String(d.prop_id || '');
    var esLam = (d.lamina !== '' && d.lamina !== null), m0 = String(d.marca || '');
    if (esLam && m0 !== 'si' && m0 !== 'no' && m0 !== 'borrar') return;       // pendiente: no cuenta
    var k = rol0 + '|' + pid0 + '|' + (esLam ? String(d.lamina) : 'nota');
    if (!esLam && !String(d.nota_propuesta || '') && !String(d.nota_dia || '')) return;   // fila de nota vacía: no cuenta
    if (!(k in mejorFila) || selloEnvio[eid] >= selloEnvio[String(mejorFila[k].envio_id)]) mejorFila[k] = d;
  });
  var vivos = {}; Object.keys(vigE).forEach(function (q) { vivos[vigE[q]] = q; });
  var dec = { propuestas: {}, editores: [] }, ult = 0;
  Object.keys(mejorFila).map(function (k) { return mejorFila[k]; }).forEach(function (d) {
    var eid = String(d.envio_id);
    var rol = rolEnvio[eid], quien = nombreDe(rol);
    if (String(d.marca || '') === 'borrar') { d = Object.assign({}, d); d.marca = ''; }
    if (dec.editores.indexOf(quien) < 0) dec.editores.push(quien);
    var pid = String(d.prop_id);
    if (pid) {
      var fi = dec.propuestas[pid] = dec.propuestas[pid] || { laminas: [], nota: '', notas: [], firmas: [] };
      if (d.lamina !== '' && d.lamina !== null) {
        var i2 = Number(d.lamina), m = String(d.marca || '');
        m = (m === 'si' || m === 'no') ? m : null;
        var nota = d.nota_propuesta ? String(d.nota_propuesta) : '';
        // el NO manda: si a uno no le gusto, se rehace cumpliendo las notas de los dos
        var prev = fi.laminas[i2] || null;
        fi.laminas[i2] = (prev === 'no' || m === 'no') ? 'no' : (m || prev);
        fi.firmas[i2] = (fi.firmas[i2] || []).concat([{ quien: quien, marca: m, nota: nota }]);
      } else if (d.nota_propuesta) {
        var t = String(d.nota_propuesta);
        fi.nota = fi.nota ? (fi.nota + ' | ' + quien + ': ' + t) : t;
      }
      // 8-sep: una fila de nota VACÍA no borra una nota anterior. Alejandro escribió «quiero que lo revise
      // Hormozi, escena por escena» a las 08:19 y los envíos siguientes (con la nota ya limpia en el
      // cliente) la machacaron. Igual que con las marcas: el vacío nunca pisa lo escrito.
    }
    if (d.nota_dia) dec.nota_general = (dec.nota_general ? dec.nota_general + ' | ' : '') + quien + ': ' + String(d.nota_dia);
    if (d.nota_estrategia) dec.nota_estrategia = String(d.nota_estrategia);
    var ts = selloDe(d.guardado); if (ts > ult) ult = ts;
  });
  // notas: una sola voz se deja tal cual; dos o mas van firmadas para que Produccion
  // cumpla las dos. Una lamina que un editor dejo pendiente y el otro marco, cuenta marcada.
  Object.keys(dec.propuestas).forEach(function (pid) {
    var fi = dec.propuestas[pid];
    for (var i = 0; i < fi.laminas.length; i++) {
      if (fi.laminas[i] === undefined) fi.laminas[i] = null;
      var con = (fi.firmas[i] || []).filter(function (x) { return x.nota; });
      if (con.length === 1) fi.notas[i] = con[0].nota;
      else if (con.length > 1) fi.notas[i] = con.map(function (x) { return x.quien + ': ' + x.nota; }).join(' | ');
    }
  });
  return { dec: dec, ult: ult };
}
/* Herencia (5-sep): una propuesta que sigue en la mesa pero se decidio (parcialmente) otro dia trae esas
   marcas en la misma respuesta. Antes la Sala las pedia aparte (4 dias, 6 s de tope) y con el GAS tardando
   5-11 s los ✓ se perdian y volvia a preguntar lo ya aprobado. */
function heredarMarcas_(DE, props, dec, f) {
  var faltan = props.map(function (p) { return p.id; }).filter(function (id) { return !dec.propuestas[id]; });
  for (var k = 1; k <= 14 && faltan.length; k++) {
    var fk = Utilities.formatDate(new Date(new Date(f + 'T12:00:00').getTime() - k * 864e5), TZ, 'yyyy-MM-dd');
    var hay = DE.some(function (d) { return fechaDe(d.fecha) === fk && faltan.indexOf(String(d.prop_id)) >= 0; });
    if (!hay) continue;
    var fz = fusionDia_(DE, fk).dec;
    faltan = faltan.filter(function (id) {
      if (!fz.propuestas[id]) return true;
      var m = fz.propuestas[id]; m.heredada = fk; dec.propuestas[id] = m; return false;
    });
  }
}
/* Misma regla que el relevo de la Mac: un eje se cierra con UN si (o todas no); una tira, con marca en todas. */
function cerrada_(p, m) {
  var marcas = (m && m.laminas) || [];
  if (p.tipo === 'eje') {
    // 12-sep (tarde): aquí estaba la raíz del invariante 59 («el eje del 28-ago se volvía a
    // preguntar»). Un eje moderno guarda sus opciones como OBJETO —{candidatas:[…]}— y
    // `.length` de un objeto es undefined: `n` salía 0, `cerrada_` contestaba false SIEMPRE y
    // ningún eje decidido se retiraba solo de la mesa. Se retiraban a mano, o no se retiraban.
    var op = p.opciones || [];
    var n = (op.length !== undefined) ? op.length : ((op.candidatas || []).length);
    if (!n) return false;
    var s = marcas.slice(0, n);
    return s.some(function (x) { return x === 'si'; }) || s.filter(function (x) { return x === 'no'; }).length >= n;
  }
  var n2 = (p.laminas || []).length; if (!n2) return false;
  return marcas.slice(0, n2).filter(function (x) { return x === 'si' || x === 'no'; }).length >= n2;
}

/* ------------------------------------------------ lectura */
function doGet(e) {
  var p = (e && e.parameter) || {};
  // (Antes aquí corría resembrar() en cada lectura: escribía en CONFIG en cada request y
  //  volvía imposible rotar las claves. Ahora sólo se corre a mano desde el editor.)
  var rolQuien = rolDe(p.clave);
  if (!rolQuien) return json({ error: 'clave incorrecta' });
  if (p.recurso === 'bitacora') {                 // las últimas líneas, para diagnosticar desde la Mac
    if (rolDe(p.clave) !== 'agente') return json({ error: 'solo el agente' });
    var ult = filas('BITACORA').slice(-40).map(function (b) { var t = selloDe(b.fecha_hora);
      return { cuando: t ? Utilities.formatDate(new Date(t), TZ, 'yyyy-MM-dd HH:mm') : String(b.fecha_hora),
               evento: String(b.evento), detalle: String(b.detalle || '').slice(0, 300) }; });
    return json({ ok: true, bitacora: ult });
  }
  if (p.recurso === 'envios') {                   // TODAS las filas de DECISIONES de un dia (auditoria desde la Mac):
    if (rolDe(p.clave) !== 'agente') return json({ error: 'solo el agente' });   // recupera marcas que un envio posterior tapo
    if (p.f && !/^\d{4}-\d{2}-\d{2}$/.test(p.f)) return json({ error: 'fecha inválida (yyyy-mm-dd)' });
    var fE = p.f || hoy();
    var fil = filas('DECISIONES').filter(function (d) { return fechaDe(d.fecha) === fE; }).map(function (d) {
      var t = selloDe(d.guardado);
      return { envio: String(d.envio_id), quien: String(d.quien),
               guardado: t ? Utilities.formatDate(new Date(t), TZ, 'yyyy-MM-dd HH:mm:ss') : String(d.guardado),
               prop: String(d.prop_id || ''), lamina: (d.lamina === '' || d.lamina === null) ? null : Number(d.lamina),
               marca: String(d.marca || ''), nota: String(d.nota_propuesta || ''), nota_dia: String(d.nota_dia || ''), nota_estrategia: String(d.nota_estrategia || '') };
    });
    return json({ ok: true, fecha: fE, filas: fil });
  }
  if (p.recurso === 'reprogramar_correo') {       // el correo "de las 7:00" salia a las 00:30 (5-sep): se recrea el disparador en la zona de la casa
    if (rolDe(p.clave) !== 'agente') return json({ error: 'solo el agente' });
    var borrados = 0;
    ScriptApp.getProjectTriggers().forEach(function (t) {
      if (t.getHandlerFunction() === 'correoDiario') { ScriptApp.deleteTrigger(t); borrados++; }
    });
    ScriptApp.newTrigger('correoDiario').timeBased().everyDays(1).atHour(7).inTimezone(TZ).create();
    bitacora('Correo diario reprogramado', 'entre 7:00 y 8:00 ' + TZ + ' (' + borrados + ' disparador(es) anteriores borrados)');
    return json({ ok: true, borrados: borrados, zona: TZ });
  }
  if (p.recurso === 'zona_hoja') {                // la hoja parseaba ahora() (hora Hermosillo) como UTC: bitacora y guardado salian 7 h atras
    if (rolDe(p.clave) !== 'agente') return json({ error: 'solo el agente' });
    var ss0 = SpreadsheetApp.getActive(), antes = ss0.getSpreadsheetTimeZone();
    if (p.fijar === '1' && antes !== TZ) {
      ss0.setSpreadsheetTimeZone(TZ);
      bitacora('Zona horaria de la hoja fijada', antes + ' → ' + TZ + ' (los sellos anteriores se leen 7 h antes; los nuevos van bien)');
    }
    return json({ ok: true, antes: antes, ahora: ss0.getSpreadsheetTimeZone(), script: Session.getScriptTimeZone() });
  }
  if (p.recurso === 'calentador') {                // (agente) instala el disparador que mantiene el cache tibio cada 10 min
    if (rolDe(p.clave) !== 'agente') return json({ error: 'solo el agente' });
    var b = 0; ScriptApp.getProjectTriggers().forEach(function (t) { if (t.getHandlerFunction() === 'calentarCache') { ScriptApp.deleteTrigger(t); b++; } });
    ScriptApp.newTrigger('calentarCache').timeBased().everyMinutes(10).create();
    calentarCache();
    bitacora('Calentador de cache instalado', 'cada 10 min · ' + b + ' anterior(es) borrado(s)');
    return json({ ok: true, borrados: b });
  }
  if (p.recurso === 'catalogo') {                 // 8-sep: el registro de láminas, SOLO LETRAS.
    // Lo puede leer cualquier rol con clave: no trae imágenes, trae seriales y ligas de Drive.
    var ck = 'catalogo:v1';
    var enCache = CacheService.getScriptCache().get(ck);
    if (enCache && !p.fresco) return ContentService.createTextOutput(enCache).setMimeType(ContentService.MimeType.JSON);
    var act = {};
    filas('CATALOGO').forEach(function (r) {
      if (!r.serial) return;
      var a = act[r.serial] = act[r.serial] || { serial: String(r.serial), pieza: String(r.pieza),
        lamina: Number(r.lamina), estado: String(r.estado || ''), revisiones: [] };
      a.estado = String(r.estado || a.estado);
      a.revisiones.push({ r: Number(r.revision), de: Number(r.de), fecha: String(r.fecha || ''),
        prueba: String(r.drive_prueba || ''), original: String(r.drive_original || ''),
        ruta: String(r.ruta || ''),   // la ruta vieja del repo: así la Sala reconoce la lámina que ya pinta
        rutas: String(r.rutas || r.ruta || ''),   // TODAS las carpetas donde vive esa misma revisión, con |
        pidio: String(r.nota_que_lo_pidio || ''), huella: String(r.huella || '') });
    });
    var sal = JSON.stringify({ ok: true, catalogo: act, cuantas: Object.keys(act).length });
    CacheService.getScriptCache().put(ck, sal, 900);
    return ContentService.createTextOutput(sal).setMimeType(ContentService.MimeType.JSON);
  }

  if (p.recurso === 'expedientes') {
    if (!rolDe(p.clave)) return json({ error: 'clave incorrecta' });
    var ex = {};
    filas('EXPEDIENTES').forEach(function (r) {
      if (!r.pieza) return;
      try { ex[String(r.pieza)] = JSON.parse(String(r.json || '{}')); } catch (e) {}
    });
    return json({ ok: true, expedientes: ex });
  }
  if (p.recurso === 'reglas') {                   // 12-sep: los umbrales y la cascada de motores
    // Los lee el agente (sala_reglas.py) y también el editor, para que Ajustes pueda mostrarlos
    // sin una segunda puerta. No hay nada secreto aquí: son números de producción.
    if (['agente', 'editor', 'editor2'].indexOf(rolQuien) < 0) return json({ error: 'solo el agente o un editor' });
    var reg = {};
    filas('REGLAS').forEach(function (r) {
      var n = String(r.nombre || '').trim(); if (!n) return;
      reg[n] = r.valor;                            // tal cual: sala_reglas.py convierte según el default
    });
    var mot = filas('MOTORES').filter(function (m) { return String(m.etapa || '').trim(); })
      .map(function (m) {
        return { etapa: String(m.etapa).trim(), motor: String(m.motor || '').trim(),
                 encendido: String(m.encendido === '' || m.encendido === null ? 1 : m.encendido),
                 tope_dia: Number(m.tope_dia || 0), costo: String(m.costo === '' || m.costo === null ? 0 : m.costo),
                 orden: Number(m.orden || 99), nota: String(m.nota || '') };
      });
    return json({ ok: true, reglas: reg, motores: mot,
                  hojas: { REGLAS: !!hoja('REGLAS'), MOTORES: !!hoja('MOTORES'), COLA: !!hoja('COLA') } });
  }
  if (p.recurso === 'prompts') {                  // 12-sep: las recetas base de las láminas
    if (['agente', 'editor', 'editor2'].indexOf(rolQuien) < 0) return json({ error: 'solo el agente o un editor' });
    var pr = filas('PROMPTS').filter(function (x) { return String(x.pieza || '').trim(); })
      .map(function (x) {
        return { pieza: String(x.pieza).trim(), lamina: String(x.lamina === null || x.lamina === undefined ? '' : x.lamina).trim(),
                 prompt_base: String(x.prompt_base || ''), acento: String(x.acento || ''), notas: String(x.notas || '') };
      });
    if (p.pieza) pr = pr.filter(function (x) { return x.pieza === String(p.pieza); });
    return json({ ok: true, prompts: pr, cuantos: pr.length });
  }
  if (p.recurso === 'cola') {                     // 12-sep: los trabajos del productor
    if (['agente', 'editor', 'editor2'].indexOf(rolQuien) < 0) return json({ error: 'solo el agente o un editor' });
    var col = filas('COLA').filter(function (t) { return String(t.id || '').trim(); }).map(function (t) {
      return { id: String(t.id), pieza: String(t.pieza || ''), etapa: String(t.etapa || ''),
               item: String(t.item === null || t.item === undefined ? '' : t.item),
               motor: String(t.motor || ''), estado: String(t.estado || ''),
               prioridad: Number(t.prioridad || 5), bloqueado_por: String(t.bloqueado_por || ''),
               evidencia: String(t.evidencia || ''), pidio: String(t.pidio || ''),
               creado: String(t.creado || ''), actualizado: String(t.actualizado || '') };
    });
    // filtros opcionales, para no bajar la cola entera cuando sólo interesa una pieza
    ['pieza', 'etapa', 'estado'].forEach(function (k) {
      if (!p[k]) return;
      col = col.filter(function (t) { return String(t[k]) === String(p[k]); });
    });
    return json({ ok: true, cola: col, cuantos: col.length });
  }
  if (p.recurso !== 'dia') return json({ error: 'recurso desconocido' });
  var f = /^\d{4}-\d{2}-\d{2}$/.test(p.f || '') ? p.f : hoy();
  var cuerpo = diaCacheado_(f, p.fresco === '1');
  cuerpo.rol = rolQuien;
  var nueva = claveNuevaPara_(p.clave);        // 8-sep: si entró con la llave anterior (en gracia), se le manda la nueva
  if (nueva) { cuerpo.clave_nueva = nueva; cuerpo.aviso_llave = 'Tu llave se renovó; la Sala la guardó sola.'; }
  cuerpo.quien = (rolQuien === 'editor' || rolQuien === 'editor2') ? nombreDe(rolQuien) : (nombrePortero_(p.clave) || '');
  cuerpo.version = 'dos-compuertas-2026-09-12';
  return json(cuerpo);
}

/* CACHE (5-sep): cada lectura leia 6 pestanas y tardaba 7-12 s. El dia se arma una vez, se guarda 5 min
   en CacheService y CUALQUIER escritura (doPost) lo invalida, asi que nunca se sirve algo viejo tras
   una decision. Lo que depende de quien pregunta (rol, quien) se agrega fuera del cache. */
function diaCacheado_(f, fresco) {
  var cache = CacheService.getScriptCache(), ck = 'dia:v2:' + f;
  if (!fresco) { try { var raw = cache.get(ck); if (raw) { var o = JSON.parse(raw); o.cache = true; return o; } } catch (e) {} }
  var cuerpo = armarDia_(f);
  try { var txt = JSON.stringify(cuerpo); if (txt.length < 95000) cache.put(ck, txt, 900); } catch (e2) {}
  cuerpo.cache = false; return cuerpo;
}
function programarCalentado_() {
  try {
    var ya = ScriptApp.getProjectTriggers().filter(function (t) { return t.getHandlerFunction() === 'calentarUnaVez_'; });
    if (ya.length >= 3) return;                          // nunca inundar de disparadores
    ScriptApp.newTrigger('calentarUnaVez_').timeBased().after(1000).create();
  } catch (e) {}
}
function calentarUnaVez_(ev) {
  try { calentarCache(); } finally {
    try { ScriptApp.getProjectTriggers().forEach(function (t) { if (t.getHandlerFunction() === 'calentarUnaVez_') ScriptApp.deleteTrigger(t); }); } catch (e) {}
  }
}
function calentarCache() {
  var f = hoy(), c = armarDia_(f);
  try { var txt = JSON.stringify(c); if (txt.length < 95000) CacheService.getScriptCache().put('dia:v2:' + f, txt, 900); } catch (e) {}
}
function invalidarDia_(f) {
  var ks = ['dia:v2:' + hoy()]; if (f && /^\d{4}-\d{2}-\d{2}$/.test(String(f)) && ks.indexOf('dia:v2:' + f) < 0) ks.push('dia:v2:' + f);
  try { CacheService.getScriptCache().removeAll(ks); } catch (e) {}
}
function armarDia_(f) {
  // una lectura por pestaña (presupuesto <3 s firmado por el ingeniero)
  var PR = filas('PROPUESTAS'), DE = filas('DECISIONES'), PA = filas('PARRILLA'),
      CO = filas('CONTROL'), PD = filas('PRODUCCION'), BI = filas('BITACORA');

  // 9-sep: aquí faltaba el filtro de RETIRADAS. `accion=retirar` marcaba estado='retirada'
  // en la fila, pero armarDia_ sólo descartaba las retiradas de días PREVIOS (más abajo, en
  // `extra`); las de hoy se servían igual. Consecuencia: montar una versión rehecha el mismo
  // día dejaba la vieja Y la nueva en la mesa — el duplicado que más molesta a Alejandro, y
  // que hoy volvió a pasar con el corte del Apodo aunque el GAS contestó «retiradas: 2».
  var esRetirada_ = function (x) {
    return /^retirada/i.test(String(x.estado || '')) || /^retirada/i.test(String(x.origen || ''));
  };
  var deHoy = PR.filter(function (x) { return fechaDe(x.fecha) === f && !esRetirada_(x); });
  var relevoVirtual = false, deAntes = {};
  // 8-sep: el relevo virtual COMPLEMENTA, ya no es «solo si la mesa está vacía». Antes, montar una pieza
  // nueva en un día que venía de relevo virtual apagaba el relevo y se llevaba de la mesa todo lo pendiente
  // (a Alejandro le desaparecieron las láminas 4 y 7 al montarle el video). Ahora lo pendiente de días
  // previos se suma a lo de hoy, y la Sala lo filtra con las marcas de esos días.
  if (f === hoy()) {
    // La mesa amanecía vacía de 00:00 a que la Mac despertara y corriera el relevo (5-sep: el de las
    // 6:00 no corrió). Si hoy no hay filas, se sirve la última versión de cada propuesta de los 14 días
    // previos que no esté retirada; la Sala descarta las ya decididas con las marcas de esos días.
    var lim14 = Utilities.formatDate(new Date(new Date(f + 'T12:00:00').getTime() - 14 * 864e5), TZ, 'yyyy-MM-dd');
    var ultimaPorId = {};
    PR.forEach(function (x) {
      var fx = fechaDe(x.fecha); if (fx < lim14 || fx >= f) return;
      var id = String(x.prop_id); if (!id) return;
      if (!ultimaPorId[id] || fechaDe(ultimaPorId[id].fecha) <= fx) ultimaPorId[id] = x;
    });
    var yaHoy = {}; deHoy.forEach(function (x) { yaHoy[String(x.prop_id)] = 1; });
    var extra = Object.keys(ultimaPorId).map(function (id) { return ultimaPorId[id]; })
      .filter(function (x) { return !esRetirada_(x) && !yaHoy[String(x.prop_id)]; });
    extra.forEach(function (x) { deAntes[String(x.prop_id)] = fechaDe(x.fecha); });
    relevoVirtual = !deHoy.length && extra.length > 0;      // «virtual» solo cuando la mesa venía vacía
    deHoy = deHoy.concat(extra);
  }
  var props = deHoy.map(function (x) {
    var lam, opc;
    try { lam = JSON.parse(x.laminas_json); } catch (err) { lam = []; }
    try { opc = JSON.parse(x.opciones_json); } catch (err) { opc = []; }
    return { id: String(x.prop_id), titulo: String(x.titulo), tipo: String(x.tipo || 'laminas'),
             laminas: lam, opciones: opc, video: String(x.video || '') || null,
             de_antes: deAntes[String(x.prop_id)] || null,
             origen: String(x.origen || '') || null };
  });

  var fus = fusionDia_(DE, f), dec = fus.dec, ult = fus.ult;
  if (ult) dec.guardado = Utilities.formatDate(new Date(ult), TZ, "yyyy-MM-dd'T'HH:mm:ss");
  heredarMarcas_(DE, props, dec, f);                   // marcas de dias previos en la misma respuesta
  props = props.filter(function (p) { return !p.de_antes || !cerrada_(p, dec.propuestas[p.id]); });   // lo traído de días previos ya decidido no vuelve   // sin cartas ya decididas

  // retro de ayer, contando SOLO su envio vigente
  var ayer = Utilities.formatDate(new Date(new Date(f + 'T12:00:00').getTime() - 864e5), TZ, 'yyyy-MM-dd');
  var vigAmap = vigentePorEditor(DE, ayer), vigA = {};
  Object.keys(vigAmap).forEach(function (q) { vigA[vigAmap[q]] = 1; });
  var r = { fecha: ayer, aprobadas: 0, tiradas: 0, producidas: 0, rehechas: 0, nota: '' };
  DE.forEach(function (d) {
    if (fechaDe(d.fecha) !== ayer || !vigA[String(d.envio_id)]) return;
    if (String(d.marca) === 'si') r.aprobadas++;
    if (String(d.marca) === 'no') r.tiradas++;
    if (d.nota_dia) r.nota = String(d.nota_dia);
  });
  PD.forEach(function (x) {
    if (fechaDe(x.fecha) !== ayer) return;
    if (String(x.estado) === 'video' || String(x.estado) === 'publicada') r.producidas++;
  });
  r.rehechas = relevoVirtual ? 0 : props.filter(function (x) { return x.origen; }).length;

  var lim = Utilities.formatDate(new Date(new Date(f + 'T12:00:00').getTime() + 35 * 864e5), TZ, 'yyyy-MM-dd');
  var parr = PA.filter(function (x) { var d = fechaDe(x.fecha); return d >= f && d <= lim; })
    .map(function (x) { return { fecha: fechaDe(x.fecha), pieza: String(x.pieza || ''),
      gate: String(x.gate || ''), desde: x.desde ? fechaDe(x.desde) : '',
      decision_editor: String(x.decision_editor || '') }; })
    .sort(function (a, b) { return a.fecha < b.fecha ? -1 : 1; });

  var dias = {}; PR.forEach(function (x) { dias[fechaDe(x.fecha)] = 1; });
  var bit = BI.filter(function (b) { return fechaDe(b.fecha_hora) === f; })
    .map(function (b) { var t = selloDe(b.fecha_hora);
      return { hora: t ? Utilities.formatDate(new Date(t), TZ, 'HH:mm') : '', evento: String(b.evento), detalle: String(b.detalle || '').slice(0, 200) }; });

  // ultima revision enviada (para el modo «Mientras no estabas» del Umbral)
  var ultRevT = 0;
  DE.forEach(function (d) { var t = selloDe(d.guardado); if (t > ultRevT) ultRevT = t; });
  var ultRev = ultRevT ? Utilities.formatDate(new Date(ultRevT), TZ, "yyyy-MM-dd'T'HH:mm:ss") : '';

  return {
    fecha: f, dias: Object.keys(dias).sort(), propuestas: props, decisiones: dec, retro: r,
    parrilla: parr, control: CO.length ? CO[CO.length - 1] : null,
    produccion: PD.slice().reverse().slice(0, 30).map(function (x) { x.fecha = fechaDe(x.fecha); return x; }),
    bitacora: bit, ultima_revision: ultRev, relevo_virtual: relevoVirtual
  };
}

/* ------------------------------------------------ escritura */
function doPost(e) {
  var d; try { d = JSON.parse(e.postData.contents); } catch (err) { return json({ error: 'cuerpo ilegible' }); }
  if (d && d.accion && d.accion !== 'entrada') { invalidarDia_(d.fecha || d.dia); _RECALENTAR = d.fecha || d.dia || hoy(); }   // lo que se escribe se ve en la siguiente lectura
  // «mándame mi entrada» NO pide clave: es justo para cuando ya no la tienes.
  // No revela nada: el correo va SOLO a la dirección de CONFIG.
  /* ENTRAR CON GOOGLE (3-sep): «estoy entrando por Google, quiero que así funcione».
     El OS ya validó al usuario con su Portero. Aquí NO se cree el correo que digan:
     se le pregunta al Portero por el token, y solo si él contesta ok se entrega la
     llave que corresponde a ese correo. El token no se guarda ni se escribe en la hoja. */
  // (accion 'canje_os' retirada el 4-sep: entregaba una llave permanente a cualquier sesión
  //  viva del Portero. Ya no hace falta: la credencial del Portero VALE como clave, y el
  //  backend decide el rol en cada request — ver rolPorPortero_.)

  if (d.accion === 'gracia_manual') {              // (agente) sembrar una llave anterior en gracia, para desbloquear a quien quedó fuera de una rotación
    if (rolDe(d.clave) !== 'agente') return json({ error: 'solo el agente' });
    var okg = [];
    (d.pares || []).forEach(function (par) {
      var k = String(par.rol || ''), v = String(par.anterior || '');
      if (['clave', 'clave_editor2', 'clave_lector', 'clave_agente'].indexOf(k) < 0 || v.length < 8) return;
      if (v === leerConfig(k)) return;               // nunca sembrar la vigente como «anterior»
      escribirConfig_(k + '_anterior', v); escribirConfig_(k + '_rotada_en', ahora()); okg.push(k);
    });
    bitacora('Gracia sembrada', okg.join(', ') + ' · ' + GRACIA_HORAS + ' h');
    return json({ ok: true, sembradas: okg, horas: GRACIA_HORAS });
  }

  if (d.accion === 'rotar_claves') {               // (agente) las 4 claves suaves cambian; la nueva del agente viaja en la respuesta y se guarda en la Mac
    if (rolDe(d.clave) !== 'agente') return json({ error: 'solo el agente' });
    var cfgR = hoja('CONFIG'), valsR = cfgR.getDataRange().getValues(), nuevas = {};
    ['clave', 'clave_editor2', 'clave_lector', 'clave_agente'].forEach(function (k) {
      var nv = Utilities.getUuid().replace(/-/g, '').slice(0, 16), filas_ = [];
      var previa = leerConfig(k);
      // 8-sep (revisión): si ya hay una gracia VIGENTE, no se pisa — si no, una segunda rotación dentro de
      // las 72 h dejaría fuera de golpe a quien todavía trae la llave más vieja.
      var graciaVigente = false, desdeAnt = leerConfig(k + '_rotada_en');
      if (leerConfig(k + '_anterior') && desdeAnt) {
        var hs = (new Date().getTime() - new Date(desdeAnt).getTime()) / 3600000;
        graciaVigente = (hs >= 0 && hs <= GRACIA_HORAS);
      }
      if (previa && !graciaVigente) { escribirConfig_(k + '_anterior', previa); escribirConfig_(k + '_rotada_en', ahora()); }
      for (var i = 1; i < valsR.length; i++) if (String(valsR[i][0]) === k) filas_.push(i + 1);
      // 7-sep: si CONFIG trae la llave repetida, se actualizan TODAS las filas (antes se escribía la última y se leía la primera → «clave incorrecta»)
      if (filas_.length) filas_.forEach(function (fl) { cfgR.getRange(fl, 2).setValue(nv); }); else cfgR.appendRow([k, nv]);
      nuevas[k] = nv;
    });
    bitacora('Claves rotadas', 'las 4 claves suaves cambiaron a peticion del agente');
    return json({ ok: true, claves: nuevas });
  }
  if (d.accion === 'expediente') {                 // la Mac publica la historia de una pieza
    if (rolDe(d.clave) !== 'agente' && rolDe(d.clave) !== 'editor') return json({ error: 'solo el agente' });
    if (!d.pieza) return json({ error: 'falta la pieza' });
    var h = hoja('EXPEDIENTES');
    if (!h) {                                     // la pestaña nace sola la primera vez
      h = SpreadsheetApp.getActive().insertSheet('EXPEDIENTES');
      h.appendRow(PESTANAS.EXPEDIENTES); h.setFrozenRows(1);
    }
    var datos = h.getDataRange().getValues(), fila = 0;
    for (var i = 1; i < datos.length; i++) if (String(datos[i][0]) === String(d.pieza)) { fila = i + 1; break; }
    var v = [String(d.pieza), ahora(), JSON.stringify(d.expediente || {})];
    if (fila) h.getRange(fila, 1, 1, 3).setValues([v]); else h.appendRow(v);
    return json({ ok: true });
  }

  if (d.accion === 'catalogar') {                  // (agente) la Mac vuelca el catálogo completo
    if (rolDe(d.clave) !== 'agente' && rolDe(d.clave) !== 'editor') return json({ error: 'solo el agente' });
    var h = hoja('CATALOGO');
    if (!h) { h = SpreadsheetApp.getActive().insertSheet('CATALOGO');
              h.appendRow(PESTANAS.CATALOGO); h.setFrozenRows(1); }
    var filasNuevas = [];
    (d.catalogo || []).forEach(function (a) {
      (a.revisiones || []).forEach(function (v) {
        filasNuevas.push([a.serial, a.pieza, a.lamina, v.r, (a.revisiones || []).length,
                          a.estado || 'en revisión', v.fecha || hoy(),
                          v.drive_prueba || '', v.drive_original || '', v.ruta || '', v.rutas || '',
                          v.pidio || '', v.huella || '']);
      });
    });
    // se reescribe entero: el catálogo se DERIVA de las huellas, no se edita a mano.
    if (h.getLastRow() > 1) h.getRange(2, 1, h.getLastRow() - 1, PESTANAS.CATALOGO.length).clearContent();
    if (filasNuevas.length) h.getRange(2, 1, filasNuevas.length, PESTANAS.CATALOGO.length).setValues(filasNuevas);
    CacheService.getScriptCache().remove('catalogo:v1');
    bitacora('catalogo', filasNuevas.length + ' revisiones de ' + (d.catalogo || []).length + ' láminas');
    return json({ ok: true, revisiones: filasNuevas.length, laminas: (d.catalogo || []).length });
  }

  if (d.accion === 'hojas') {                      // 12-sep: nacen REGLAS, MOTORES y COLA
    // IDEMPOTENTE a propósito: si la hoja ya existe no se toca, y de las filas por defecto sólo
    // se agregan las que faltan. Alejandro edita estos números a mano; correr esto dos veces
    // NUNCA debe devolverle sus cambios a los valores de fábrica ni duplicarle renglones.
    if (rolDe(d.clave) !== 'agente') return json({ error: 'solo el agente' });
    var ssH = SpreadsheetApp.getActive(), hechas = {};
    ['REGLAS', 'MOTORES', 'COLA', 'PROMPTS'].forEach(function (n) {
      var h = ssH.getSheetByName(n), nueva = false;
      if (!h) { h = ssH.insertSheet(n); nueva = true; }
      if (h.getLastRow() === 0) { h.appendRow(PESTANAS[n]); h.setFrozenRows(1); }
      // 12-sep, mordida en vivo: el `item` de una candidata es «3-1» y la hoja lo guardó como
      // la FECHA 1-mar-2026. Con eso el productor no reconocía sus propias candidatas y las
      // volvía a encolar en cada pasada. Las columnas de identidad (id e item) se fuerzan a
      // TEXTO; se reaplica en cada corrida porque es idempotente y barato.
      if (n === 'COLA') {
        h.getRange(1, 1, h.getMaxRows(), 1).setNumberFormat('@');
        h.getRange(1, 4, h.getMaxRows(), 1).setNumberFormat('@');
      }
      // misma mordida que la COLA: la columna `lamina` de PROMPTS es identidad («3», «5»),
      // y una hoja sin formato la convierte en número —o peor, en fecha— y deja de cuadrar
      // con el `item` de la COLA, que sí es texto.
      if (n === 'PROMPTS') h.getRange(1, 2, h.getMaxRows(), 1).setNumberFormat('@');
      hechas[n] = { creada: nueva, filas_antes: Math.max(0, h.getLastRow() - 1) };
    });
    // REGLAS: se agrega la que falte, por nombre
    var hR = ssH.getSheetByName('REGLAS'), yaR = {};
    filas('REGLAS').forEach(function (r) { yaR[String(r.nombre || '').trim()] = 1; });
    var nuevasR = REGLAS_DEFAULT.filter(function (x) { return !yaR[x[0]]; });
    if (nuevasR.length) hR.getRange(hR.getLastRow() + 1, 1, nuevasR.length, 3).setValues(nuevasR);
    // MOTORES: la llave es etapa+motor (una etapa tiene varios motores en cascada)
    var hM = ssH.getSheetByName('MOTORES'), yaM = {};
    filas('MOTORES').forEach(function (m) { yaM[String(m.etapa).trim() + '|' + String(m.motor).trim()] = 1; });
    var nuevasM = MOTORES_DEFAULT.filter(function (x) { return !yaM[x[0] + '|' + x[1]]; });
    if (nuevasM.length) hM.getRange(hM.getLastRow() + 1, 1, nuevasM.length, 7).setValues(nuevasM);
    bitacora('Hojas del plan de raíz', 'REGLAS +' + nuevasR.length + ' · MOTORES +' + nuevasM.length + ' · COLA y PROMPTS listas');
    return json({ ok: true, hojas: hechas, reglas_agregadas: nuevasR.length, motores_agregados: nuevasM.length });
  }

  if (d.accion === 'prompts') {                    // 12-sep: las recetas base de cada lámina
    /* Idempotente con la misma vara que 'hojas': la llave es pieza+lamina y por defecto sólo
       AGREGA lo que falta. Alejandro (o Sayri) van a corregir estos prompts a mano en el
       Sheet — sembrar dos veces jamás debe devolverles su texto al de fábrica. `forzar:1`
       reescribe, y sólo se usa cuando de verdad se quiere sustituir la receta. */
    if (rolDe(d.clave) !== 'agente') return json({ error: 'solo el agente' });
    var hP = hoja('PROMPTS');
    if (!hP) return json({ error: 'no existe la hoja PROMPTS: corre antes accion:hojas' });
    var dtP = hP.getDataRange().getValues(), dondeP = {};
    for (var iP = 1; iP < dtP.length; iP++) {
      var kP = String(dtP[iP][0] || '').trim() + '|' + String(dtP[iP][1] || '').trim();
      if (kP !== '|' && !(kP in dondeP)) dondeP[kP] = iP + 1;
    }
    var agregadas = 0, reescritas = 0, respetadas = 0, porAgregarP = [];
    (d.filas || []).forEach(function (x) {
      var pz = String(x.pieza || '').trim(), lm = String(x.lamina === undefined ? '' : x.lamina).trim();
      if (!pz || !lm) return;
      var v = [pz, lm, String(x.prompt_base || ''), String(x.acento || ''), String(x.notas || '')];
      var fl = dondeP[pz + '|' + lm];
      if (fl) {
        if (d.forzar) { hP.getRange(fl, 1, 1, 5).setValues([v]); reescritas++; }
        else respetadas++;
      } else { porAgregarP.push(v); agregadas++; dondeP[pz + '|' + lm] = -1; }
    });
    if (porAgregarP.length) hP.getRange(hP.getLastRow() + 1, 1, porAgregarP.length, 5).setValues(porAgregarP);
    bitacora('PROMPTS sembrados', agregadas + ' nueva(s), ' + reescritas + ' reescrita(s), ' +
             respetadas + ' respetada(s) tal como estaban');
    return json({ ok: true, agregadas: agregadas, reescritas: reescritas, respetadas: respetadas });
  }

  if (d.accion === 'regla') {                      // 12-sep: prender/apagar reglas sin abrir el Sheet
    // Alejandro: «nada hardcodeado». Una regla vive en la hoja REGLAS; esto sólo la EDITA
    // (nombre → valor). Si el nombre no existe, se agrega al final con su descripción.
    if (rolDe(d.clave) !== 'agente') return json({ error: 'solo el agente edita reglas' });
    var hr = hoja('REGLAS'); if (!hr) return json({ error: 'no existe la hoja REGLAS (corre accion=hojas)' });
    var dr = hr.getDataRange().getValues(), n = 0;
    Object.keys(d.set || {}).forEach(function (k) {
      var fila = -1;
      for (var i = 1; i < dr.length; i++) if (String(dr[i][0]).trim() === k) { fila = i + 1; break; }
      if (fila > 0) hr.getRange(fila, 2).setValue(String(d.set[k]));
      else hr.appendRow([k, String(d.set[k]), d.desc && d.desc[k] ? d.desc[k] : '']);
      n++;
    });
    bitacora('Reglas editadas: ' + Object.keys(d.set || {}).join(', '), '');
    return jsonR({ ok: true, editadas: n });
  }

  if (d.accion === 'cola') {                       // 12-sep: el productor escribe sus trabajos
    /* op:'upsert' → crea o reemplaza la fila completa por `id`.
       op:'estado' → sólo mueve estado/motor/evidencia/bloqueado_por de una fila que ya existe.
       El `id` es la identidad del trabajo (pieza:etapa:item:version): por eso mandar dos veces
       lo mismo no apila filas. Sin esa idempotencia, un productor que se cae a media corrida
       dejaría la cola llena de gemelos y volvería a animar lo ya animado. */
    if (rolDe(d.clave) !== 'agente') return json({ error: 'solo el agente' });
    var op = String(d.op || 'upsert');
    if (['upsert', 'estado'].indexOf(op) < 0) return json({ error: 'op desconocida (upsert|estado)' });
    var hC = hoja('COLA');
    if (!hC) return json({ error: 'no existe la hoja COLA: corre antes accion:hojas' });
    var dtC = hC.getDataRange().getValues(), donde = {};
    for (var iC = 1; iC < dtC.length; iC++) {
      var idC = String(dtC[iC][0] || '').trim(); if (idC && !(idC in donde)) donde[idC] = iC + 1;
    }
    var creadas = 0, tocadas = 0, ignoradas = [], porAgregar = [];
    (d.filas || []).forEach(function (t) {
      var id = String(t.id || '').trim(); if (!id) { ignoradas.push('(sin id)'); return; }
      var fila = donde[id];
      if (op === 'estado') {
        if (!fila) { ignoradas.push(id); return; }   // 'estado' nunca inventa un trabajo
        var actual = dtC[fila - 1];
        if (t.motor !== undefined) hC.getRange(fila, 5).setValue(String(t.motor));
        if (t.estado !== undefined) hC.getRange(fila, 6).setValue(String(t.estado));
        if (t.bloqueado_por !== undefined) hC.getRange(fila, 8).setValue(String(t.bloqueado_por));
        if (t.evidencia !== undefined)
          hC.getRange(fila, 9).setValue(typeof t.evidencia === 'string' ? t.evidencia : JSON.stringify(t.evidencia));
        hC.getRange(fila, 12).setValue(ahora());
        tocadas++; return;
      }
      var v = [id, String(t.pieza || ''), String(t.etapa || ''),
               String(t.item === undefined || t.item === null ? '' : t.item),
               String(t.motor || ''), String(t.estado || 'pendiente'),
               Number(t.prioridad === undefined ? 5 : t.prioridad), String(t.bloqueado_por || ''),
               typeof t.evidencia === 'string' ? t.evidencia : JSON.stringify(t.evidencia || {}),
               String(t.pidio || 'productor'), '', ahora()];
      if (fila) {
        v[10] = String(dtC[fila - 1][10] || ahora());   // el «creado» original no se pierde al reescribir
        hC.getRange(fila, 1, 1, 12).setValues([v]); tocadas++;
      } else { v[10] = ahora(); porAgregar.push(v); creadas++; }
    });
    if (porAgregar.length) hC.getRange(hC.getLastRow() + 1, 1, porAgregar.length, 12).setValues(porAgregar);
    bitacora('COLA · ' + op, creadas + ' nueva(s), ' + tocadas + ' actualizada(s)' +
             (ignoradas.length ? ' · sin fila: ' + ignoradas.join(', ') : ''));
    return json({ ok: true, op: op, creadas: creadas, actualizadas: tocadas, ignoradas: ignoradas });
  }

  if (d.accion === 'sembrar_editores') {
    if (rolDe(d.clave) !== 'agente' && rolDe(d.clave) !== 'editor') return json({ error: 'solo el agente' });
    return json({ ok: true, resultado: sembrarEditores() });
  }

  if (d.accion === 'entrada') {                 // «mándame mi entrada» desde cualquier aparato
    var props = PropertiesService.getScriptProperties();
    var ult = Number(props.getProperty('ult_entrada') || 0);
    if (Date.now() - ult < 60000) return json({ ok: true, espera: true });   // un correo por minuto
    var dia = Utilities.formatDate(new Date(), TZ, 'yyyy-MM-dd');
    var cuenta = JSON.parse(props.getProperty('entradas_dia') || '{}');
    if (cuenta.dia !== dia) cuenta = { dia: dia, n: 0 };
    if (cuenta.n >= 8) return json({ ok: true, espera: true, tope: true });  // nadie agota la cuota
    cuenta.n++; props.setProperty('entradas_dia', JSON.stringify(cuenta));
    props.setProperty('ult_entrada', String(Date.now()));
    var exec = ScriptApp.getService().getUrl();
    var ligaE = PORTAL + '#gas=' + encodeURIComponent(exec) + '&clave=' + encodeURIComponent(leerConfig('clave')) + '&rol=editor';
    bitacora('Entrada enviada por correo', 'pedida desde la Sala');
    return json({ ok: true, correo: CORREO.replace(/^(.).*(@.*)$/, '$1•••$2') });
  }

  var rol = rolDe(d.clave);
  // 8-sep (revisión): también al ESCRIBIR se devuelve la llave renovada. Antes solo pasaba al leer el día,
  // así que quien solo mandaba su revisión llegaba a la hora 73 y se topaba con «no reconocí tu entrada».
  var _nuevaPost = claveNuevaPara_(d.clave);
  function jsonR(o){ if (_nuevaPost) { o.clave_nueva = _nuevaPost; o.aviso_llave = 'Tu llave se renovó; la Sala la guardó sola.'; } return json(o); }
  if (!rol) {                                    // que NINGÚN rechazo sea silencioso
    try { var kk = String(d.clave || ''); bitacora('Envío rechazado: credencial no reconocida',
      (d.accion || '') + ' · clave ' + kk.slice(0, 3) + '…(' + kk.length + ')'); } catch (e0) {}
    return json({ error: 'no reconocí tu entrada (credencial no válida o sin acceso a la Sala)' });
  }

  if (d.accion === 'decidir') {
    if (rol !== 'editor' && rol !== 'editor2') return json({ error: 'tu rol solo lee' });
    if (!/^\d{4}-\d{2}-\d{2}$/.test(d.fecha || '')) return json({ error: 'falta la fecha; no se guardó nada' });
    if (!d.envio_id) return json({ error: 'falta envio_id' });
    if (typeof d.propuestas !== 'object') return json({ error: 'revisión mal formada' });

    var DE = filas('DECISIONES');
    for (var i = 0; i < DE.length; i++)                     // idempotencia: mismo envio_id = ya esta
      if (String(DE[i].envio_id) === String(d.envio_id))
        return jsonR({ ok: true, guardado: String(DE[i].guardado), repetido: true });

    var sello = ahora(), h = hoja('DECISIONES'), fs = [];
    Object.keys(d.propuestas).forEach(function (pid) {
      var p = d.propuestas[pid] || {};
      (p.laminas || []).forEach(function (m, i2) {
        // la nota POR LAMINA y las mejoras palomeadas viajan en la misma fila de
        // la marca: el agente lee exactamente que le cambio a cada foto tachada
        var notaLam = (p.notas && p.notas[i2]) || '';
        var mej = (p.mejoras && p.mejoras[i2] && p.mejoras[i2].length)
                  ? ' [mejoras elegidas: ' + p.mejoras[i2].join(',') + ']' : '';
        fs.push([d.envio_id, rol, sello, d.fecha, pid, i2, m || 'pendiente', notaLam + mej, '', '']);
      });
      fs.push([d.envio_id, rol, sello, d.fecha, pid, '', '', p.nota || '', '', '']);
    });
    fs.push([d.envio_id, rol, sello, d.fecha, '', '', '', '', d.nota_general || '', d.nota_estrategia || '']);
    h.getRange(h.getLastRow() + 1, 1, fs.length, 10).setValues(fs);
    bitacora('Revisión recibida de ' + rol, fs.length + ' registro(s) · envío ' + String(d.envio_id).slice(0, 8));
    // 7-sep: la cache del día se recalienta en un disparador aparte 1 s después, para que este POST conteste
    // en ~3 s (con calentarCache() adentro tardaba 15-27 s y la Sala se quedaba en «Guardando…»).
    if ((d.fecha || hoy()) === hoy()) programarCalentado_();
    return jsonR({ ok: true, guardado: sello });
  }

  if (d.accion === 'parrilla_decision') {                   // el andon jalado desde la Mesa
    if (rol !== 'editor' && rol !== 'editor2') return json({ error: 'tu rol solo lee' });
    if (d.decision !== 'empujar' && d.decision !== 'matar') return json({ error: 'decisión desconocida' });
    var hp = hoja('PARRILLA'), datos = hp.getDataRange().getValues(), fila = -1;
    for (var j = 1; j < datos.length; j++)
      if (fechaDe(datos[j][0]) === d.dia) { fila = j + 1; break; }
    if (fila < 0) return json({ error: 'no encontré ese día en la parrilla' });
    hp.getRange(fila, 5, 1, 2).setValues([[d.decision, ahora()]]);
    bitacora('Andón: ' + (d.pieza || '') + ' → ' + d.decision + ' (' + rol + ')');
    return jsonR({ ok: true });
  }

  if (d.accion === 'proponer') {                            // la Mac monta el dia
    if (rol !== 'agente' && rol !== 'editor') return json({ error: 'solo el agente propone' });
    var hpr = hoja('PROPUESTAS'), fpr = d.fecha || hoy();
    // 7-sep (Alejandro: «¿por qué me duplicas cosas a revisar?»): proponer es IDEMPOTENTE.
    // Si ya existe una fila con la misma fecha + prop_id, se reemplaza; nunca se apila.
    var dtp = hpr.getDataRange().getValues();
    (d.propuestas || []).forEach(function (p) {
      var fila = [fpr, p.id, p.titulo, p.tipo || 'laminas',
                  JSON.stringify(p.laminas || []), JSON.stringify(p.opciones || []),
                  p.video || '', 'en revisión', p.origen || ''];
      var vistas = [];
      for (var q = 1; q < dtp.length; q++) if (fechaDe(dtp[q][0]) === fpr && String(dtp[q][1]) === String(p.id)) vistas.push(q + 1);
      if (vistas.length) {
        hpr.getRange(vistas[0], 1, 1, fila.length).setValues([fila]);
        for (var w = vistas.length - 1; w >= 1; w--) hpr.deleteRow(vistas[w]);   // duplicados fuera
        dtp = hpr.getDataRange().getValues();
      } else hpr.appendRow(fila);
    });
    // 12-sep (tarde) · «una pieza, una carta viva». Alejandro: «no quiero cosas a medias ni
    // andarte picando… que no me dejes duplicados». Al Apodo se le preguntó SEIS veces porque
    // cada rehecha montaba una carta nueva y la anterior se quedaba en la mesa. Si la llamada
    // declara su FAMILIA (el prefijo de la pieza) y la regla está encendida, toda carta viva de
    // esa familia que NO venga en este envío se retira aquí mismo, en la misma escritura: el
    // cliente ya no puede «olvidarse» de retirarla. Lo que este guardia NO hace es decidir si
    // una carta estaba decidida o no —eso vive en DECISIONES y lo evalúa el productor—; aquí
    // sólo se garantiza que no queden dos cartas de la misma pieza esperando respuesta.
    var retFam = [];
    if (d.familia && String(reglaGas_('una_carta_por_pieza', 1)) !== '0') {
      var fam = String(d.familia);
      var nuevos = {}; (d.propuestas || []).forEach(function (p) { nuevos[String(p.id)] = 1; });
      var dtf = hpr.getDataRange().getValues();
      for (var rf = 1; rf < dtf.length; rf++) {
        var idf = String(dtf[rf][1] || '');
        if (idf.indexOf(fam) !== 0 || nuevos[idf]) continue;
        if (String(dtf[rf][7] || '') === 'retirada') continue;
        hpr.getRange(rf + 1, 8, 1, 2).setValues([['retirada',
          'retirada · una carta por pieza: la sustituye ' + Object.keys(nuevos).join(', ')]]);
        retFam.push(idf);
      }
    }
    bitacora('Propuestas del día montadas', (d.propuestas || []).length + ' propuesta(s)' +
             (retFam.length ? ' · familia «' + d.familia + '»: retiradas ' + retFam.join(', ') : ''));
    return jsonR({ ok: true, retiradas_familia: retFam });
  }

  if (d.accion === 'retirar') {                             // 7-sep: sacar de la mesa sin borrar historia
    if (rol !== 'agente' && rol !== 'editor') return json({ error: 'solo el agente retira' });
    var hpq = hoja('PROPUESTAS'), dtq = hpq.getDataRange().getValues(), fq = d.fecha || hoy(), nq = 0;
    var ids = (d.ids || []).map(String);
    var tocado = {};
    for (var r2 = 1; r2 < dtq.length; r2++) {
      if (fechaDe(dtq[r2][0]) === fq && ids.indexOf(String(dtq[r2][1])) >= 0) {
        hpq.getRange(r2 + 1, 8, 1, 2).setValues([['retirada', 'retirada · ' + (d.motivo || 'por Producción')]]);
        tocado[String(dtq[r2][1])] = 1; nq++;
      }
    }
    // 8-sep: una pieza que llega a la mesa por el RELEVO no tiene fila de hoy — su fila vive en un día
    // anterior. Antes «retirar» contestaba ok sin retirar nada y la pieza volvía en la siguiente lectura
    // (le pasó a «¿Vendo o construyo?», ya publicada). Ahora se marca su fila más reciente, sea del día que sea.
    ids.forEach(function (id) {
      if (tocado[id]) return;
      var mejor = -1, mejorF = '';
      for (var r3 = 1; r3 < dtq.length; r3++) {
        if (String(dtq[r3][1]) !== id) continue;
        var fx = fechaDe(dtq[r3][0]);
        if (fx >= mejorF) { mejorF = fx; mejor = r3; }
      }
      if (mejor > 0) {
        hpq.getRange(mejor + 1, 8, 1, 2).setValues([['retirada', 'retirada · ' + (d.motivo || 'por Producción')]]); nq++;
      }
    });
    bitacora('Retiradas de la mesa: ' + ids.join(', '), d.motivo || '');
    return jsonR({ ok: true, retiradas: nq });
  }

  if (d.accion === 'parrilla') {                            // la Mac actualiza un hueco
    if (rol !== 'agente' && rol !== 'editor') return json({ error: 'solo el agente' });
    var hpa = hoja('PARRILLA'), dt = hpa.getDataRange().getValues(), f2 = -1;
    for (var k = 1; k < dt.length; k++) if (fechaDe(dt[k][0]) === d.dia) { f2 = k + 1; break; }
    var v = [d.dia, d.pieza || '', d.gate || '', d.desde || hoy(), '', ''];
    if (f2 > 0) hpa.getRange(f2, 1, 1, 6).setValues([v]); else hpa.appendRow(v);
    bitacora('Parrilla: ' + d.dia + ' → ' + (d.pieza || 'hueco'));
    return jsonR({ ok: true });
  }

  if (d.accion === 'produccion') {                          // la Mac reporta avances
    if (rol !== 'agente' && rol !== 'editor') return json({ error: 'solo el agente' });
    hoja('PRODUCCION').appendRow([d.fecha || hoy(), d.pieza || '', d.estado || '',
                                  d.detalle || '', d.enlace || '']);
    bitacora('Producción: ' + (d.pieza || '') + ' → ' + (d.estado || ''), d.detalle || '');
    return jsonR({ ok: true });
  }

  return json({ error: 'acción desconocida' });
}

/* ------------------------------------------------ el correo de las 7:00 */
function correoDiario() {
  var f = hoy();
  var n = filas('PROPUESTAS').filter(function (x) { return fechaDe(x.fecha) === f; }).length;
  var asunto = n > 0 ? 'Sala de Edición · ' + n + ' propuesta(s) esperan tu revisión'
                     : 'Sala de Edición · hoy no hay pendientes';
  // la liga trae la sesion en el fragmento #: no viaja al servidor y el portal la siembra solo
  var exec = ScriptApp.getService().getUrl();
  var liga = PORTAL + '#gas=' + encodeURIComponent(exec) +
             '&clave=' + encodeURIComponent(leerConfig('clave')) + '&rol=editor';
  var html =
    '<div style="background:#0a0a0c;padding:34px 22px;font-family:Georgia,serif;color:#f4f1ec">' +
    '<p style="color:#debc7e;font-size:12px;letter-spacing:3px;margin:0 0 6px">YO DESARROLLO</p>' +
    '<h2 style="font-weight:400;margin:0 0 16px">Sala de <em style="color:#debc7e">Edición</em></h2>' +
    '<p style="font-size:15px;line-height:1.6;margin:0 0 22px">' +
    (n > 0 ? 'Hay <b>' + n + ' propuesta(s)</b> esperándote. Cinco minutos.' : 'Hoy no hay propuestas nuevas.') + '</p>' +
    '<a href="' + liga + '" style="background:#c2a06b;color:#17130c;text-decoration:none;' +
    'padding:13px 26px;border-radius:8px;font-family:-apple-system,sans-serif;font-weight:600">Abrir mi turno</a>' +
    '<p style="color:#8a867e;font-size:12px;margin:26px 0 0">Palomea lo que sirve, tacha lo que no, ' +
    'y escribe lo que quieres distinto.</p></div>';
  MailApp.sendEmail({ to: CORREO, subject: asunto, htmlBody: html });
  bitacora('Correo de las 7:00 enviado', asunto);
}


/* Migracion de un solo sentido: instalar() corrio con claves aleatorias antes de
   que la siembra llegara al despliegue. Las claves canonicas (las que la Mac y el
   portal conocen) sobreescriben; cuando ya coinciden, no toca nada. */
function resembrar() {
  var SEM = {'clave':'57c6b8a8b91648c6','clave_editor2':'e9bf841689014e6d','clave_lector':'95398491248444a1','clave_agente':'3b2e27caa9d64ba8'};
  var h = hoja('CONFIG'); if (!h) return;
  var datos = h.getDataRange().getValues(), vistos = {};
  for (var i = 1; i < datos.length; i++) {
    var k = String(datos[i][0]);
    if (SEM[k] !== undefined) { vistos[k] = true;
      if (String(datos[i][1]) !== SEM[k]) h.getRange(i + 1, 2).setValue(SEM[k]); }
  }
  Object.keys(SEM).forEach(function (k) { if (!vistos[k]) h.appendRow([k, SEM[k]]); });
}


/* Siembra/actualiza los correos y nombres de los dos editores sin tocar nada más.
   Se corre desde la Mac con accion:'sembrar_editores' o a mano desde el editor. */
function sembrarEditores() {
  var pares = { correo_editor: CORREO, correo_editor2: 'proyectos@aurumarquitectos.com',
                nombre_editor: 'Alejandro', nombre_editor2: 'Sayri' };
  var h = hoja('CONFIG'), datos = h.getDataRange().getValues(), vistos = {};
  for (var i = 1; i < datos.length; i++) {
    var k = String(datos[i][0]);
    if (pares[k] !== undefined) { vistos[k] = true;
      if (String(datos[i][1]) !== pares[k]) h.getRange(i + 1, 2).setValue(pares[k]); }
  }
  Object.keys(pares).forEach(function (k) { if (!vistos[k]) h.appendRow([k, pares[k]]); });
  bitacora('Editores sembrados', 'Alejandro y Sayri con su correo');
  return 'ok';
}


/* CAMINO B para «una sola llave»: correr esta función UNA vez desde el editor del script
   (▶ Ejecutar → Revisar permisos → Permitir). Con eso el script queda autorizado para
   preguntarle al Portero por HTTP y la sesión del YOD OS entra a la Sala. */
function autorizar() {
  var r = UrlFetchApp.fetch(PORTERO_EXEC + '?recurso=meta', { muteHttpExceptions: true, followRedirects: true });
  bitacora('Autorización concedida', 'UrlFetchApp responde ' + r.getResponseCode());
  return 'ok · ' + r.getResponseCode();
}
