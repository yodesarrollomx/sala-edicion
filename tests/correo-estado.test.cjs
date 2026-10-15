const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const TODAY = '2026-10-14';
function backend() {
  const ctx = vm.createContext({});
  vm.runInContext(fs.readFileSync(process.env.SALA_GAS_SOURCE || path.join(__dirname, '../gas/Code.gs'), 'utf8'), ctx);
  ctx.leerConfig = k => ({nombre_editor: 'Editor uno', nombre_editor2: 'Editor dos', clave: 'sintetica'}[k] || '');
  ctx.hoy = () => TODAY;
  return ctx;
}
function prop(id, extra = {}) {
  return {prop_id: id, fecha: '2026-09-01', laminas_json: '["uno.jpg"]', opciones_json: '[]', tipo: 'laminas', ...extra};
}
function decision(id, mark, extra = {}) {
  return {envio_id: 'e1', prop_id: id, fecha: '2026-09-02', guardado: '2026-09-02T12:00:00-07:00',
    quien: 'editor', lamina: 0, marca: mark, ...extra};
}
function summarize(ctx, props = [], dec = [], production = [], queue = []) {
  return ctx.estadoCorreo_(TODAY, props, dec, production, queue);
}

test('historial de más de 14 días y retiro más reciente; aprobar no publica', () => {
  const ctx = backend();
  const props = [prop('pendiente'), prop('lista'), prop('retirada'),
    prop('retirada', {fecha: '2026-10-01', estado: 'retirada'}), prop('futura', {fecha: '2026-10-20'})];
  const decisions = [decision('lista', 'si')];
  const before = JSON.stringify({props, decisions});
  const r = summarize(ctx, props, decisions);
  assert.equal(r.revision, 1);
  assert.equal(r.aprobadas, 1);
  assert.equal(r.producidas, 0);
  assert.equal(r.publicadas, 0);
  assert.equal(JSON.stringify({props, decisions}), before);
});

test('fusiona decisiones entre días sin perder láminas ni veto de otro editor', () => {
  const ctx = backend();
  const props = [prop('pieza', {laminas_json: '["uno.jpg","dos.jpg"]'})];
  const decisions = [decision('pieza', 'si'), decision('pieza', 'si', {
    envio_id: 'e2', lamina: 1, fecha: '2026-10-10', guardado: '2026-10-10T12:00:00-07:00'})];
  assert.equal(summarize(ctx, props, decisions).aprobadas, 1);
  decisions.push(decision('pieza', 'no', {quien: 'editor2', envio_id: 'e3', lamina: 1,
    fecha: '2026-10-09', guardado: '2026-10-09T12:00:00-07:00'}));
  const veto = summarize(ctx, props, decisions);
  assert.equal(veto.aprobadas, 0);
  assert.equal(veto.cambios, 1);
  assert.equal(veto.revision, 0);
});

test('pendiente no borra decisiones; borrar sí quita la marca de ese editor', () => {
  const ctx = backend();
  const props = [prop('pieza')];
  const decisions = [decision('pieza', 'si'), decision('pieza', 'pendiente', {
    envio_id: 'e2', fecha: '2026-10-10', guardado: '2026-10-10T12:00:00-07:00'})];
  assert.equal(summarize(ctx, props, decisions).aprobadas, 1);
  decisions.push(decision('pieza', 'borrar', {envio_id: 'e3', fecha: TODAY, guardado: TODAY+'T12:00:00-07:00'}));
  assert.equal(summarize(ctx, props, decisions).revision, 1);
});

test('eje elegido cierra con un sí y conserva no de opciones no elegidas', () => {
  const r = summarize(backend(), [prop('eje', {tipo: 'eje', laminas_json: '[]',
    opciones_json: '{"candidatas":["a","b","c"]}'})], [decision('eje', 'si'), decision('eje', 'no', {lamina: 1})]);
  assert.equal(r.revision, 0);
  assert.equal(r.aprobadas, 1);
  assert.equal(r.cambios, 0);
});

