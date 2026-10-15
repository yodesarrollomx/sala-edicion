const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
for (const name of ['node:http', 'node:https']) {
  const transport = require(name);
  transport.request = transport.get = () => { throw Error('red prohibida en fixtures sintéticas'); };
}
global.fetch = () => { throw Error('red prohibida en fixtures sintéticas'); };

const TODAY = '2026-10-15';
function backend() {
  const ctx = vm.createContext({});
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../gas/Code.gs'), 'utf8'), ctx);
  ctx.leerConfig = k => ({nombre_editor: 'Uno', nombre_editor2: 'Dos'}[k] || '');
  ctx.hoy = () => TODAY;
  return ctx;
}
const clone = value => JSON.parse(JSON.stringify(value));
function card(id = 'historia', more = {}) {
  return {prop_id: id, fecha: '2026-08-01', titulo: 'Sintética', tipo: 'laminas',
    laminas_json: '["imagen.jpg"]', opciones_json: '[]', estado: 'en revisión', origen: '', ...more};
}
function mark(marca = 'si', more = {}) {
  return {prop_id: 'historia', fecha: '2026-08-01', guardado: '2026-08-01T12:00:00-07:00',
    envio_id: 'sobre', quien: 'editor', lamina: 0, marca, nota_propuesta: '', ...more};
}
function read(props, decisions) { return clone(backend().produccionHistorica_(TODAY, props, decisions)); }

test('fuente antigua y marcas de más de14d son lectura canónica, sin inventar fecha actual', () => {
  const r = read([card()], [mark()]);
  assert.equal(r.contrato, 'produccion-historica-v1');
  assert.equal(r.alcance, 'historial_completo');
  assert.equal(r.propuestas[0].fecha_fuente, '2026-08-01');
  assert.deepEqual(r.decisiones.propuestas.historia.laminas, ['si']);
  assert.equal(r.decisiones.propuestas.historia.firmas[0][0].guardado, '2026-08-01T19:00:00.000Z');
});

test('última fila de la fuente manda y retirada no revive copia anterior', () => {
  const r = read([card(), card('historia', {fecha: '2026-09-01', estado: 'retirada'}),
    card('otra', {fecha: '2026-09-10'}), card('otra', {fecha: '2026-08-01'})], []);
  assert.deepEqual(r.propuestas.map(x => x.id), ['otra']);
  assert.equal(r.propuestas[0].fecha_fuente, '2026-09-10');
  assert.equal(r.fuentes.retiradas, 1);
});

test('retirada por origen y propuesta futura no se hacen fuentes activas', () => {
  const r = read([card('origen', {origen: 'retirada · cambio explícito'}),
    card('futura', {fecha: '2027-01-01'})], []);
  assert.deepEqual(r.propuestas, []);
  assert.equal(r.fuentes.retiradas, 1);
});

test('recencia usa guardado verdadero de cada fila aunque fecha y envio_id sean antiguos', () => {
  const r = read([card()], [
    mark('si', {envio_id: 'reutilizado'}),
    mark('si', {envio_id: 'reutilizado', lamina: 1, guardado: '2026-10-10T12:00:00-07:00'}),
    mark('no', {envio_id: 'otro', fecha: '2026-07-01', guardado: '2026-09-01T12:00:00-07:00'})]);
  assert.deepEqual(r.decisiones.propuestas.historia.laminas, ['no', 'si']);
});

test('un no posterior no se pierde por recuperar sólo el sí histórico', () => {
  const r = read([card()], [mark(), mark('no', {
    fecha: '2026-10-01', guardado: '2026-10-01T09:00:00-07:00'})]);
  assert.deepEqual(r.decisiones.propuestas.historia.laminas, ['no']);
});

test('Date nativo de Sheet conserva instante real y milisegundos', () => {
  const ctx = backend();
  const native = vm.runInContext("new Date('2026-09-01T12:00:00.345-07:00')", ctx);
  const result = clone(ctx.produccionHistorica_(TODAY, [card()], [mark('si', {guardado: native})]));
  assert.equal(result.decisiones.propuestas.historia.firmas[0][0].guardado, '2026-09-01T19:00:00.345Z');
});

