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
  const contexto = {_porRuta:{'laminas/lote/L1.png':{prueba:'test-drive'},'laminas/lote/L1.jpg':{prueba:'test-drive-jpg'},'externa.png':{prueba:'test-drive'}},
    deDrive: id => 'https://drive.invalid/'+id};
  vm.runInNewContext(extraer('const esLaminaLocal=src=>', '/* Ampliar sí permite') +
    '\nthis.ligeraPublica = ligera;', contexto);
  assert.equal(contexto.ligeraPublica('laminas/lote/L1.png'),'laminas/lote/L1.jpg');
  assert.equal(contexto.ligeraPublica('laminas/lote/L1.jpg'),'laminas/lote/L1.jpg'); // no Drive
  assert.equal(contexto.ligeraPublica('externa.png'),'https://drive.invalid/test-drive');
});
test('la lectura secundaria arranca después de pintar la mesa', () => {
  assert.match(html, /if\(_pintado&&d\) cargarSecundarios\(\)/);
  const inicio=extraer('(async function(){', "  // Catálogo y vistas auxiliares se cargan");
  assert.doesNotMatch(inicio, /_expP=cargarExpedientes\(\)/);
  assert.doesNotMatch(inicio, /traerCatalogo\(\)/);
  assert.doesNotMatch(inicio, /traerCola\(\)/);
});

test('ninguna solicitud secundaria o comprobación de versión arranca antes de Hoy', () => {
  assert.doesNotMatch(html, /setTimeout\(actualizarLineaHoy,2500\)/);
  assert.doesNotMatch(html, /setTimeout\(vigilarVersion,4000\)/);
  const inicio = extraer('(async function(){', '  // Catálogo y vistas auxiliares se cargan');
  assert.doesNotMatch(inicio, /traerCatalogo\(\)|traerCola\(\)|cargarExpedientes\(\)/);
  const secundarios = extraer('function cargarSecundarios(){', 'function pintarFecha(');
  assert.match(secundarios, /setTimeout\(vigilarVersion,9500\)/);
  assert.match(secundarios, /setTimeout\(\(\)=>\{/);
  assert.match(html, /if\(_pintado&&document\.body\.dataset\.vista==='hoy'\)/);
});

test('un fallo de JPG intenta alternativa y ofrece un botón real para reintentar', () => {
  const contexto = {
    _porRuta:{'laminas/test/L1.jpg':{prueba:'nube'}},
    deDrive: id => 'https://drive.invalid/'+id
  };
  const codigo=extraer('const esLaminaLocal=src=>','/* El serial visible:')+
    '\n'+extraer('function montarImagen(', 'function dobleToque(')+
    '\nthis.montar=montarImagen;';
  vm.runInNewContext(codigo,contexto);
  const botones={},clases=new Set(),img={
    classList:{add:x=>clases.add(x),remove:x=>clases.delete(x)},
    naturalWidth:0,complete:false,src:''
  };
  const cargando={
    textContent:'cargando...',innerHTML:'',
    querySelector:s=>s==='button'?botones:null,
    remove(){ this.retirado=true }
  };
  const el={querySelector:s=>s==='.lienzo > img'?img:s==='.lienzo .cargando'?cargando:null};
  contexto.montar(el,'laminas/test/L1.jpg',true);
  assert.equal(img.src,'laminas/test/L1.jpg');
  assert.equal(img.fetchPriority,'high');
  img.onerror();
  assert.equal(img.src,'https://drive.invalid/nube');
  img.onerror();
  assert.match(cargando.innerHTML,/Reintentar imagen/);
  assert.equal(typeof botones.onclick,'function');
  botones.onclick({stopPropagation(){}});
  assert.match(img.src,/^laminas\/test\/L1\.jpg\?recarga=\d+$/);
  img.onload();
  assert.equal(cargando.retirado,true);
  assert.equal(clases.has('lista'),true);
});
test('el catálogo no recrea la foto principal ni la cambia a Drive', () => {
  const codigo=extraer('async function traerCatalogo(){','/* La liga de Drive');
  assert.doesNotMatch(codigo,/pintarCartas\(\)/);
  assert.match(codigo,/querySelectorAll\('\.carta\[data-k\]'\)/);
  const resolucion=extraer('const esLaminaLocal=src=>','/* El serial visible:');
  assert.match(resolucion,/if\(esLaminaLocal\(src\)\)/);
});
test('el móvil abre zoom a un toque, con JPG de Pages y original bajo demanda', () => {
  assert.match(html,/querySelector\('\.lienzo > img'\)\.onclick/);
  const zoom=extraer('function abrirZoom(src){','\/\* ══ final \/ vacío ══ \*\/');
  assert.match(zoom,/const vista=ligera\(src\),alta=original\(src\)/);
  assert.match(zoom,/img\.src=vista/);
  assert.match(zoom,/Original HD/);
});
test('tiras y consultas auxiliares esperan a la primera imagen', () => {
  const montar=extraer('function montar(d){','\/\* ══ el alto de la carta');
  assert.match(montar,/trasPrimeraFoto\(\(\)=>\{/);
  const secundarios=extraer('function cargarSecundarios(){','function pintarFecha(');
  assert.match(secundarios,/trasPrimeraFoto\(\(\)=>\{/);
  assert.match(html,/img\.addEventListener\('load',terminar,\{once:true\}\)/);
});
