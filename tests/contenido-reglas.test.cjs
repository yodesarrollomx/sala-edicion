const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function backend(extra = '') {
  const source = fs.readFileSync(path.join(__dirname, '../gas/Code.gs'), 'utf8');
  const ctx = vm.createContext({});
  vm.runInContext(source, ctx);
  ctx.reglaGas_ = () => extra;
  ctx.rolDe = () => 'agente';
  ctx.invalidarDia_ = () => {};
  ctx.hoy = () => '2026-10-01';
  ctx.claveNuevaPara_ = () => null;
  ctx.json = x => x;
  ctx.bitacora = () => { throw new Error('escribió bitácora'); };
  ctx.hoja = () => { throw new Error('accedió a hoja de negocio'); };
  return ctx;
}

test('GAS reconoce acentos, mayúsculas y palabras completas', () => {
  const ctx = backend();
  for (const value of ['HERMOSILLO', 'sonora', 'MEXICO', 'MéXiCo', 'Me\u0301xico']) {
    assert.ok(ctx.contenidoVetado_([{ titulo: `En «${value}», hoy.` }]));
  }
  assert.equal(ctx.contenidoVetado_([{ texto: 'Sonoramente cálido.' }]), '');
});

test('GAS REGLAS añade vetos sin eliminar los obligatorios', () => {
  const ctx = backend('Otra Ciudad');
  assert.ok(ctx.contenidoVetado_([{ texto: 'En otra ciudad.' }]));
  assert.ok(ctx.contenidoVetado_([{ texto: 'México' }]));
});

test('GAS conserva notas, IDs, URLs y versiones históricas', () => {
  const ctx = backend();
  const value = [{ id: 'mexico-001', laminas: ['Sonora/L1.jpg'], nota: 'Quitar México',
    origen: 'Hermosillo', versiones: [{ dice: 'México' }],
    opciones: [{ titulo: 'Un terreno', texto: 'Una posibilidad' }] }];
  const before = JSON.stringify(value);
  assert.equal(ctx.contenidoVetado_(value), '');
  assert.equal(JSON.stringify(value), before);
});

test('doPost rechaza cada lote nuevo completo antes de tocar hojas', () => {
  for (const accion of ['proponer', 'ideas', 'arbol']) {
    const ctx = backend();
    const lote = [
      { id: 'uno', titulo: 'Un terreno', opciones: [] },
      { id: 'dos', titulo: 'Otra posibilidad', opciones: [{ texto: 'En MEXICO' }] }
    ];
    const result = ctx.doPost({ postData: { contents: JSON.stringify({
      accion, clave: 'sintetica', [accion === 'proponer' ? 'propuestas' : 'filas']: lote
    }) } });
    assert.equal(result.codigo, 'contenido_vetado', accion);
    assert.ok(result.detalle.includes('opciones[0].texto'), accion);
  }
});

test('doPost conserva el recorrido válido con una hoja sintética', () => {
  const ctx = backend();
  const rows = [['fecha', 'id', 'titulo']];
  ctx.hoja = nombre => {
    assert.equal(nombre, 'PROPUESTAS');
    return { getDataRange: () => ({ getValues: () => rows }), appendRow: row => rows.push(row) };
  };
  ctx.bitacora = () => {};
  const result = ctx.doPost({ postData: { contents: JSON.stringify({
    accion: 'proponer', clave: 'sintetica', propuestas: [
      { id: 'mexico-sintetico', titulo: 'Un terreno', laminas: ['Sonora/L1.jpg'],
        opciones: [{ texto: 'Una posibilidad' }] }
    ]
  }) } });
  assert.equal(result.ok, true);
  assert.equal(rows.length, 2);
  assert.equal(rows[1][2], 'Un terreno');
});
