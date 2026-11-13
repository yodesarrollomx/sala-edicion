// Roast Room (7-nov-2026): el GAS acepta la firma del consejo y la marca humana manda sobre ella.
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

const TODAY = '2026-11-07';
function backend(config = {}) {
  const ctx = vm.createContext({});
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../gas/Code.gs'), 'utf8'), ctx);
  const base = {nombre_editor: 'Alejandro', nombre_editor2: 'Sayri', clave: 'k-editor', clave_editor2: 'k-sayri',
    clave_lector: 'k-lector', clave_agente: 'k-agente', ...config};
  ctx.leerConfig = k => base[k] || '';
  ctx.hoy = () => TODAY;
  ctx.rolPorGracia_ = () => null;
  ctx.rolPorPortero_ = () => null;
  return ctx;
}
const clone = value => JSON.parse(JSON.stringify(value));
function card(more = {}) {
  return {prop_id: 'pieza', fecha: TODAY, titulo: 'Sintética', tipo: 'laminas',
    laminas_json: '["a.jpg","b.jpg"]', opciones_json: '[]', estado: 'en revisión', origen: '', ...more};
}
function mark(quien, lamina, marca, guardado, more = {}) {
  return {prop_id: 'pieza', fecha: TODAY, guardado, envio_id: quien + '-' + guardado, quien, lamina, marca,
    nota_propuesta: '', ...more};
}

test('la llave del consejo da el rol consejo y sólo si existe en CONFIG', () => {
  assert.equal(backend({clave_consejo: 'k-roast'}).rolDe('k-roast'), 'consejo');
  assert.equal(backend().rolDe(''), null);
  assert.equal(backend().rolDe('k-roast'), null);
  assert.equal(backend({clave_consejo: 'k-roast'}).nombreDe('consejo'), 'Roast Room');
});

test('producción: el sí del consejo aprueba donde ningún humano marcó', () => {
  const r = clone(backend().produccionHistorica_(TODAY, [card()], [
    mark('consejo', 0, 'si', '2026-11-07T10:00:00-07:00'),
    mark('consejo', 1, 'no', '2026-11-07T10:00:00-07:00', {nota_propuesta: '2 de 6 a favor'})]));
  assert.deepEqual(r.decisiones.propuestas.pieza.laminas, ['si', 'no']);
  assert.equal(r.decisiones.propuestas.pieza.firmas[0][0].quien, 'Roast Room');
  assert.equal(r.decisiones.propuestas.pieza.humana, undefined);
});

test('producción: el no de Alejandro manda sobre el sí del consejo, y el sí de Sayri sobre su no', () => {
  const r = clone(backend().produccionHistorica_(TODAY, [card()], [
    mark('consejo', 0, 'si', '2026-11-07T10:00:00-07:00'),
    mark('editor', 0, 'no', '2026-11-07T09:00:00-07:00', {nota_propuesta: 'no va'}),
    mark('consejo', 1, 'no', '2026-11-07T10:00:00-07:00', {nota_propuesta: '3 de 6'}),
    mark('editor2', 1, 'si', '2026-11-07T11:00:00-07:00')]));
  assert.deepEqual(r.decisiones.propuestas.pieza.laminas, ['no', 'si']);
  assert.equal(r.decisiones.propuestas.pieza.firmas[0].length, 2);
});

test('mesa del día: misma precedencia que producción', () => {
  const ctx = backend();
  const DE = [
    mark('consejo', 0, 'no', '2026-11-07T10:00:00-07:00', {nota_propuesta: '3 de 6'}),
    mark('editor', 0, 'si', '2026-11-07T11:00:00-07:00'),
    mark('consejo', 1, 'si', '2026-11-07T10:00:00-07:00')];
  const dec = clone(ctx.fusionDia_(DE, TODAY).dec);
  assert.deepEqual(dec.propuestas.pieza.laminas, ['si', 'si']);
  assert.equal(dec.propuestas.pieza.humana, undefined);
});

test('un rol desconocido sigue rompiendo el contrato de producción', () => {
  assert.throws(() => backend().produccionHistorica_(TODAY, [card()], [
    mark('agente', 0, 'si', '2026-11-07T10:00:00-07:00')]));
});
