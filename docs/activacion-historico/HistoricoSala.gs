function fechaProduccionValida_(f) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(f))) return false;
  var d = new Date(f + 'T12:00:00Z');
  return isFinite(d.getTime()) && d.toISOString().slice(0, 10) === f;
}
function selloProduccion_(valor) {
  if (valor instanceof Date) return selloDe(valor);
  if (typeof valor !== 'string') return 0;
  var iso = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?$/.exec(valor);
  if (!iso || !fechaProduccionValida_(iso[1]) || Number(iso[2]) > 23 || Number(iso[3]) > 59 || Number(iso[4] || 0) > 59) return 0;
  return selloDe(valor); // Date nativo conserva el instante real guardado por el GAS.
}
function fusionProduccion_(DE) {
  if (!Array.isArray(DE) || DE.length > 50000) throw new Error('produccion_sin_contrato');
  var ultimas = Object.create(null), maximo = 0;
  function elegir(clave, d, t, marca, nota) {
    var actual = ultimas[clave];
    if (!actual || t > actual.t) ultimas[clave] = { d: d, t: t, marca: marca, nota: nota, ambigua: false };
    else if (t === actual.t && (marca !== actual.marca || nota !== actual.nota)) actual.ambigua = true;
  }
  DE.forEach(function (d) {
    if (!d || typeof d !== 'object') throw new Error('produccion_decision_invalida');
    var rol = String(d.quien || 'editor'), pid = String(d.prop_id || ''), t = selloProduccion_(d.guardado);
    if (['editor', 'editor2'].indexOf(rol) < 0 || !t || !isFinite(t) ||
        (pid && !/^[A-Za-z0-9_.-]{1,256}$/.test(pid)) ||
        !fechaProduccionValida_(fechaDe(d.fecha))) throw new Error('produccion_decision_invalida');
    var esLam = d.lamina !== '' && d.lamina !== null && d.lamina !== undefined;
    var marca = String(d.marca || ''), nota = String(d.nota_propuesta || '');
    if (esLam) {
      var n = Number(d.lamina);
      if (!pid || !/^\d+$/.test(String(d.lamina)) || !Number.isInteger(n) || n > 999 ||
          ['', 'pendiente', 'si', 'no', 'borrar'].indexOf(marca) < 0) throw new Error('produccion_lamina_invalida');
      if (marca === 'si' || marca === 'no' || marca === 'borrar') elegir(rol + '|' + pid + '|lam|' + n, d, t, marca, nota);
    } else if (pid && nota) elegir(rol + '|' + pid + '|nota', d, t, '', nota);
    if (!pid && String(d.nota_dia || '')) elegir(rol + '|general', d, t, '', String(d.nota_dia));
    if (!pid && String(d.nota_estrategia || '')) elegir(rol + '|estrategia', d, t, '', String(d.nota_estrategia));
  });
  var dec = { propuestas: Object.create(null), editores: [] }, generales = [], estrategias = [];
  var nombresLectura = Object.create(null);
  Object.keys(ultimas).sort().forEach(function (clave) {
    var u = ultimas[clave], d = u.d;
    if (u.ambigua) throw new Error('produccion_sello_ambiguo');
    var rol = String(d.quien || 'editor'), pid = String(d.prop_id || '');
    if (!(rol in nombresLectura)) nombresLectura[rol] = nombreDe(rol);
    var quien = nombresLectura[rol];
    if (dec.editores.indexOf(quien) < 0) dec.editores.push(quien);
    if (u.t > maximo) maximo = u.t;
    if (!pid) {
      (clave.indexOf('|estrategia') >= 0 ? estrategias : generales).push(quien + ': ' + u.nota);
      return;
    }
    var fi = dec.propuestas[pid] = dec.propuestas[pid] || { laminas: [], nota: '', notas: [], firmas: [], firmas_nota: [] };
    if (clave.indexOf('|lam|') < 0) {
      fi.nota = fi.nota ? fi.nota + ' | ' + quien + ': ' + u.nota : quien + ': ' + u.nota;
      fi.firmas_nota.push({ rol: rol, quien: quien, nota: u.nota, guardado: new Date(u.t).toISOString() });
      return;
    }
    var n = Number(d.lamina), marca = u.marca === 'borrar' ? null : u.marca;
    var previa = fi.laminas[n] || null;
    fi.laminas[n] = previa === 'no' || marca === 'no' ? 'no' : (marca || previa);
    fi.firmas[n] = (fi.firmas[n] || []).concat([{ rol: rol, quien: quien, marca: marca,
      nota: u.nota, guardado: new Date(u.t).toISOString() }]);
  });
  Object.keys(dec.propuestas).forEach(function (pid) {
    var fi = dec.propuestas[pid];
    for (var i = 0; i < fi.laminas.length; i++) {
      if (fi.laminas[i] === undefined) fi.laminas[i] = null;
      if (!fi.firmas[i]) fi.firmas[i] = [];
      var notas = fi.firmas[i].filter(function (x) { return x.nota; });
      fi.notas[i] = notas.length === 1 ? notas[0].nota : notas.map(function (x) { return x.quien + ': ' + x.nota; }).join(' | ');
    }
  });
  if (generales.length) dec.nota_general = generales.join(' | ');
  if (estrategias.length) dec.nota_estrategia = estrategias.join(' | ');
  if (maximo) dec.guardado = new Date(maximo).toISOString();
  return dec;
}

