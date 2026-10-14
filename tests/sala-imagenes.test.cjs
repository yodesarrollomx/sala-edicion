const test=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const html=fs.readFileSync('index.html','utf8');
const workflow=fs.readFileSync('.github/workflows/sala-mesa.yml','utf8');
const producer=fs.readFileSync('nube/sala_mesa.py','utf8');
function block(a,b){const i=html.indexOf(a),j=html.indexOf(b,i+a.length);assert.ok(i>=0&&j>i,'falta '+a);return html.slice(i,j)}
test('los scripts de Sala son JavaScript válido',()=>{
  const blocks=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m=>m[1]).filter(s=>s.trim());
  assert.ok(blocks.length>0);
  blocks.forEach((source,i)=>assert.doesNotThrow(()=>new vm.Script(source,{filename:'sala-'+i+'.js'})));
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
test('error de imagen ofrece botón real de reintento y bloqueo de aprobaciones',()=>{
  const snippet=block('function montarImagen(el,src,prioritaria=true,reintento=false){','function dobleToque(');
  const ctx={_porRuta:{},ligera:x=>x,deDrive:()=>'',Date,document:{createElement(tag){return {tag,textContent:'',onclick:null}}}};
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
  retry.onclick({preventDefault(){},stopPropagation(){}});
  assert.match(img.src,/reintentar=/);
  const decide=block('function decidir(m){','function avanzar(m){');
  assert.match(decide,/actual\.dataset\.imagenLista!=='si'/);
  assert.match(block('function pintarCartas(){','const MANDO_HTML='),/mini\.naturalWidth/);
});
test('imagen disponible se muestra y el visor tiene salida y reintento',()=>{
  const snippet=block('function montarImagen(el,src,prioritaria=true,reintento=false){','function dobleToque(');
  const ctx={_porRuta:{},ligera:x=>x,deDrive:()=>'',Date,document:{createElement(tag){return {tag}}}};
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
  const ctx={Map,Set,Date,innerWidth:390,innerHeight:844,ICO_VOLVER:'',ligera:x=>x,original:x=>x,bloquear(){},
    matchMedia:()=>({matches:false}),setTimeout:()=>1,clearTimeout(){},
    addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:name=>listeners.delete(name),
    abrirCapa:(_,fn)=>cleanup=fn,cerrarCapa:()=>cleanup(),
    document:{body:{appendChild:z=>layer=z},createElement(){return {classList:{add(){}},
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
