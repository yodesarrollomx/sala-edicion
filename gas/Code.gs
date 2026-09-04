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
  BITACORA:   ['fecha_hora', 'evento', 'detalle']
};

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
  var SEMILLA = {'clave':'…','clave_editor2':'…','clave_lector':'…','clave_agente':'…'};
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
function rolDe(clave) {
  if (!clave) return null;
  if (clave === leerConfig('clave')) return 'editor';
  if (clave === leerConfig('clave_editor2')) return 'editor2';
  if (clave === leerConfig('clave_lector')) return 'lector';
  if (clave === leerConfig('clave_agente')) return 'agente';
  return rolPorPortero_(clave);          // UNA SOLA LLAVE: la sesión del YOD OS también entra
}

/* UNA SOLA LLAVE (3-sep-2026, pedido de Alejandro: «la misma clave del portero me debe dar
   acceso a todo, incluida la Sala»). Patrón de la casa (ver board-aurum/apps-script/
   portero-auth.gs): el backend le pregunta al Portero por la credencial —liga mágica de 90
   días, clave de equipo o Google— y decide él mismo la autorización. Se canjea SIN &board=
   para no depender del filtro del Portero. Caché por hash: 10 min si vale, 1 min si no.
   Portero caído = nadie entra por esta vía (fail-closed), pero las claves suaves siguen. */