test('dos editores iguales: no antiguo del otro veta sí posterior y conserva notas firmadas', () => {
  const r = read([card()], [mark('no', {quien: 'editor2', nota_propuesta: 'Corrección dos'}),
    mark('si', {guardado: '2026-10-01T09:00:00-07:00', nota_propuesta: 'Elección uno'})]);
  const d = r.decisiones.propuestas.historia;
  assert.deepEqual(d.laminas, ['no']);
  assert.equal(d.firmas[0].length, 2);
  assert.deepEqual(new Set(d.firmas[0].map(x => x.rol)), new Set(['editor', 'editor2']));
  assert.match(d.notas[0], /Uno: Elección uno/);
  assert.match(d.notas[0], /Dos: Corrección dos/);
});

test('pendiente no borra; borrar explícito revoca sólo la marca de ese editor', () => {
  const pending = mark('pendiente', {guardado: '2026-10-01T12:00:00-07:00'});
  assert.deepEqual(read([card()], [mark(), pending]).decisiones.propuestas.historia.laminas, ['si']);
  const clear = mark('borrar', {guardado: '2026-10-02T12:00:00-07:00'});
  const own = read([card()], [mark(), pending, clear]).decisiones.propuestas.historia;
  assert.deepEqual(own.laminas, [null]);
  assert.equal(own.firmas[0][0].marca, null);
  const other = read([card()], [mark('no'), clear, mark('si', {quien: 'editor2'})]);
  assert.deepEqual(other.decisiones.propuestas.historia.laminas, ['si']);
});

test('empate contradictorio de sello máximo cierra, incluso nota de toma diferente', () => {
  for (const conflicting of [mark('no'), mark('si', {nota_propuesta: '[toma elegida: 2]'})]) {
    assert.throws(() => read([card()], [mark(), conflicting]), /produccion_sello_ambiguo/);
  }
  const resolved = read([card()], [mark(), mark('no'), mark('si', {guardado: '2026-09-02T12:00:00-07:00'})]);
  assert.deepEqual(resolved.decisiones.propuestas.historia.laminas, ['si']);
});

test('roles, sellos, índices o marcas imposibles cierran sin aprobar parcialmente', () => {
  for (const bad of [{quien: 'agente'}, {guardado: 'no-fecha'}, {lamina: -1}, {lamina: 1000},
    {lamina: 'x'}, {marca: 'aprobado'}, {prop_id: '../otra'}]) {
    assert.throws(() => read([card()], [mark('si', bad)]));
  }
});

test('fuente JSON rota o identidad inválida nunca se convierte en cero fuentes', () => {
  for (const bad of [{laminas_json: '{'}, {opciones_json: 'null'}, {fecha: ''}, {prop_id: '../otra'}]) {
    assert.throws(() => read([card('historia', bad)], []));
  }
});

test('lectura es estable e inmutable y no altera filas o fechas históricas', () => {
  const ctx = backend(), props = [card()], decisions = [mark()];
  const before = JSON.stringify({props, decisions});
  const first = JSON.stringify(ctx.produccionHistorica_(TODAY, props, decisions));
  const second = JSON.stringify(ctx.produccionHistorica_(TODAY, props, decisions));
  assert.equal(first, second);
  assert.equal(JSON.stringify({props, decisions}), before);
});

function endpoint(role = 'agente', badHeader = false, missing = false) {
  const ctx = backend();
  ctx.rolDe = () => role;
  ctx.json = value => clone(value);
  ctx.hoja = name => missing ? null : ({getLastRow: () => 1, getRange: () => ({
    getValues: () => [badHeader ? ['otra'] : clone(ctx.PESTANAS[name])]
  })});
  ctx.filas = name => name === 'PROPUESTAS' ? [card()] : [mark()];
  ctx.bitacora = () => { throw Error('la lectura no debe escribir'); };
  ctx.MailApp = {sendEmail: () => { throw Error('la lectura no envía correo'); }};
  return ctx;
}

test('GET producción usa rol agente existente y no concede lectura a otros roles', () => {
  assert.equal(endpoint().doGet({parameter: {recurso: 'produccion'}}).contrato, 'produccion-historica-v1');
  for (const role of ['editor', 'editor2', 'lector']) {
    assert.deepEqual(endpoint(role).doGet({parameter: {recurso: 'produccion'}}), {error: 'solo el agente'});
  }
});

test('pestaña o cabecera ausente es fallo explícito, no colección vacía', () => {
  for (const ctx of [endpoint('agente', true), endpoint('agente', false, true)]) {
    const r = ctx.doGet({parameter: {recurso: 'produccion'}});
    assert.equal(r.ok, false);
    assert.equal(r.error, 'produccion_sin_lectura_confirmada');
    assert.equal(r.propuestas, undefined);
  }
});
