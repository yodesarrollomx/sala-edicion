const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../gas/Code.gs'), 'utf8');
const day = '2026-10-15';
const plain = x => JSON.parse(JSON.stringify(x));
function backend() {
  const ctx = vm.createContext({});
  vm.runInContext(source, ctx);
  const names = {nombre_editor: 'Uno', nombre_editor2: 'Dos'};
  const reads = [];
  ctx.leerConfig = key => { reads.push(key); return names[key] || ''; };
  ctx.hoja = () => { throw Error('No se permiten escrituras ni otras lecturas'); };
  return {ctx, names, reads};
}
function row(id, role, mark = 'si', extra = {}) {
  return {fecha: day, guardado: day + 'T12:00:00-07:00', envio_id: id + role,
    prop_id: id, quien: role, lamina: 0, marca: mark, nota_propuesta: '', ...extra};
}
for (const method of ['fusionDia_', 'fusionProduccion_']) {
  const run = (ctx, rows) => { const r = ctx[method](rows, day); return method === 'fusionDia_' ? r.dec : r; };
  test(method + ': 240 firmas, dos lecturas, 120 vetos y notas conservadas', () => {
    const {ctx, reads} = backend();
    const rows = Array.from({length:120}, (_, i) => [
      row('p' + i, 'editor', 'si', {nota_propuesta:'Nota uno'}),
      row('p' + i, 'editor2', 'no', {nota_propuesta:'Nota dos'})]).flat();
    const before = JSON.stringify(rows);
    const dec = plain(run(ctx, rows));
    assert.equal(Object.keys(dec.propuestas).length, 120);
    for (const p of Object.values(dec.propuestas)) {
      assert.deepEqual(p.laminas, ['no']);
      assert.equal(p.firmas[0].length, 2);
      assert.match(p.notas[0], /Uno: Nota uno/);
      assert.match(p.notas[0], /Dos: Nota dos/);
    }
    assert.deepEqual(reads.sort(), ['nombre_editor', 'nombre_editor2']);
    assert.equal(JSON.stringify(rows), before);
  });
  test(method + ': nombres frescos en cada invocación, sin cachear identidades', () => {
    const {ctx, names, reads} = backend();
    const rows = [row('p', 'editor')];
    assert.deepEqual(plain(run(ctx, rows).editores), ['Uno']);
    names.nombre_editor = 'Nombre actualizado';
    assert.deepEqual(plain(run(ctx, rows).editores), ['Nombre actualizado']);
    assert.equal(reads.length, 2);
    ctx[method]([], day);
    assert.equal(reads.length, 2);
  });
  test(method + ': pendiente conserva y borrar revoca sólo la firma propia', () => {
    const {ctx} = backend();
    const rows = [row('p','editor','si'), row('p','editor2','no'),
      row('p','editor','pendiente',{envio_id:'pendiente',guardado:day+'T13:00:00-07:00'})];
    assert.deepEqual(plain(run(ctx, rows).propuestas.p.laminas), ['no']);
    rows.push(row('p','editor2','borrar',{envio_id:'borrar',guardado:day+'T14:00:00-07:00'}));
    assert.deepEqual(plain(run(ctx, rows).propuestas.p.laminas), ['si']);
  });
}