var PORTERO_EXEC = 'https://script.google.com/macros/s/AKfycbwlDDCWWzOWYZsUpBU9uqsQ7aenQ469PF6s6FkNlBFS1_cJSU5njG9oQmuyELy5zlqzFg/exec';
var CODIGO_SALA  = 'MK';               // la Sala vive en el Embudo, junto a Métricas/Marketing
function rolPorPortero_(k) {
  k = String(k || '').trim();
  if (k.length < 8) return null;
  var cache = CacheService.getScriptCache();
  var ck = 'sala_auth_' + Utilities.base64EncodeWebSafe(
    Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, k)).slice(0, 24);
  var hit = cache.get(ck);
  if (hit) return hit === 'no' ? null : hit;
  var rol = null, nombre = '';
  try {
    var r = UrlFetchApp.fetch(PORTERO_EXEC + '?recurso=canje&t=' + encodeURIComponent(k),
      { muteHttpExceptions: true, followRedirects: true });
    var j = JSON.parse(r.getContentText());
    var role = String(j && j.rol || '').toLowerCase();
    var boards = String(j && j.boards || '');
    var puede = !!(j && j.ok && (role === 'admin' || boards.trim() === '*' ||
      boards.split(',').map(function (v) { return v.trim().toUpperCase(); }).indexOf(CODIGO_SALA) >= 0));
    if (puede) {
      var correo = String(j.correo || '').toLowerCase().trim();
      nombre = String(j.nombre || '');
      if (correo && correo === String(leerConfig('correo_editor') || CORREO).toLowerCase()) rol = 'editor';
      else if (correo && correo === String(leerConfig('correo_editor2') || '').toLowerCase()) rol = 'editor2';
      else rol = 'lector';
      if (nombre) cache.put(ck + '_n', nombre, 300);
    }
  } catch (err) { rol = null; }        // Portero inaccesible → fail-closed
  cache.put(ck, rol || 'no', rol ? 300 : 60);   // 5 min: revocar a alguien no debe tardar 20
  return rol;
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
function json(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
function fechaDe(v) {
  // a prueba de zonas: medianoche de CUALQUIER zona +12 h cae en la fecha correcta en UTC
  return (v instanceof Date)
    ? Utilities.formatDate(new Date(v.getTime() + 43200000), 'Etc/UTC', 'yyyy-MM-dd')
    : String(v).slice(0, 10);
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

/* ------------------------------------------------ lectura */
function doGet(e) {
  var p = (e && e.parameter) || {};
  // (Antes aquí corría resembrar() en cada lectura: escribía en CONFIG en cada request y
  //  volvía imposible rotar las claves. Ahora sólo se corre a mano desde el editor.)
  var rolQuien = rolDe(p.clave);
  if (!rolQuien) return json({ error: 'clave incorrecta' });
  if (p.recurso !== 'dia') return json({ error: 'recurso desconocido' });
  var f = /^\d{4}-\d{2}-\d{2}$/.test(p.f || '') ? p.f : hoy();

  // una lectura por pestaña (presupuesto <3 s firmado por el ingeniero)
  var PR = filas('PROPUESTAS'), DE = filas('DECISIONES'), PA = filas('PARRILLA'),
      CO = filas('CONTROL'), PD = filas('PRODUCCION'), BI = filas('BITACORA');

  var props = PR.filter(function (x) { return fechaDe(x.fecha) === f; }).map(function (x) {
    var lam, opc;
    try { lam = JSON.parse(x.laminas_json); } catch (err) { lam = []; }
    try { opc = JSON.parse(x.opciones_json); } catch (err) { opc = []; }
    return { id: String(x.prop_id), titulo: String(x.titulo), tipo: String(x.tipo || 'laminas'),
             laminas: lam, opciones: opc, video: String(x.video || '') || null,
             origen: String(x.origen || '') || null };
  });

  // decisiones: el ultimo envio DE CADA EDITOR, fusionados (ver vigentePorEditor)
  var vigE = vigentePorEditor(DE, f);
  var vivos = {}; Object.keys(vigE).forEach(function (q) { vivos[vigE[q]] = q; });
  var dec = { propuestas: {}, editores: [] }, ult = 0;
  DE.forEach(function (d) {
    if (fechaDe(d.fecha) !== f) return;
    var eid = String(d.envio_id); if (!(eid in vivos)) return;
    var rol = vivos[eid], quien = nombreDe(rol);
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
  if (ult) dec.guardado = Utilities.formatDate(new Date(ult), TZ, "yyyy-MM-dd'T'HH:mm:ss");

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
  r.rehechas = props.filter(function (x) { return x.origen; }).length;

  var lim = Utilities.formatDate(new Date(new Date(f + 'T12:00:00').getTime() + 35 * 864e5), TZ, 'yyyy-MM-dd');
  var parr = PA.filter(function (x) { var d = fechaDe(x.fecha); return d >= f && d <= lim; })
    .map(function (x) { return { fecha: fechaDe(x.fecha), pieza: String(x.pieza || ''),
      gate: String(x.gate || ''), desde: x.desde ? fechaDe(x.desde) : '',
      decision_editor: String(x.decision_editor || '') }; })
    .sort(function (a, b) { return a.fecha < b.fecha ? -1 : 1; });

  var dias = {}; PR.forEach(function (x) { dias[fechaDe(x.fecha)] = 1; });
  var bit = BI.filter(function (b) { return String(b.fecha_hora).slice(0, 10) === f; })
    .map(function (b) { return { hora: String(b.fecha_hora).slice(11, 16), evento: String(b.evento) }; });

  // ultima revision enviada (para el modo «Mientras no estabas» del Umbral)
  var ultRevT = 0;
  DE.forEach(function (d) { var t = selloDe(d.guardado); if (t > ultRevT) ultRevT = t; });
  var ultRev = ultRevT ? Utilities.formatDate(new Date(ultRevT), TZ, "yyyy-MM-dd'T'HH:mm:ss") : '';

  return json({
    fecha: f, dias: Object.keys(dias).sort(), propuestas: props, decisiones: dec, retro: r,
    parrilla: parr, control: CO.length ? CO[CO.length - 1] : null,
    produccion: PD.slice().reverse().slice(0, 30).map(function (x) { x.fecha = fechaDe(x.fecha); return x; }),
    bitacora: bit, ultima_revision: ultRev, rol: rolQuien, quien: (rolQuien === 'editor' || rolQuien === 'editor2') ? nombreDe(rolQuien) : (nombrePortero_(p.clave) || ''), version: 'una-sola-llave-2026-09-03'
  });
}

/* ------------------------------------------------ escritura */
function doPost(e) {
  var d; try { d = JSON.parse(e.postData.contents); } catch (err) { return json({ error: 'cuerpo ilegible' }); }
  // «mándame mi entrada» NO pide clave: es justo para cuando ya no la tienes.
  // No revela nada: el correo va SOLO a la dirección de CONFIG.
  /* ENTRAR CON GOOGLE (3-sep): «estoy entrando por Google, quiero que así funcione».
     El OS ya validó al usuario con su Portero. Aquí NO se cree el correo que digan:
     se le pregunta al Portero por el token, y solo si él contesta ok se entrega la
     llave que corresponde a ese correo. El token no se guarda ni se escribe en la hoja. */
  // (accion 'canje_os' retirada el 4-sep: entregaba una llave permanente a cualquier sesión
  //  viva del Portero. Ya no hace falta: la credencial del Portero VALE como clave, y el
  //  backend decide el rol en cada request — ver rolPorPortero_.)

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
  if (!rol) return json({ error: 'clave incorrecta' });

  if (d.accion === 'decidir') {
    if (rol !== 'editor' && rol !== 'editor2') return json({ error: 'tu rol solo lee' });
    if (!/^\d{4}-\d{2}-\d{2}$/.test(d.fecha || '')) return json({ error: 'falta la fecha; no se guardó nada' });
    if (!d.envio_id) return json({ error: 'falta envio_id' });
    if (typeof d.propuestas !== 'object') return json({ error: 'revisión mal formada' });

    var DE = filas('DECISIONES');
    for (var i = 0; i < DE.length; i++)                     // idempotencia: mismo envio_id = ya esta
      if (String(DE[i].envio_id) === String(d.envio_id))
        return json({ ok: true, guardado: String(DE[i].guardado), repetido: true });

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
    return json({ ok: true, guardado: sello });
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
    return json({ ok: true });
  }

  if (d.accion === 'proponer') {                            // la Mac monta el dia
    if (rol !== 'agente' && rol !== 'editor') return json({ error: 'solo el agente propone' });
    var hpr = hoja('PROPUESTAS');
    (d.propuestas || []).forEach(function (p) {
      hpr.appendRow([d.fecha || hoy(), p.id, p.titulo, p.tipo || 'laminas',
                     JSON.stringify(p.laminas || []), JSON.stringify(p.opciones || []),
                     p.video || '', 'en revisión', p.origen || '']);
    });
    bitacora('Propuestas del día montadas', (d.propuestas || []).length + ' propuesta(s)');
    return json({ ok: true });
  }

  if (d.accion === 'parrilla') {                            // la Mac actualiza un hueco
    if (rol !== 'agente' && rol !== 'editor') return json({ error: 'solo el agente' });
    var hpa = hoja('PARRILLA'), dt = hpa.getDataRange().getValues(), f2 = -1;
    for (var k = 1; k < dt.length; k++) if (fechaDe(dt[k][0]) === d.dia) { f2 = k + 1; break; }
    var v = [d.dia, d.pieza || '', d.gate || '', d.desde || hoy(), '', ''];
    if (f2 > 0) hpa.getRange(f2, 1, 1, 6).setValues([v]); else hpa.appendRow(v);
    bitacora('Parrilla: ' + d.dia + ' → ' + (d.pieza || 'hueco'));
    return json({ ok: true });
  }

  if (d.accion === 'produccion') {                          // la Mac reporta avances
    if (rol !== 'agente' && rol !== 'editor') return json({ error: 'solo el agente' });
    hoja('PRODUCCION').appendRow([d.fecha || hoy(), d.pieza || '', d.estado || '',
                                  d.detalle || '', d.enlace || '']);
    bitacora('Producción: ' + (d.pieza || '') + ' → ' + (d.estado || ''), d.detalle || '');
    return json({ ok: true });
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
  var SEM = {'clave':'…','clave_editor2':'…','clave_lector':'…','clave_agente':'…'};
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