function produccionHistorica_(f, PR, DE) {
  if (!fechaProduccionValida_(f) || !Array.isArray(PR) || PR.length > 10000)
    throw new Error('produccion_sin_contrato');
  var ultimas = Object.create(null), ambiguas = Object.create(null), dias = Object.create(null);
  PR.forEach(function (p) {
    var fecha = fechaDe(p.fecha), pid = String(p.prop_id || '');
    if (!fechaProduccionValida_(fecha) || !/^[A-Za-z0-9_.-]{1,256}$/.test(pid))
      throw new Error('produccion_fuente_invalida');
    dias[fecha] = 1;
    if (fecha <= f && (!ultimas[pid] || fechaDe(ultimas[pid].fecha) < fecha)) { ultimas[pid] = p; ambiguas[pid] = false; }
    else if (fecha <= f && fechaDe(ultimas[pid].fecha) === fecha && JSON.stringify(ultimas[pid]) !== JSON.stringify(p))
      ambiguas[pid] = true;
  });
  var retiradas = 0, props = [];
  Object.keys(ultimas).sort().forEach(function (pid) {
    if (ambiguas[pid]) throw new Error('produccion_fuente_duplicada');
    var p = ultimas[pid];
    if (/^retirada/i.test(String(p.estado || '')) || /^retirada/i.test(String(p.origen || ''))) { retiradas++; return; }
    var laminas = JSON.parse(p.laminas_json || '[]'), opciones = JSON.parse(p.opciones_json || '[]');
    if (!Array.isArray(laminas) || laminas.length > 1000 || !opciones || typeof opciones !== 'object')
      throw new Error('produccion_fuente_invalida');
    props.push({ id: pid, titulo: String(p.titulo || ''), tipo: String(p.tipo || 'laminas'),
      laminas: laminas, opciones: opciones, video: String(p.video || '') || null,
      origen: String(p.origen || '') || null, estado: String(p.estado || ''),
      fecha_fuente: fechaDe(p.fecha), de_antes: fechaDe(p.fecha) < f ? fechaDe(p.fecha) : null });
  });
  return { ok: true, contrato: 'produccion-historica-v1', alcance: 'historial_completo',
    version: 'produccion-historica-2026-10-15', fecha: f, dias: Object.keys(dias).sort(),
    propuestas: props, decisiones: fusionProduccion_(DE),
    fuentes: { leidas: PR.length, activas: props.length, retiradas: retiradas,
      decisiones_leidas: DE.length } };
}

function leerProduccionHistorica_() {
  ['PROPUESTAS', 'DECISIONES'].forEach(function (n) {
    var h = hoja(n);
    if (!h || h.getLastRow() < 1) throw new Error('produccion_hoja_ausente');
    var cab = h.getRange(1, 1, 1, PESTANAS[n].length).getValues()[0];
    if (JSON.stringify(cab) !== JSON.stringify(PESTANAS[n])) throw new Error('produccion_cabecera_invalida');
  });
  return produccionHistorica_(hoy(), filas('PROPUESTAS'), filas('DECISIONES'));
}

function respuestaProduccionHistorica_(rolQuien) {
  if (rolQuien !== 'agente') return json({ error: 'solo el agente' });
  try { return json(leerProduccionHistorica_()); }
  catch (errProduccion) { return json({ ok: false, contrato: 'produccion-historica-v1',
    alcance: 'historial_completo', error: 'produccion_sin_lectura_confirmada' }); }
}

