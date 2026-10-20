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
    deDrive: id => 'https://drive.invalid/'+id,SalaMedios:{vista:(src,ruta)=>ruta}};
  vm.runInNewContext(extraer('const ligera=src=>{', '/* Ampliar sí pide') +
    '\nthis.ligeraPublica = ligera;', contexto);
  assert.equal(contexto.ligeraPublica('laminas/lote/L1.png'),'laminas/lote/L1.jpg');
  assert.equal(contexto.ligeraPublica('laminas/lote/L1.jpg'),'laminas/lote/L1.jpg');
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

test('al llegar el catálogo se actualiza el serial sin reemplazar la JPG ya cargada', () => {
  const segmento=extraer('async function traerCatalogo(){','/* La liga de Drive');
  assert.doesNotMatch(segmento, /pintarCartas\(\)/);
  assert.match(segmento, /querySelectorAll\('\.carta\[data-k\]'\)/);
  assert.match(segmento, /etiqueta\.textContent=serial/);
});
test('consultas secundarias dan prioridad limitada a la primera foto', () => {
  const secundarios=extraer('function cargarSecundarios(){','function pintarFecha(');
  assert.match(secundarios,/principal\.addEventListener\('load',adelante,\{once:true\}\)/);
  assert.match(secundarios,/principal\.addEventListener\('error',adelante,\{once:true\}\)/);
  assert.match(secundarios,/setTimeout\(adelante,2000\)/);
});

test('vista vacía de visitante no da por decididas las tarjetas de los editores ni anuncia trabajo sin cola',()=>{
  const nodes=new Map(),get=s=>{if(!nodes.has(s))nodes.set(s,{textContent:'',innerHTML:'',hidden:false});return nodes.get(s)};
  const data={quien:'',_todas:[{id:'synthetic',laminas:['a.jpg','b.jpg','c.jpg']}],decisiones:{propuestas:{}}};
  const ctx={$:get,D:data,PZ:{synthetic:{pieza:'Sintética',estado:'en camino',etapa:'copy'}},COLA:[],lockeadas:[],
    DECIDE:()=>false,pintarCtx(){},pintarPanel(){},ICO_CHECK:'',fetch(){throw Error('sin red')},subir(){throw Error('sin escrituras')}};
  const before=JSON.stringify({D:ctx.D,PZ:ctx.PZ});
  vm.runInNewContext(extraer('function pintarVacio(){','/* ══ vista de solo lectura:')+'\npintarVacio();',ctx);
  assert.equal(get('#titulo').textContent,'Vista de consulta');
  assert.match(get('#zona').innerHTML,/Estás viendo la Sala como visitante/);
  assert.match(get('#zona').innerHTML,/Las decisiones corresponden a los editores/);
  assert.doesNotMatch(get('#zona').innerHTML,/Todo decidido|Producción trabaja|Cuando necesite tu decisión/);
  assert.equal(JSON.stringify({D:ctx.D,PZ:ctx.PZ}),before);
  assert.equal(get('#mandoWrap').hidden,true);
  assert.match(get('#zona').innerHTML,/onclick="irVista\('pub'\)"/);
});

test('vista vacía distingue cuenta editora y cuenta de consulta sin cambiar sus acciones',()=>{
  for(const editora of [true,false]){
    const nodes=new Map(),get=s=>{if(!nodes.has(s))nodes.set(s,{});return nodes.get(s)};
    const ctx={$:get,D:{quien:'Cuenta sintética'},PZ:{},lockeadas:[],DECIDE:()=>editora,
      pintarCtx(){},pintarPanel(){},ICO_CHECK:''};
    vm.runInNewContext(extraer('function pintarVacio(){','/* ══ vista de solo lectura:')+'\npintarVacio();',ctx);
    assert.equal(get('#titulo').textContent,editora?'Sin tarjetas por responder para ti':'Vista de consulta');
    assert.match(get('#zona').innerHTML,editora?/para tu cuenta en esta vista/:/Tu cuenta tiene acceso de consulta/);
    assert.doesNotMatch(get('#zona').innerHTML,/Todo decidido|Producción trabaja|onclick=/);
    assert.equal(get('#mandoWrap').hidden,true);
  }
});