test('separa corte producido, publicación con enlace y registro sin enlace; deduplica piezas', () => {
  const production = [
    {fecha: '2026-10-10', pieza: 'video', estado: 'video', enlace: 'https://example.invalid/corte.mp4'},
    {fecha: TODAY, pieza: 'video', estado: 'video'},
    {fecha: TODAY, pieza: 'post', estado: 'publicada', enlace: 'https://example.invalid/post/1'},
    {fecha: TODAY, pieza: 'post', estado: 'publicada', enlace: 'https://example.invalid/post/1'},
    {fecha: TODAY, pieza: 'sin-acuse', estado: 'publicada', enlace: ''},
    {fecha: TODAY, pieza: 'no-final', estado: 'voz'}];
  const queue = [
    {id: 'q1', pieza: 'video', etapa: 'corte', estado: 'hecho'},
    {id: 'q2', pieza: 'otro', etapa: 'corte', estado: 'hecho'},
    {id: 'q3', pieza: 'otro', etapa: 'voz', estado: 'hecho'},
    {id: 'q4', estado: 'pendiente'}, {id: 'q4', estado: 'corriendo'},
    {id: 'q5', estado: 'pendiente'}, {id: 'q6', estado: 'fallo'}, {id: 'q7', estado: 'obsoleto'}];
  const r = summarize(backend(), [], [], production, queue);
  assert.equal(r.producidas, 2);
  assert.equal(r.publicadas, 1);
  assert.equal(r.sin_acuse, 1);
  assert.equal(r.en_cola, 1);
  assert.equal(r.corriendo, 1);
  assert.equal(r.fallos, 1);
});

test('fuente malformada impide confirmar conteos', () => {
  for (const call of [
    ctx => summarize(ctx, [prop('rota', {laminas_json: '{'})]),
    ctx => summarize(ctx, [prop('sin-fecha', {fecha: ''})]),
    ctx => summarize(ctx, [], [decision('pieza', 'si', {guardado: 'no-fecha'})]),
    ctx => summarize(ctx, [], [], [{pieza: 'sin-fecha'}]),
    ctx => summarize(ctx, [], [], [], [{id: 'q1', estado: 'desconocido'}])]) {
    assert.throws(() => call(backend()));
  }
});

function mailBackend(failRead = false) {
  const ctx = backend(), sent = [], events = [];
  ctx.ScriptApp = {getService: () => ({getUrl: () => 'https://example.invalid/exec'})};
  ctx.MailApp = {sendEmail: message => sent.push(message)};
  ctx.bitacora = (event, detail) => events.push({event, detail});
  ctx.hoja = name => failRead ? null : ({getLastRow: () => 1,
    getRange: () => ({getValues: () => [ctx.PESTANAS[name]]})});
  ctx.filas = name => name === 'PROPUESTAS' ? [prop('historia')] : [];
  return {ctx, sent, events};
}

test('correo conserva destinatario y entrada; incluye texto plano y estado histórico', () => {
  const {ctx, sent, events} = mailBackend();
  ctx.correoDiario();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].to, ctx.CORREO);
  assert.ok(sent[0].subject.includes('1 propuesta'));
  assert.ok(sent[0].htmlBody.includes('Publicaciones registradas con enlace: 0'));
  assert.ok(sent[0].body.includes('Propuestas pendientes de revisión: 1'));
  assert.ok(sent[0].body.includes('#gas=https%3A%2F%2Fexample.invalid%2Fexec&clave=sintetica&rol=editor'));
  const telemetry = JSON.parse(events[0].detail);
  assert.equal(telemetry.revision, 1);
  assert.ok(events[0].detail.length < 300);
  assert.ok(!events[0].detail.includes('sintetica'));
});

test('una pestaña ausente envía diagnóstico, nunca cero inventado', () => {
  const {ctx, sent, events} = mailBackend(true);
  ctx.correoDiario();
  assert.ok(sent[0].subject.includes('no se pudo confirmar'));
  assert.ok(!sent[0].body.includes('Publicaciones registradas con enlace: 0'));
  assert.equal(JSON.parse(events[0].detail).lectura, 'sin_confirmar');
});

test('un fallo al enviar no registra un correo enviado', () => {
  const {ctx, events} = mailBackend();
  ctx.MailApp.sendEmail = () => {throw new Error('fallo sintético de envío');};
  assert.throws(() => ctx.correoDiario());
  assert.equal(events.length, 0);
});

test('diagnóstico del correo sólo para agente y sin efectos', () => {
  const {ctx, sent, events} = mailBackend();
  ctx.json = data => data;
  ctx.rolDe = () => 'agente';
  const r = ctx.doGet({parameter: {recurso: 'correo_estado', clave: 'sintetica'}});
  assert.equal(r.ok, true);
  assert.equal(r.version, 'correo-historico-2026-10-15');
  assert.equal(r.resumen.revision, 1);
  for (const role of ['editor', 'editor2', 'lector']) {
    ctx.rolDe = () => role;
    assert.equal(ctx.doGet({parameter: {recurso: 'correo_estado'}}).error, 'solo el agente');
  }
  assert.equal(sent.length, 0);
  assert.equal(events.length, 0);
});
