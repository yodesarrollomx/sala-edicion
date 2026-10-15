const test=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const html=fs.readFileSync('index.html','utf8');
const workflow=fs.readFileSync('.github/workflows/sala-mesa.yml','utf8');
const producer=fs.readFileSync('nube/sala_mesa.py','utf8');
const medios=require('../medios-publicos.js'),crypto=require('node:crypto');
function fixtureMedios(){
  const sha='a'.repeat(64),tag='sala-media-'+'b'.repeat(64)+'-mesa';
  return {schema:1,repo:'yodesarrollomx/sala-edicion',entries:{'laminas/synthetic/L1.png':{
    sha256:sha,bytes:1024,mime:'image/png',release_id:123,asset_id:456,tag,
    url:'https://github.com/yodesarrollomx/sala-edicion/releases/download/'+tag+'/'+sha+'.png'}}};
}
function lectorMedios(value,options={}){
  const raw=typeof value==='string'?value:JSON.stringify(value),calls=[];
  const hash=crypto.createHash('sha256').update(raw).digest('hex');
  const receipt=options.receipt===undefined?{media_manifest_sha256:hash}:options.receipt;
  const api=medios.crear({crypto:crypto.webcrypto,fetch:async(url,init)=>{
    calls.push({url,init});
    if(options.fail)throw Error('private error should never escape');
    if(url.startsWith('datos/'))return new Response(raw,{status:options.status||200});
    return new Response(JSON.stringify(receipt),{status:options.receiptStatus||200});
  }});
  return {api,calls};
}
function block(a,b){const i=html.indexOf(a),j=html.indexOf(b,i+a.length);assert.ok(i>=0&&j>i,'falta '+a);return html.slice(i,j)}
test('los scripts de Sala son JavaScript válido',()=>{
  const blocks=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m=>m[1]).filter(s=>s.trim());
  assert.ok(blocks.length>0);
  blocks.forEach((source,i)=>assert.doesNotThrow(()=>new vm.Script(source,{filename:'sala-'+i+'.js'})));
});
test('el lector valida bytes publicados antes de resolver y conserva la ruta editorial',async()=>{
  const value=fixtureMedios(),path=Object.keys(value.entries)[0],url=value.entries[path].url;
  const {api,calls}=lectorMedios(value);
  assert.equal(api.resolver(path),'');assert.equal(api.disponible(),false);
  assert.equal(await api.cargar(),'listo');assert.equal(api.resolver(path),url);
  assert.equal(api.vista(path,'https://drive.invalid/private-original'),url);
  assert.deepEqual(api.fuentes(path,['laminas/synthetic/L1.jpg',path,'https://drive.invalid/private-original']),[url]);
  assert.equal(api.reintentar(url),url);assert.match(api.reintentar('laminas/existing/L1.jpg'),/reintentar=/);
  assert.ok(value.entries[path]);assert.equal(api.resolver('video/existing.mp4'),'video/existing.mp4');
  assert.equal(api.resolver('muestras/existing.jpg'),'muestras/existing.jpg');
  assert.equal(calls.length,2);assert.ok(calls.every(c=>c.init.cache==='no-store'&&c.init.credentials==='omit'));
  assert.ok(calls.every(c=>!c.url.includes('clave')&&!c.url.includes('token')));
});
test('ausencia sólo es legado cuando el recibo tampoco declara manifiesto',async()=>{
  for(const receiptStatus of [200,404]){
    const {api}=lectorMedios('',{status:404,receipt:{},receiptStatus});
    assert.equal(await api.cargar(),'legado');assert.equal(api.resolver('laminas/existing/L1.png'),'laminas/existing/L1.png');
  }
  const {api}=lectorMedios('',{status:404});
  assert.equal(await api.cargar(),'error');assert.equal(api.disponible(),false);
  assert.deepEqual(api.fuentes('laminas/existing/L1.png',['laminas/existing/L1.jpg','https://drive.invalid/original']),[]);
});
test('fallo de red, JSON, pin ausente o distinto cierran imágenes, sin convertir error en vacío',async()=>{
  for(const options of [{fail:true},{status:500},{receipt:{}},{receipt:{media_manifest_sha256:'0'.repeat(64)}},{receiptStatus:403},{receipt:{media_manifest_sha256:null}}]){
    const {api}=lectorMedios(fixtureMedios(),options);
    assert.equal(await api.cargar(),'error');assert.equal(api.disponible(),false);assert.equal(api.resolver('laminas/existing/L1.jpg'),'');
  }
  const {api}=lectorMedios('{broken');assert.equal(await api.cargar(),'error');
  const raw=JSON.stringify(fixtureMedios()).replace('"schema":1','"schema":1,"schema":1');
  assert.equal(await lectorMedios(raw).api.cargar(),'error');
});
test('el contrato rechaza URLs ajenas, firmas, formatos, rutas y referencias contradictorias',()=>{
  const bad=[
    v=>v.repo='another/repo',v=>v.schema=2,v=>v.extra='private',
    v=>v.entries['laminas/../bad.png']=v.entries['laminas/synthetic/L1.png'],
    v=>v.entries['laminas/private%2Fbad.png']=v.entries['laminas/synthetic/L1.png'],
    v=>v.entries['laminas/synthetic/L1.png'].url+='?token=private',
    v=>v.entries['laminas/synthetic/L1.png'].url='https://api.github.com/repos/yodesarrollomx/sala-edicion/releases/assets/456',
    v=>v.entries['laminas/synthetic/L1.png'].url='https://github.com/another/repo/releases/download/sala-media-'+'b'.repeat(64)+'-mesa/a.png',
    v=>v.entries['laminas/synthetic/L1.png'].url='https://drive.google.com/thumbnail?id=private',
    v=>v.entries['laminas/synthetic/L1.png'].mime='image/jpeg',
    v=>v.entries['laminas/synthetic/L1.png'].bytes=0,
    v=>v.entries['laminas/synthetic/L1.png'].bytes=25*1024*1024+1,
    v=>v.entries['laminas/synthetic/L1.png'].release_id=true,
    v=>v.entries['laminas/synthetic/L1.png'].tag=['sala-media-'+'b'.repeat(64)+'-mesa'],
    v=>{const e=v.entries['laminas/synthetic/L1.png'];e.tag='sala-media-12345-1-mesa';e.url='https://github.com/yodesarrollomx/sala-edicion/releases/download/'+e.tag+'/'+e.sha256+'.png';},
    v=>v.entries['laminas/synthetic/L1.png'].private_drive_id='private',
    v=>{const e={...v.entries['laminas/synthetic/L1.png'],bytes:1025};v.entries['laminas/synthetic/L2.png']=e;}
  ];
  for(const mutate of bad){const value=fixtureMedios();mutate(value);assert.throws(()=>medios.validar(value));}
});
test('un reintento fresco invalida imágenes ya cargadas y puede recuperar el mismo mapa',async()=>{
  let fail=false;const value=fixtureMedios(),raw=JSON.stringify(value),hash=crypto.createHash('sha256').update(raw).digest('hex');
  const api=medios.crear({crypto:crypto.webcrypto,fetch:async u=>{
    if(fail)throw Error('network');
    return new Response(u.startsWith('datos/')?raw:JSON.stringify({media_manifest_sha256:hash}));
  }});
  assert.equal(await api.cargar(),'listo');fail=true;
  assert.equal(await api.cargar(),'error');assert.equal(api.disponible(),false);
  fail=false;assert.equal(await api.cargar(),'listo');assert.equal(api.disponible(),true);
});
test('mientras se relee una versión lista o legada se cierra aprobación, sin duplicar lecturas',async()=>{
  for(const initial of ['listo','legado']){
    const value=fixtureMedios(),raw=JSON.stringify(value),hash=crypto.createHash('sha256').update(raw).digest('hex');
    const path=Object.keys(value.entries)[0],pending=[];let hold=false,fail=false;
    const api=medios.crear({crypto:crypto.webcrypto,fetch:async u=>{
      if(hold)await new Promise(resolve=>pending.push(resolve));
      if(fail)throw Error('network');
      if(initial==='legado')return new Response(u.startsWith('datos/')?'':JSON.stringify({}),{status:u.startsWith('datos/')?404:200});
      return new Response(u.startsWith('datos/')?raw:JSON.stringify({media_manifest_sha256:hash}));
    }});
    assert.equal(await api.cargar(),initial);assert.equal(api.disponible(),true);
    hold=true;const fresh=api.cargar(),shared=api.cargar();
    assert.equal(pending.length,2,'dos GET compartidos por ambos consumidores');
    assert.equal(api.estado(),'pendiente');assert.equal(api.disponible(),false);
    assert.equal(api.resolver(path),'');assert.deepEqual(api.fuentes(path,[path,'https://drive.invalid/original']),[]);
    fail=true;pending.forEach(resolve=>resolve());
    assert.deepEqual(await Promise.all([fresh,shared]),['error','error']);assert.equal(api.disponible(),false);
  }
});
test('la aprobación real del tablero comprueba el manifiesto aun con la foto cargada',()=>{
  const source=fs.readFileSync('tablero-sala.js','utf8');
  const vote=source.slice(source.indexOf('function vote('),source.indexOf('async function reintentarFoto('));
  let ready=false,writes=0;
  const context={api:{contexto:()=>({pid:'p',lamina:1,version:1})},S:{choice:{group:'g',n:1,k:0},groups:[{id:'g',pid:'p',t:{laminas:[{n:1,estado:'rehecha'}]}}]},
    eligible:()=>true,markData:()=>({i:0}),options:()=>[{src:'laminas/synthetic/L1.png',indiceOriginal:null}],
    dec:{p:{laminas:[''],notas:['']}},mediosDisponibles:()=>ready,root:{querySelector:()=>({complete:true,naturalWidth:72})},
    pasos:[],lockeadas:[],guardarBorrador(){},programarSubida(){},subir(){writes++;},render(){}};
  vm.runInNewContext(vote+'\nthis.vote=vote;',context);
  context.vote('si');assert.equal(writes,0);assert.equal(context.dec.p.laminas[0],'');assert.match(context.S.notice,/Espera a que cargue/);
  ready=true;context.vote('si');assert.equal(writes,1);assert.equal(context.dec.p.laminas[0],'si');
});
test('Mesa sólo monta después de publicación confirmada y comprobación de archivos',()=>{
  assert.match(workflow,/id: publicacion/);
  assert.match(workflow,/SALA_PUBLICADOR_MODO: snapshots/);
  assert.match(workflow,/steps\.publicacion\.outcome == 'success'/);
  assert.match(producer,/_snapshot_verifier\.file_is_published/);
  assert.match(producer,/la tira no coincide con la versión publicada/);
  assert.match(producer,/def _existe_en_commit_publicado\(ruta\):/);
  assert.match(producer,/sin_publicar\s*=\s*\[/);
  assert.match(producer,/raise sala\.SalaError\(\s*'%d lámina\(s\) sin hash confirmado en la versión publicada/);
});
test('error de imagen ofrece botón real de reintento y bloqueo de aprobaciones',async()=>{
  const snippet=block('function montarImagen(el,src,prioritaria=true,reintento=false){','function dobleToque(');
  const ctx={_porRuta:{},ligera:x=>x,fuentesImagen:(src,x)=>[...new Set(x.filter(Boolean))],mediosDisponibles:()=>true,deDrive:()=>'',Date,document:{createElement(tag){return {tag,textContent:'',onclick:null}}}};
  vm.runInNewContext(snippet+'\nthis.montar=montarImagen;',ctx);
  const content={children:[],textContent:'',replaceChildren(){this.children=[]},append(...v){this.children.push(...v)},remove(){this.removed=true}};
  const img={complete:false,naturalWidth:0,classList:{add(){}},
    set src(x){this.url=x;this.onerror()},get src(){return this.url}};
  const el={dataset:{},querySelector(q){if(q==='.lienzo img'||q==='img')return img;if(q==='.lienzo .cargando')return content;return null}};
  ctx.montar(el,'laminas/sin-publicar/L1-1.jpg');
  assert.equal(el.dataset.imagenLista,'no');
  const retry=content.children.find(x=>x.tag==='button');
  assert.equal(retry.textContent,'Reintentar imagen');
  assert.equal(typeof retry.onclick,'function');
  await retry.onclick({preventDefault(){},stopPropagation(){}});
  assert.match(img.src,/reintentar=/);
  const decide=block('function decidir(m){','function avanzar(m){');
  assert.match(decide,/actual\.dataset\.imagenLista!=='si'/);
  assert.match(block('function pintarCartas(){','const MANDO_HTML='),/mini\.naturalWidth/);
});
test('imagen disponible se muestra y el visor tiene salida y reintento',()=>{
  const snippet=block('function montarImagen(el,src,prioritaria=true,reintento=false){','function dobleToque(');
  const ctx={_porRuta:{},ligera:x=>x,fuentesImagen:(src,x)=>[...new Set(x.filter(Boolean))],mediosDisponibles:()=>true,deDrive:()=>'',Date,document:{createElement(tag){return {tag}}}};
  vm.runInNewContext(snippet+'\nthis.montar=montarImagen;',ctx);
  const content={removed:false,remove(){this.removed=true}};
  const img={complete:false,naturalWidth:0,classList:{add(){}},
    set src(x){this.url=x;this.complete=true;this.naturalWidth=1080;this.onload()},get src(){return this.url}};
  const el={dataset:{},querySelector(q){if(q==='.lienzo img'||q==='img')return img;if(q==='.lienzo .cargando')return content.removed?null:content;return null}};
  ctx.montar(el,'laminas/publicada/L1-1.jpg');
  assert.equal(el.dataset.imagenLista,'si'); assert.equal(content.removed,true);
  const zoom=block('function abrirZoom(src,opc){','/* ══ final / vacío');
  assert.match(zoom,/class="zoom-error"/);assert.match(zoom,/class="reintentar-zoom"/);
  assert.match(zoom,/img\.onerror=\(\)=>proxima\(\)/);
  assert.match(zoom,/closest\('\.zx,\.reintentar-zoom,\.zg'\)/);
  assert.match(html,/\.cargando\{[^}]*\}\s*\.lienzo>\.cargando\{z-index:3\}/); // regla separada, no CSS anidado
});
test('galería sintética navega por teclado y elige sólo por clic explícito',()=>{
  let layer,cleanup,chosen=null;
  const listeners=new Map(),nodes={};
  for(const selector of ['.zoom-error','.reintentar-zoom','.zx','.zg-cual b','.zg-cual small','.zg-elegir','.zg-ant','.zg-sig'])nodes[selector]={style:{}};
  const img={style:{},naturalWidth:1000,naturalHeight:600,complete:true,set src(value){this.url=value;this.onload?.()},get src(){return this.url}};
  const gallery={querySelector:q=>nodes[q]};
  const ctx={Map,Set,Date,innerWidth:390,innerHeight:844,ICO_VOLVER:'',ligera:x=>x,original:x=>x,fuentesImagen:(src,x)=>[...new Set(x.filter(Boolean))],bloquear(){},
    matchMedia:()=>({matches:false}),setTimeout:()=>1,clearTimeout(){},
    addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:name=>listeners.delete(name),
    abrirCapa:(_,fn)=>cleanup=fn,cerrarCapa:()=>cleanup(),
    document:{body:{appendChild:z=>layer=z},createElement(){return {dataset:{},classList:{add(){}},
      querySelector(q){return q==='img'?img:q==='.zg'?(this.innerHTML.includes('class="zg"')?gallery:null):nodes[q]},
      addEventListener(){},remove(){this.removed=true}}}}};
  vm.runInNewContext(block('function abrirZoom(src,opc){','/* ══ final / vacío')+'\nthis.open=abrirZoom;',ctx);
  ctx.open('synthetic-a',{galeria:[{src:'synthetic-a',titulo:'Actual'},{src:'synthetic-b',titulo:'Candidata',elegir:()=>chosen='b'}],i:0});
  assert.equal(img.src,'synthetic-a');assert.equal(nodes['.zg-cual small'].textContent,'1 de 2');assert.equal(chosen,null);
  listeners.get('keydown')({key:'ArrowRight',preventDefault(){}});assert.equal(img.src,'synthetic-b');assert.equal(nodes['.zg-cual small'].textContent,'2 de 2');assert.equal(chosen,null);
  listeners.get('keydown')({key:'ArrowLeft',preventDefault(){}});assert.equal(img.src,'synthetic-a');
  nodes['.zg-sig'].onclick({stopPropagation(){}});nodes['.zg-elegir'].onclick({stopPropagation(){}});
  assert.equal(chosen,'b');assert.equal(layer.removed,true);assert.equal(listeners.has('keydown'),false);
  ctx.open('synthetic-alone');assert.equal(layer.querySelector('.zg'),null);cleanup();
});