test('sin identidad confirmada tampoco se atribuye un turno a un rol editor local',()=>{
  const nodes=new Map(),get=s=>{if(!nodes.has(s))nodes.set(s,{});return nodes.get(s)};
  const ctx={$:get,D:null,PZ:{},lockeadas:[],DECIDE:()=>true,pintarCtx(){},pintarPanel(){},ICO_CHECK:''};
  vm.runInNewContext(extraer('function pintarVacio(){','/* ══ vista de solo lectura:')+'\npintarVacio();',ctx);
  assert.equal(get('#titulo').textContent,'Vista de consulta');
  assert.match(get('#zona').innerHTML,/Estás viendo la Sala como visitante/);
  assert.doesNotMatch(get('#zona').innerHTML,/Todo decidido|Producción trabaja|No hay tarjetas por responder para tu cuenta/);
});

{
/* Estados que ve el editor: consumidor real, datos sintéticos y ninguna escritura. */
const test=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const html=fs.readFileSync('index.html','utf8');
function block(start,end){
  const a=html.indexOf(start),b=html.indexOf(end,a+start.length);
  assert.ok(a>=0&&b>a,'falta consumidor '+start);
  return html.slice(a,b);
}
function sala(){
  const surface={innerHTML:'',querySelectorAll:()=>[]};
  const ctx=vm.createContext({D:{propuestas:[],decisiones:{propuestas:{}}},dec:{},pasos:[],TIRAS:{},PZ:{},
    COLA:[],FABRICA:[],IDEAS:[],ARRANQUE:{},EXP:{cargado:true},publicadas:new Set(),
    $:()=>surface,esc:s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
    ligera:x=>x,fuenteLamina:(l,src)=>src,CANDIDATAS:p=>p.opciones?.candidatas||[],mapaDe:t=>t.mapa||{'1':1},
    fetch:()=>{throw Error('el estado cargado no necesita red')},
    proximaCorrida:()=>{throw Error('no prometer horarios sin trabajo confirmado')},
    estimaFabrica:()=>{throw Error('no estimar una etapa genérica')},
    COLA_DE_ETAPA:{laminas:'prospectos',voz:'voz',escenas:'escena',corte:'corte'},HORAS_ATORADO:3,
    NOM_COLA:{prospectos:'las candidatas de lámina',voz:'la voz',escena:'la escena',corte:'el corte'}});
  ctx.esPublicada=nombre=>ctx.publicadas.has(nombre);
  ctx.nomCola=e=>ctx.NOM_COLA[e]||e;
  for(const source of [
    block('function normSlug(s){','// una lámina puede tener'),
    block('function ejeEligioLamina(l){','function evidenciaSrc(f){'),
    block('function quefaltaPara(t,g,publicada){','async function pintarProduccion(){'),
    block('function edadHoras(txt){','function filaLinea(z){'),
    block('const ETAPAS = {','/* el anillo:'),
    block('function hechasDe(z,publicada){','function frutoPub(c){'),
    block('function filaLinea(z){','function enganchaLinea(c){')
  ]) vm.runInContext(source,ctx);
  ctx.enganchaLinea=()=>{};
  function piece(rows={},approved=true){
    const tira={pieza:'Pieza sintética',pieza_slug:'synthetic',laminas:[{n:1,src:'synthetic.jpg',estado:approved?'aprobada':'pendiente'}]};
    ctx.TIRAS={'synthetic-v1':tira};
    return {slug:'synthetic',nombre:'Pieza sintética',tira,filas:{prospectos:[],voz:[],escena:[],corte:[],...rows}};
  }
  async function render(z){
    await ctx.pintarLinea([z],'linea',true);
    return surface.innerHTML;
  }
  return {ctx,piece,render};
}

test('lámina aprobada sin trabajo en cola pide confirmar texto, sin promesa de producción',async()=>{
  const s=sala(),z=s.piece(),before=JSON.stringify(z),rendered=await s.render(z);
  assert.match(rendered,/Texto de publicación por confirmar/);
  assert.doesNotMatch(rendered,/Productor lo pone|≈|hace después|próxima ronda/);
  assert.equal(s.ctx.filaLinea(z).fab,false);
  assert.equal(JSON.stringify(z),before);
});

test('una publicación registrada no vuelve a pedir publicarla ni cuenta como abierta',async()=>{
  const s=sala(),z=s.piece();s.ctx.publicadas.add(z.nombre);
  assert.equal(s.ctx.filaLinea(z).que,'Publicación registrada.');
  const rendered=await s.render(z);
  assert.match(rendered,/No hay publicaciones abiertas/);
  assert.doesNotMatch(rendered,/Falta publicarla|pone en cola|≈/);
});

test('sin tarjeta actual no inventa una decisión de hoy ni una próxima ronda',async()=>{
  const s=sala(),rendered=await s.render(s.piece({},false));
  assert.match(rendered,/No hay una tarjeta por responder de esta pieza en la mesa actual/);
  assert.doesNotMatch(rendered,/Hoy ya decidiste|próxima ronda|≈/);
});

test('un trabajo pendiente real muestra cola sin atribuirle copy ni una hora garantizada',async()=>{
  const s=sala(),z=s.piece({voz:[{id:'q1',etapa:'voz',estado:'pendiente'}]}),rendered=await s.render(z);
  assert.match(rendered,/1 trabajo en cola/);
  assert.match(rendered,/Inicio pendiente de confirmar/);
  assert.equal(s.ctx.filaLinea(z).fab,true);
  assert.doesNotMatch(rendered,/trabajo de copy|pone en cola|≈|revísalo/);
});

test('un trabajo en curso conserva su etapa y no promete una terminación sin recibo',async()=>{
  const s=sala(),now=new Date(Date.now()-7*3600000).toISOString().slice(0,19);
  const z=s.piece({voz:[{id:'q1',etapa:'voz',estado:'corriendo',actualizado:now}]}),rendered=await s.render(z);
  assert.match(rendered,/En proceso: voz \(1 trabajo\)/);
  assert.match(rendered,/Finalización pendiente de confirmar/);
  assert.equal(s.ctx.filaLinea(z).fab,true);
  assert.doesNotMatch(rendered,/≈|pone en cola|Lo próximo de la fábrica/);
});

test('voz, escena y corte hechos no se presentan como producción todavía activa',async()=>{
  const s=sala(),z=s.piece(Object.fromEntries(['voz','escena','corte'].map(etapa=>[etapa,[{id:etapa,etapa,estado:'hecho'}]])));
  const rendered=await s.render(z);
  assert.match(rendered,/Texto de publicación por confirmar/);
  assert.doesNotMatch(rendered,/En proceso:|trabajo en cola|pone en cola|≈/);
  assert.equal(s.ctx.filaLinea(z).fab,false);
});

}

