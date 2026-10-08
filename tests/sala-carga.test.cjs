/* Pruebas aisladas del arranque de Sala: sin credenciales, red ni Google Sheets. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('index.html', 'utf8');
function extraer(inicio, fin) {
  const a = html.indexOf(inicio);
  assert.ok(a >= 0, 'falta ' + inicio);
  const b = html.indexOf(fin, a + inicio.length);
  assert.ok(b > a, 'falta cierre para ' + inicio);
  return html.slice(a, b);
}
function prepararHerencia(traer) {
  const contexto = { traer, etapaCarga: () => {} };
  vm.runInNewContext(extraer('async function conMarcasDeAntes(', 'function normalizarDia(') +
    '\nthis.reconciliar = conMarcasDeAntes;', contexto);
  return contexto.reconciliar;
}
test('el GAS moderno evita todas las consultas históricas redundantes', async () => {
  let consultas = 0;
  const revisar = prepararHerencia(async () => { consultas++; throw Error('no debe pedir más días'); });
  const d = {fecha:'2026-10-08',propuestas:[{id:'nueva',de_antes:null},{id:'relevo',de_antes:'2026-10-07'}],
    decisiones:{propuestas:{relevo:{laminas:['si'],heredada:'2026-10-07'}},editores:['Editor']}};
  assert.equal(await revisar(d,''), d);
  assert.equal(consultas, 0);
  assert.deepEqual(d.decisiones.editores, ['Editor']);
});
test('para un GAS antiguo se rescatan las marcas sin perder los demás campos', async () => {
  const fechas = [];
  const revisar = prepararHerencia(async f => {
    fechas.push(f);
    return {decisiones:{propuestas:{vieja:{laminas:['no'],notas:['Cambiar']}}}};
  });
  const d = {fecha:'2026-10-08',dias:['2026-10-07'],propuestas:[{id:'vieja'}],
    decisiones:{editores:['Editor'],nota_general:'Conservar',propuestas:{}}};
  const j = await revisar(d, '');
  assert.equal(fechas.length, 1);
  assert.equal(j.decisiones.propuestas.vieja.laminas[0], 'no');
  assert.equal(j.decisiones.nota_general, 'Conservar');
  assert.deepEqual(j.decisiones.editores, ['Editor']);
});
test('una portada del repo prefiere JPG ligera aunque el catálogo ofrezca Drive', () => {
  const contexto = {_porRuta:{'laminas/lote/L1.png':{prueba:'test-drive'},'externa.png':{prueba:'test-drive'}},
    deDrive: id => 'https://drive.invalid/'+id};
  vm.runInNewContext(extraer('const ligera=src=>{', '/* Ampliar sí pide') +
    '\nthis.ligeraPublica = ligera;', contexto);
  assert.equal(contexto.ligeraPublica('laminas/lote/L1.png'),'laminas/lote/L1.jpg');
  assert.equal(contexto.ligeraPublica('externa.png'),'https://drive.invalid/test-drive');
});
test('la lectura secundaria arranca después de pintar la mesa', () => {
  assert.match(html, /if\(_pintado&&d\) cargarSecundarios\(\)/);
  const inicio=extraer('(async function(){', "  // Catálogo y vistas auxiliares se cargan");
  assert.doesNotMatch(inicio, /_expP=cargarExpedientes\(\)/);
  assert.doesNotMatch(inicio, /traerCatalogo\(\)/);
  assert.doesNotMatch(inicio, /traerCola\(\)/);
});
