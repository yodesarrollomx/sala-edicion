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

/* 9-nov-2026 · Dirección: «trae glitches, no carga bien». Medido en su navegador: con el caché del Apps Script
   frío el día tarda 14 s; la Sala se rendía a los 8 s dos veces y lo listo para publicar nunca se pedía. */
test('lo listo para publicar no espera a la mesa: arranca al abrir, por su cuenta y una sola vez', () => {
  const inicio=extraer('(async function(){', "  // Catálogo y vistas auxiliares se cargan");
  assert.match(inicio, /abrirMesaPublicada\(\);\s*arrancarSalida\(\);/, 'antes de esperar al día');
  assert.ok(inicio.indexOf('arrancarSalida()')<html.slice(html.indexOf('(async function(){')).indexOf('await traer()'));
  const salida=extraer('function arrancarSalida(){','async function cargarExpedientes(){');
  assert.match(salida, /if\(_salidaArrancada\|\|!ENTRADO\(\)\|\|typeof SalaSalida==='undefined'\) return;/);
  // sólo dos lecturas de la hoja: expedientes y reglas. Catálogo, cola, fábrica e ideas siguen esperando.
  assert.deepEqual((salida.match(/\b(?:traer[A-Z]\w*|leerExpedientesHoja|cargarExpedientes)\(/g)||[]).sort(),['leerExpedientesHoja(','traerReglasSala(']);
  assert.match(fs.readFileSync('sala-salida.js','utf8'), /if\(typeof arrancarSalida==='function'\) arrancarSalida\(\);/, 'si la Sala arrancó antes de cargar el archivo, el archivo la despierta');
});

test('los expedientes se leen una vez, un fallo no se guarda como respuesta y las llaves con prefijo no son publicaciones', async () => {
  const hecho=[];
  function ctx(responder){
    const c={EXP:{},ENTRADO:()=>true,GAS:()=>'https://synthetic.invalid',CLAVE:()=>'k',encodeURIComponent,AbortSignal,SALA_TOPE_DIA_MS:30000,
      leerJSON:r=>r.json(),SalaSalida:{llegaron:s=>hecho.push(['llegaron',Object.keys(s)]),falla:()=>hecho.push(['falla']),abrirGuardada:()=>hecho.push(['guardada']),pintar:()=>{}},
      traerReglasSala:async()=>{hecho.push(['reglas'])},llamadas:0,opciones:null};
    c.fetch=async(url,o)=>{c.llamadas++;c.opciones=o;return responder(c.llamadas)};
    vm.runInNewContext(extraer('let EXP={}, METR=null, _expP=null, _expHojaP=null;','async function cargarExpedientes(){').replace('let EXP={}, METR=null, _expP=null, _expHojaP=null;','let _expHojaP=null;')+
      '\nthis.leer=leerExpedientesHoja;this.releer=releerExpedientes;this.arrancar=arrancarSalida;',c);
    return c;
  }
  const ok={ok:true,json:async()=>({ok:true,expedientes:{'Pieza':{estado:'lista'},'v4:serie:1':{x:1},'salida:plan':{orden:['Pieza']},
    'cambio:pieza':{tira:'pieza-nube-2026-11-09-abc123',ordenes:[{n:1,nota:'Más luminosa'}]}}})};
  const a=ctx(()=>ok);
  assert.equal(await a.leer(),true);assert.equal(await a.leer(),true);
  assert.equal(a.llamadas,1,'dos lectores comparten una petición');
  assert.deepEqual(Object.keys(a.EXP),['Pieza'],'ni v4: ni salida: ni cambio: entran a Publicaciones');
  assert.deepEqual(hecho.pop(),['llegaron',['salida:plan','cambio:pieza']],'el plan y las órdenes de cambio van con la salida');
  assert.ok(a.opciones&&a.opciones.signal,'la lectura tiene tope de tiempo');
  assert.equal(await a.releer(),true);assert.equal(a.llamadas,2,'Actualizar sí vuelve a preguntar');

  const b=ctx(n=>n===1?{ok:true,json:async()=>({error:'clave incorrecta'})}:ok);
  assert.equal(await b.leer(),false);assert.deepEqual(b.EXP,{});
  assert.equal(await b.leer(),true,'el fallo no quedó guardado');assert.equal(b.llamadas,2);

  hecho.length=0;
  const c=ctx(()=>{throw Error('red')});
  c.arrancar();c.arrancar();await new Promise(r=>setTimeout(r,5));
  assert.deepEqual(hecho.map(x=>x[0]).sort(),['falla','guardada','reglas'],'arranca una sola vez y avisa del fallo');
  const d=ctx(()=>ok);d.ENTRADO=()=>false;d.arrancar();assert.equal(d.llamadas,0,'sin sesión no pregunta nada');
});

test('el indicador de carga no le pone a toda la página el esqueleto de una carta', () => {
  assert.doesNotMatch(html, /html\.cargando/);
  assert.doesNotMatch(html, /documentElement\.classList\.(?:add|remove|toggle)\('cargando'/);
  assert.match(html, /html\.trayendo::before\{/);assert.match(html, /html\.trayendo #actualizando\{display:flex\}/);
  assert.match(html, /document\.documentElement\.classList\.add\('trayendo'\)/);assert.match(html, /document\.documentElement\.classList\.remove\('trayendo'\)/);
  assert.match(html, /\n\.cargando\{position:absolute;inset:0;display:grid;/, 'el esqueleto de carta sigue existiendo, con su nombre');
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
  ctx.DECIDE=()=>true;
  vm.runInContext(fs.readFileSync('sala-salida.js','utf8'),ctx);   // la salida real: estado y paquete de cada pieza
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

test('lámina aprobada sin paquete dice que falta su texto, sin prometer cuándo',async()=>{
  const s=sala(),z=s.piece(),before=JSON.stringify(z),rendered=await s.render(z);
  assert.match(rendered,/Imágenes aprobadas\. Falta su texto\./);
  assert.match(rendered,/Es el paso del consejo/);
  assert.doesNotMatch(rendered,/Productor lo pone|≈|hace después|próxima ronda|próxima sesión|\d+:\d\d/);
  assert.equal(s.ctx.filaLinea(z).fab,false);
  assert.equal(s.ctx.filaLinea(z).sal,'texto');
  assert.equal(JSON.stringify(z),before);
});

test('con el paquete hecho la pieza es de Dirección: «lista», va primero y no apura a publicar',async()=>{
  const s=sala(),z=s.piece();
  s.ctx.EXP[z.nombre]={estado:'lista',paquete:{orden:1,imagenes:[{n:1,src:'synthetic.png'}]}};
  const f=s.ctx.filaLinea(z),rendered=await s.render(z);
  assert.deepEqual([f.lista,f.tuyo,f.quien,f.paso],[true,true,'lista',null]);
  assert.match(f.que,/^Lista para lanzar: 1 imagen y su texto\.$/);assert.equal(f.cuando,'Toca para abrirla.');
  assert.match(rendered,/data-lista="1"/);assert.match(rendered,/<span class="quien lista">lista<\/span>/);
  assert.doesNotMatch(rendered,/publícala|Publicar →|Toca para publicarla/i,'Dirección junta montón antes de lanzar (9-nov)');
  assert.match(rendered,/1 está lista para lanzar/);
  assert.deepEqual([...f.segs.map(x=>x.c)],['hecho','hecho','hecho','tu']);
});

test('el avance nunca pasa de 100 %: sólo cuentan las etapas de la línea de esa pieza',async()=>{
  // nació para video y hoy camina como carrusel: conserva voz, escena y corte hechos
  const s=sala(),z=s.piece(Object.fromEntries(['voz','escena','corte'].map(etapa=>[etapa,[{id:etapa,etapa,estado:'hecho'}]])));
  s.ctx.EXP[z.nombre]={estado:'lista',paquete:{orden:1,imagenes:[{n:1,src:'synthetic.png'}]}};
  vm.runInContext("REGLAS_SALA={nube_ejecuta_etapas:'prospecto'}",s.ctx);   // video en pausa: la línea es de 4 etapas
  const f=s.ctx.filaLinea(z);
  assert.equal(f.segs.length,4);
  assert.equal(f.pct,75,'guion, imágenes y texto hechos; falta salir (antes decía 150)');
  assert.equal(f.pct,Math.round(100*f.segs.filter(x=>x.c==='hecho').length/f.segs.length));
});

test('en «Cómo va» lo listo sigue el orden de salida de los editores, no el de llegada a Drive',async()=>{
  const s=sala();
  const pieza=(nombre,slug,orden)=>{const z=s.piece();const tira={...z.tira,pieza:nombre,pieza_slug:slug};
    s.ctx.EXP[nombre]={estado:'lista',paquete:{orden,imagenes:[{n:1,src:slug+'.png'}]}};return {...z,slug,nombre,tira};};
  const a=pieza('Pieza A','a',1),b=pieza('Pieza B','b',2),c=pieza('Pieza C','c',3);
  const linea=s.ctx.$('#linea');
  s.ctx.$=sel=>sel==='#salidaHoy'?null:linea;s.ctx.ENTRADO=()=>true;   // aquí sólo se mira la Línea: el montón no tiene dónde pintarse
  const orden=async()=>{await s.ctx.pintarLinea([a,b,c],'linea',true);return [...linea.innerHTML.matchAll(/data-pieza="([^"]+)"/g)].map(m=>m[1]);};
  assert.deepEqual(await orden(),['Pieza A','Pieza B','Pieza C']);
  s.ctx.SalaSalida.llegaron({'salida:plan':{orden:['Pieza C','Pieza A','Pieza B']}});
  await new Promise(r=>setTimeout(r,5));
  assert.deepEqual(await orden(),['Pieza C','Pieza A','Pieza B']);
});

test('una pieza lista con cambio pedido sale del montón y «Cómo va» dice que se está rehaciendo',async()=>{
  const s=sala(),z=s.piece();
  s.ctx.EXP[z.nombre]={estado:'lista',paquete:{orden:1,id:'synthetic-v1',slug:'synthetic',imagenes:[{n:1,src:'synthetic.png'}]}};
  const linea=s.ctx.$('#linea');
  s.ctx.$=sel=>sel==='#salidaHoy'?null:linea;s.ctx.ENTRADO=()=>true;
  assert.equal(s.ctx.filaLinea(z).lista,true);
  // la orden es para OTRA versión de la pieza (la mesa ya la rehízo): no cuenta
  s.ctx.SalaSalida.llegaron({'cambio:synthetic':{tira:'synthetic-v0',ordenes:[{n:1,nota:'Más luminosa'}]}});
  assert.equal(s.ctx.filaLinea(z).lista,true);
  assert.deepEqual([...s.ctx.SalaSalida.pendientes().map(x=>x.nombre)],['Pieza sintética']);
  // la orden es para ESTA versión: deja de estar lista, pasa a la fábrica y ya no se cuenta en el montón
  s.ctx.SalaSalida.llegaron({'cambio:synthetic':{tira:'synthetic-v1',ordenes:[{n:1,nota:'Más luminosa'}]}});
  const f=s.ctx.filaLinea(z);
  assert.deepEqual([f.lista,f.tuyo,f.quien],[false,false,'fab']);
  assert.equal(f.que,'Cambio pedido en la imagen 1, con la nota del editor.');
  assert.equal(f.cuando,'Suele tardar varias horas; cuando esté lista llega a la mesa para aprobarla.');
  assert.equal(s.ctx.SalaSalida.pendientes().length,0);
  // sin mesa que confirme la versión no se ofrece «quitar» (quitable:false)
  assert.deepEqual(JSON.parse(JSON.stringify(s.ctx.SalaSalida.enCambio())),[{slug:'synthetic',nombre:'Pieza sintética',estado:'pedido',ordenes:[{n:1,nota:'Más luminosa',cuando:'',por:''}],quitable:false}]);
  assert.deepEqual(JSON.parse(JSON.stringify(s.ctx.SalaSalida.cambioDe('synthetic-v1',1))),{n:1,nota:'Más luminosa',cuando:'',por:''});
  assert.equal(s.ctx.SalaSalida.cambioDe('synthetic-v1',2),null);
  const rendered=await s.render(z);
  assert.doesNotMatch(rendered,/está lista para lanzar|data-lista="1"/);
  // segunda vuelta: otra orden sobre la versión rehecha (v2) antes de reempacar; el paquete v1 sigue fuera del montón
  s.ctx.SalaSalida.llegaron({'cambio:synthetic':{tira:'synthetic-v2',paquete:'synthetic-v1',ordenes:[{n:1,nota:'Otra vez'}]}});
  assert.deepEqual([s.ctx.filaLinea(z).lista,s.ctx.SalaSalida.pendientes().length],[false,0]);
  // la mesa ya trae una versión más nueva (v3): «volvió», el paquete viejo no se ofrece y no hay botón de quitar
  s.ctx.SalaTablero={pidDe:slug=>slug==='synthetic'?'synthetic-v3':null};
  const v=s.ctx.filaLinea(z);
  assert.deepEqual([v.lista,v.quien,v.que],[false,'fab','Hay una versión nueva. Cuando esté aprobada y con su paquete nuevo, vuelve a tu montón.']);
  assert.deepEqual(JSON.parse(JSON.stringify(s.ctx.SalaSalida.enCambio().map(x=>[x.estado,x.quitable]))),[['volvio',false]]);
  delete s.ctx.SalaTablero;
  // sin órdenes en la hoja vuelve a estar lista
  s.ctx.SalaSalida.llegaron({});
  assert.equal(s.ctx.filaLinea(z).lista,true);
});

test('«Cómo va» con orden de cambio: pedido, volvió y pieza sin paquete (cambioDePieza simulado según el contrato)',()=>{
  const s=sala(),z=s.piece();
  const llamadas=[];let resp={estado:'',ordenes:[]};
  s.ctx.SalaSalida.cambioDePieza=(nombre,slug)=>{llamadas.push([nombre,slug]);return resp};
  const ordenes=[{n:2,nota:'Más luminosa'},{n:3,nota:'Sin texto'}];
  const hay=(pend)=>{s.ctx.pasosPendientesDe=()=>pend;return s.ctx.filaLinea(z)};
  // estado vacío: no cambia nada y recibió nombre y slug de la pieza
  assert.equal(hay([]).quien==='fab',false);
  assert.deepEqual(llamadas[0],[z.nombre,z.slug]);
  // pedido, sin pendientes en la mesa
  resp={estado:'pedido',ordenes};let f=hay([]);
  assert.deepEqual([f.quien,f.lista,f.tuyo],['fab',false,false]);
  assert.equal(f.que,'Cambio pedido en las imágenes 2 y 3, con la nota del editor.');
  assert.equal(f.cuando,'Suele tardar varias horas; cuando esté lista llega a la mesa para aprobarla.');
  // volvió, sin pendientes: el paquete viejo no se ofrece
  s.ctx.EXP[z.nombre]={estado:'lista',paquete:{orden:1,id:'synthetic-v1',slug:'synthetic',imagenes:[{n:1,src:'synthetic.png'}]}};
  resp={estado:'volvio',ordenes:[]};f=hay([]);
  assert.deepEqual([f.quien,f.lista,f.tuyo],['fab',false,false]);
  assert.equal(f.que,'Hay una versión nueva. Cuando esté aprobada y con su paquete nuevo, vuelve a tu montón.');
  // con pendientes en la mesa manda «Te toca», en cualquiera de los dos estados
  for(const estado of ['pedido','volvio']){resp={estado,ordenes};f=hay([0]);
    assert.deepEqual([f.quien,f.tuyo],['tu',true]);assert.match(f.que,/^Te toca: 1 en tu mesa de hoy/)}
  // pieza SIN paquete («Las 48 Horas»): antes decía «Guardada»
  delete s.ctx.EXP[z.nombre];
  resp={estado:'pedido',ordenes:[{n:1,nota:'x'}]};f=hay([]);
  assert.equal(f.que,'Cambio pedido en la imagen 1, con la nota del editor.');
  assert.doesNotMatch(f.que,/Guardada/);
});

test('una pieza guardada por regla no promete texto: espera la decisión de Dirección',async()=>{
  const s=sala(),z=s.piece();
  vm.runInContext("REGLAS_SALA={salida_excluir:'otra, synthetic',nube_ejecuta_etapas:'prospecto'}",s.ctx);
  const f=s.ctx.filaLinea(z),rendered=await s.render(z);
  assert.equal(f.sal,'guardada');
  assert.match(f.que,/Guardada: no sale hasta que tú lo digas/);
  assert.match(rendered,/1 está guardada y espera tu decisión/);
  assert.doesNotMatch(rendered,/Es el paso del consejo/);
});

test('con los paquetes en pausa el relator lo dice',async()=>{
  const s=sala(),z=s.piece();
  vm.runInContext("REGLAS_SALA={salida_activa:'0'}",s.ctx);
  assert.equal(s.ctx.filaLinea(z).cuando,'Los paquetes están en pausa.');
});

test('con el video en pausa, lo que nació para video camina como carrusel y sus trabajos viejos no cuentan',async()=>{
  const s=sala(),z=s.piece({voz:[{id:'q1',etapa:'voz',estado:'fallo',evidencia:{error:'cuota'}}]});
  assert.equal(s.ctx.filaLinea(z).rojo,true,'sin reglas leídas se conserva la lectura de siempre');
  vm.runInContext("REGLAS_SALA={nube_ejecuta_etapas:'prospecto'}",s.ctx);
  const f=s.ctx.filaLinea(z);
  assert.deepEqual([...f.segs.map(x=>x.k)],['guion','laminas','copy','publicada']);
  assert.deepEqual([f.rojo,f.sal],[false,'texto']);
  vm.runInContext("REGLAS_SALA={nube_ejecuta_etapas:'voz,escena,corte,prospecto'}",s.ctx);
  assert.equal(s.ctx.filaLinea(z).segs.length,7);
  assert.equal(s.ctx.filaLinea(z).rojo,true);
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
  assert.match(rendered,/Imágenes aprobadas\. Falta su texto\./);
  assert.doesNotMatch(rendered,/En proceso:|trabajo en cola|pone en cola|≈/);
  assert.equal(s.ctx.filaLinea(z).fab,false);
});


/* ficha de la pieza y hoja de la lámina: con una orden de cambio el paquete viejo no se ofrece (9-nov) */
function conVista(s,quien='editor'){
  const c=s.ctx,sal={};
  c.hoja=(h,id)=>{sal.html=h;sal.id=id;const q=sel=>sel[0]==='#'&&h.includes('id="'+sel.slice(1)+'"')?{}:null;return {querySelector:q}};
  c.$=sel=>{const id=sel.slice(1);return sal.html&&sal.html.includes('id="'+id+'"')?{}:null};
  c.armarPiezas=async()=>[c.__z];c.formatoDePieza=()=>'carrusel';c.laminaAbierta=()=>null;c.pasoHTML=(n,e,b)=>`<div>${n}${b||''}</div>`;
  c.nodoDePieza=()=>({});c.fichaIdeaProd=()=>{throw Error('sin ficha')};c.cerrarCapas=()=>{};
  c.serialDe=()=>'';c.fechaBonita=()=>'';c.notaDeLamina=()=>'';c.enMesaTira=()=>null;c.conSeguro=()=>{};c.pedirNota=()=>{};
  c.idx=0;c.lockeadas=[];c.DECIDE=()=>quien==='editor';
  for(const f of [block('async function fichaPieza(nombre){','function pasoHTML'.length?'\n}\n':'')])
    vm.runInContext(f+'\n}',c);
  return sal;
}
test('la ficha de la pieza no ofrece publicar un paquete viejo con un cambio pedido o ya rehecho',async()=>{
  const s=sala(),z=s.piece();s.ctx.__z=z;const sal=conVista(s);
  s.ctx.EXP[z.nombre]={estado:'lista',paquete:{orden:1,id:'synthetic-v1',slug:'synthetic',imagenes:[{n:1,src:'synthetic.png'}]}};
  s.ctx.SalaSalida.llegaron({});
  await s.ctx.fichaPieza(z.nombre);
  assert.match(sal.html,/id="fPublicar"/,'sin orden: se ofrece');
  s.ctx.SalaSalida.llegaron({'cambio:synthetic':{tira:'synthetic-v1',ordenes:[{n:1,nota:'x'}]}});
  assert.equal(s.ctx.SalaSalida.cambioDePieza(z.nombre,'synthetic').estado,'pedido');
  await s.ctx.fichaPieza(z.nombre);
  assert.doesNotMatch(sal.html,/id="fPublicar"/);assert.match(sal.html,/Cambio pedido<\/b>: este paquete ya no es el que va a salir/);
  // 'volvio': la versión empacada es la de la orden y la mesa ya trae otra
  s.ctx.SalaSalida.llegaron({'cambio:synthetic':{tira:'synthetic-v1',paquete:'synthetic-v1',ordenes:[]}});
  s.ctx.SalaTablero={pidDe:()=>'synthetic-v2'};
  assert.equal(s.ctx.SalaSalida.cambioDePieza(z.nombre,'synthetic').estado,'volvio');
  await s.ctx.fichaPieza(z.nombre);
  assert.doesNotMatch(sal.html,/id="fPublicar"/);assert.match(sal.html,/Hay una versión nueva<\/b>; vuelve a tu montón/);
  assert.match(sal.html,/Escríbelo como encargo/);assert.doesNotMatch(sal.html,/la reabre/);
});

test('verLamina: «Pedir cambio a esta lámina» sólo con editor, hoja leída y pieza no publicada',()=>{
  const s=sala(),z=s.piece();const sal=conVista(s);
  const t=z.tira;t.laminas[0].estado='aprobada';
  vm.runInContext(block('function verLamina(t,n){','/* 7-sep (Alejandro)')+'\n',s.ctx);
  const ver=()=>{sal.html='';s.ctx.verLamina(t,1);return /id="reabrirLam"/.test(sal.html)};
  assert.equal(ver(),false,'sin hoja leída no aparece');
  s.ctx.SalaSalida.llegaron({});
  assert.equal(ver(),true,'editor con hoja leída');
  assert.match(sal.html,/Pedir cambio a esta lámina/);
  s.ctx.publicadas.add(t.pieza);assert.equal(ver(),false,'pieza publicada');
  s.ctx.publicadas.clear();s.ctx.DECIDE=()=>false;assert.equal(ver(),false,'lector');
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
  // 9-nov: el día tiene su propio tope (30 s). En frío midió 14 s y con 8 s fallaba siempre. Siguen siendo dos peticiones.
  assert.equal(calls,2);assert.deepEqual(delays,[30000,400,30000]);
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