test('día: máximo dos peticiones, incluso con topes explícitos y varias credenciales',async()=>{
 for(const rejected of [false,true]){
  let calls=0;const delays=[];
  const ctx={window:{},performance,AbortController,AbortSignal,encodeURIComponent,Date,JSON,
   _llaveViva:null,_mesaLocal:false,ENTRADO:()=>true,LLAVES:()=>['a','b','c'],GAS:()=> 'https://synthetic.invalid',
   cargarMediosSinBloquear(){},leerJSON:r=>r.json(),
   setTimeout:(fn,ms)=>{delays.push(ms);return setTimeout(fn,Math.min(ms,1));},clearTimeout,
   fetch:async()=>{calls++;if(rejected)return {ok:true,json:async()=>({error:'clave incorrecta'})};throw Error('red');}};
  vm.runInNewContext(extraer("let _ultimoErrorLlave='';",'async function conMarcasDeAntes')+'\nthis.run=traer;',ctx);
  await assert.rejects(()=>ctx.run('',99,60000,true));
  assert.equal(calls,2);assert.deepEqual(delays,[8000,400,8000]);
 }
});
test('el timeout del día incluye la descarga del cuerpo JSON',async()=>{
 let aborted=false;
 const ctx={window:{},performance,AbortController,AbortSignal,encodeURIComponent,Date,JSON,
  _llaveViva:null,_mesaLocal:false,ENTRADO:()=>true,LLAVES:()=>['synthetic'],GAS:()=> 'https://synthetic.invalid',
  cargarMediosSinBloquear(){},leerJSON:r=>r.json(),setTimeout:(fn)=>setTimeout(fn,2),clearTimeout,
  fetch:async(url,{signal})=>({ok:true,json:()=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>{aborted=true;reject(Error('abort'));}))})};
 vm.runInNewContext(extraer("let _ultimoErrorLlave='';",'async function conMarcasDeAntes')+'\nthis.run=traer;',ctx);
 await assert.rejects(()=>ctx.run('',1,8000,true));assert.equal(aborted,true);
 assert.equal(ctx.window.SalaRendimiento[0].resultado,'timeout');
});
