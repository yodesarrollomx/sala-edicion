/* Salida de la Sala corta en el navegador: el montón listo para lanzar (orden, ritmo, arranque), la hoja de publicar
   y «Ya la publiqué».
   Datos sintéticos; ninguna petición sale de la máquina y las escrituras se interceptan y se cuentan. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=path.resolve(__dirname,'..');
const TIPO={'.js':'application/javascript','.css':'text/css','.html':'text/html','.json':'application/json','.png':'image/png'};
const server=http.createServer((req,res)=>{const u=new URL(req.url,'http://localhost'),p=path.join(root,u.pathname==='/'?'index.html':u.pathname);
  try{res.setHeader('Content-Type',TIPO[path.extname(p)]||'text/html');res.end(fs.readFileSync(p));}catch(e){res.writeHead(404);res.end();}});
const PNG=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==','base64');

const PIEZAS=[['uno-nube-2026-11-01-aaaaaa','uno','Pieza Uno','Carrusel',3],['dos-nube-2026-11-01-bbbbbb','dos','Pieza Dos','Carrusel',2],
              ['tres-nube-2026-11-01-cccccc','tres','Pieza Tres','Lámina',1],['cuatro-nube-2026-11-01-dddddd','cuatro','Pieza Cuatro','Reel',2]];
const tira=([pid,slug,pieza,formato,n])=>({pieza,pieza_slug:slug,formato,promesa:'Promesa de '+pieza,fecha:'2026-11-01',
  laminas:Array.from({length:n},(_,i)=>({n:i+1,src:`laminas/${slug}/L${i+1}.png`,dice:`${pieza} lámina ${i+1}`,estado:'propuesta'}))});
const TEXTO='Primer renglón del texto.\nSegundo renglón.\n\nEso es tu Plan de Potencial Personalizado.';
const LIGA_IG='https://yodesarrollo.github.io/plan-potencial/?utm_source=instagram&utm_medium=social&utm_campaign=ig-2026-11-09&utm_content=uno';
const LIGA_FB=LIGA_IG.replace('instagram','facebook').replace('ig-','fb-');
const expedientes=()=>({'Pieza Uno':{pieza:'Pieza Uno',estado:'lista',portada:'laminas/uno/L1.png',
  paquete:{carpeta:'1 · Pieza Uno',orden:1,url:'https://drive.google.com/drive/folders/sintetica',formato:'Carrusel',nota_formato:'',id:PIEZAS[0][0],slug:'uno',sello:'a'.repeat(12),
    imagenes:[1,2,3].map(n=>({n,src:`laminas/uno/L${n}.png`,archivo:`0${n}.png`,dice:`Pieza Uno lámina ${n}`}))},
  copy:{texto:TEXTO,instagram:TEXTO+'\n(la liga te espera en el primer comentario)',comentario:LIGA_IG,facebook:TEXTO+'\n'+LIGA_FB,revision:['Lámina 3: el fondo se ve ajeno.']},hitos:[]}});
const dia=rol=>({fecha:'2026-11-09',rol,quien:'Editor sintético',propuestas:[],decisiones:{editores:[],propuestas:{}},produccion:[]});

/* el sitio y sus datos públicos, iguales para los dos recorridos */
async function estatico(route,u,rol){
 if(u.hostname!=='127.0.0.1')return route.fulfill({body:'',contentType:'application/javascript'});
 if(u.pathname==='/version-online.json')return route.fulfill({json:{}});
 if(u.pathname==='/datos/medios-publicos.json')return route.fulfill({status:404,body:''});
 if(u.pathname==='/datos/manifiesto.json')return route.fulfill({json:dia(rol)});
 if(u.pathname==='/datos/tiras/index.json')return route.fulfill({json:PIEZAS.map(p=>p[0])});
 if(u.pathname==='/datos/mesa-estado.json')return route.fulfill({json:{schema:1,revisado_en:'2026-11-09T22:00:00Z',
   publicaciones:PIEZAS.map(p=>({id:p[0],laminas:Array.from({length:p[4]},(_,i)=>({n:i+1,estado:'aprobada'}))}))}});
 const t=PIEZAS.find(p=>u.pathname==='/datos/tiras/'+p[0]+'.json');
 if(t)return route.fulfill({json:tira(t)});
 if(u.pathname==='/datos/universo/universo.json')return route.fulfill({json:{formato:{segundos:15},vertices:{ppp:{nombre:'Plan de Potencial'}},personajes:{marta:{nombre:'Marta',papel:'cliente'}},lugares:{terreno:{nombre:'El terreno'}},
   historias:{h1:{titulo:'Historia sintética',vertice:'ppp',personajes:['marta'],lugar:'terreno',dialogo:'Una línea de prueba.'}}}});
 if(u.pathname.startsWith('/datos/'))return route.fulfill({json:u.pathname.endsWith('/index.json')?[]:{}});
 if(u.pathname.startsWith('/laminas/'))return route.fulfill({body:PNG,contentType:'image/png'});
 return route.continue();
}

/* 12-nov: el editor abre en EL LIBRO (una publicación por página). Los recorridos del montón siguen en la lista. */
async function aLista(page){
 await page.waitForSelector('#salidaHoy .sal-carta, #salidaHoy .sal-libro',{timeout:30000});
 if(await page.locator('#salidaHoy .sal-libro').count()){await page.click('#salidaHoy [data-lista="1"]');await page.waitForSelector('#salidaHoy .sal-carta',{timeout:30000});}
}
/* El libro: va arriba, decide una por una, «No va» saca del montón sin borrar y se puede regresar. */
async function libro(base,width){
 const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH}:{})});
 try{
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),errors=[],writes=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{localStorage.setItem('sala_clave','synthetic');localStorage.setItem('sala_rol','editor');localStorage.setItem('sala_guia','1');localStorage.setItem('sala_guia_v3','1');});
  const uno=expedientes()['Pieza Uno'],exp={'Pieza Uno':uno,
   'Pieza Dos':{...uno,pieza:'Pieza Dos',portada:'laminas/dos/L1.png',paquete:{...uno.paquete,carpeta:'2 · Pieza Dos',orden:2,id:PIEZAS[1][0],slug:'dos',sello:'b'.repeat(12),imagenes:[1,2].map(n=>({n,src:`laminas/dos/L${n}.png`,dice:`Pieza Dos lámina ${n}`}))},copy:{...uno.copy,revision:[]}},
   'Pieza Cuatro':{...uno,pieza:'Pieza Cuatro',portada:'laminas/cuatro/L1.png',paquete:{...uno.paquete,carpeta:'3 · Pieza Cuatro',orden:3,id:PIEZAS[3][0],slug:'cuatro',sello:'c'.repeat(12),imagenes:[1].map(n=>({n,src:`laminas/cuatro/L${n}.png`,dice:`Pieza Cuatro lámina ${n}`}))},copy:{...uno.copy,revision:[]}}};
  await page.route('**/*',async route=>{
   const req=route.request(),u=new URL(req.url());
   if(req.method()==='POST'){const d=JSON.parse(req.postData()||'{}');writes.push(d);if(d.accion==='expediente')exp[d.pieza]=d.expediente;return route.fulfill({json:{ok:true}});}
   if(u.hostname==='script.google.com'){
    const r=u.searchParams.get('recurso');
    if(r==='dia')return route.fulfill({json:dia('editor')});
    if(r==='expedientes')return route.fulfill({json:{ok:true,expedientes:exp}});
    if(r==='reglas')return route.fulfill({json:{ok:true,reglas:{semillero_activo:'0'},motores:[]}});
    return route.fulfill({json:{ok:true,cola:[],fabrica:[],ideas:[]}});
   }
   return estatico(route,u,'editor');
  });
  await page.goto(base);
  await page.waitForSelector('#salidaHoy .sal-libro',{timeout:30000});
  const h2=()=>page.locator('#salidaHoy h2').textContent(), titulo=()=>page.locator('#salidaHoy .sal-libro h3').textContent(), pag=()=>page.locator('#salidaHoy .sal-lib-pag').textContent();
  assert.equal(await page.locator('#salidaHoy .bt-eyebrow').first().textContent(),'TU LIBRO');
  assert.equal(await h2(),'3 publicaciones por decidir');
  assert.equal(await page.locator('#salidaHoy .sal-carta').count(),0,'el libro no enseña todas juntas');
  assert.equal(await titulo(),'Pieza Uno');assert.equal(await pag(),'Página 1 de 3');
  assert.equal(await page.locator('#salidaHoy .sal-lib-img').count(),3);
  assert.equal(await page.locator('#salidaHoy .sal-lib-dec button').count(),3);
  assert.match(await page.locator('#salidaHoy .sal-ojo').innerText(),/Lámina 3: el fondo se ve ajeno\./);
  const caja=await page.locator('#salidaHoy .sal-libro').boundingBox(),dec=await page.locator('#salidaHoy .sal-lib-dec').boundingBox();
  assert.ok(caja.x>=0&&caja.x+caja.width<=width+1,'la página cabe a lo ancho');assert.ok(dec.width<=caja.width,'los tres botones caben');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth),true,'sin desbordamiento horizontal');
  if(process.env.CAPTURA)await page.locator('#salidaHoy').screenshot({path:process.env.CAPTURA+'-'+width+'.png'});
  // navegar no decide
  await page.click('#salidaHoy [data-lib-ir="1"]');assert.equal(await titulo(),'Pieza Dos');
  await page.click('#salidaHoy [data-lib-ir="-1"]');assert.equal(await titulo(),'Pieza Uno');
  assert.equal(writes.filter(w=>w.accion==='expediente').length,0,'pasar la página no escribe nada');
  // «Va»: se queda en el montón y el libro pasa a la siguiente por decidir
  await page.click('#salidaHoy [data-lib="va"]');
  await page.waitForFunction(()=>document.querySelector('#salidaHoy .sal-libro h3')?.textContent==='Pieza Dos');
  assert.equal(await h2(),'2 publicaciones por decidir');
  await page.waitForFunction(()=>true);await page.waitForTimeout(300);
  let plan=writes.filter(w=>w.accion==='expediente'&&w.pieza==='salida:plan').pop();
  assert.ok(plan,'la decisión sube al plan de salida');assert.equal(plan.expediente.visto['Pieza Uno'].m,'va');assert.equal(plan.expediente.visto['Pieza Uno'].sello,'a'.repeat(12));assert.equal(plan.expediente.visto['Pieza Uno'].por,'editor');
  // «No va»: sale del montón, nada se borra y se puede regresar
  await page.click('#salidaHoy [data-lib="no"]');
  await page.waitForFunction(()=>document.querySelector('#salidaHoy .sal-libro h3')?.textContent==='Pieza Cuatro');
  assert.equal(await h2(),'1 publicación por decidir');assert.equal(await pag(),'Página 2 de 2');
  assert.match(await page.locator('#salidaHoy .sal-cambios').last().innerText(),/1 publicación con «No va».*Pieza Dos/s);
  assert.ok(exp['Pieza Dos'].paquete,'«No va» no borra el paquete');
  await page.click('#salidaHoy [data-lib-volver="Pieza Dos"]');
  await page.waitForFunction(()=>document.querySelector('#salidaHoy .sal-libro h3')?.textContent==='Pieza Dos');
  assert.equal(await h2(),'2 publicaciones por decidir');
  await page.click('#salidaHoy [data-lib="no"]');
  await page.waitForFunction(()=>document.querySelector('#salidaHoy .sal-libro h3')?.textContent==='Pieza Cuatro');
  // «Pedir cambio» abre la orden de cambio de siempre, ya desplegada
  await page.click('#salidaHoy [data-lib="cambio"]');
  await page.waitForSelector('#salCambioCaja:not([hidden])');
  assert.equal(await page.locator('.sal-hoja h3').textContent(),'Pieza Cuatro');
  await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.querySelector('.sal-hoja'));
  // la última decisión cierra el libro y deja el montón: lo que va, en lista
  await page.click('#salidaHoy [data-lib="va"]');
  await page.waitForSelector('#salidaHoy .sal-carta');
  assert.equal(await h2(),'2 listas para lanzar');assert.equal(await page.locator('#salidaHoy .sal-carta').count(),2);
  assert.equal(await page.locator('#salidaHoy [data-lista="0"]').textContent(),'Abrir el libro');
  await page.waitForTimeout(300);
  plan=writes.filter(w=>w.accion==='expediente'&&w.pieza==='salida:plan').pop();
  assert.deepEqual(Object.fromEntries(Object.entries(plan.expediente.visto).map(([k,v])=>[k,v.m])),{'Pieza Uno':'va','Pieza Dos':'no','Pieza Cuatro':'va'});
  // al volver a abrir, la hoja manda: lo decidido no se vuelve a preguntar y el veto sigue fuera
  await page.reload();await page.waitForSelector('#salidaHoy .sal-carta',{timeout:30000});
  assert.equal(await page.locator('#salidaHoy .sal-libro').count(),0);assert.equal(await h2(),'2 listas para lanzar');
  // un paquete nuevo de una pieza ya decidida vuelve al libro
  exp['Pieza Uno']={...exp['Pieza Uno'],paquete:{...exp['Pieza Uno'].paquete,sello:'z'.repeat(12)}};
  await page.reload();await page.waitForSelector('#salidaHoy .sal-libro',{timeout:30000});
  assert.equal(await h2(),'1 publicación por decidir');assert.equal(await titulo(),'Pieza Uno');
  assert.deepEqual(errors,[]);
  await context.close();
 }finally{await browser.close();}
}

(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const base='http://127.0.0.1:'+server.address().port+'/';
 for(const w of [390,1440]) await libro(base,w);
 const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH}:{})});
 try{for(const width of [390,1440])for(const rol of ['editor','lector']){
  const context=await browser.newContext({viewport:{width,height:900},permissions:['clipboard-read','clipboard-write']}),page=await context.newPage(),errors=[],writes=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(r=>{localStorage.setItem('sala_clave','synthetic');localStorage.setItem('sala_rol',r);localStorage.setItem('sala_guia','1');localStorage.setItem('sala_guia_v3','1');},rol);
  const exp=expedientes();
  await page.route('**/*',async route=>{
   const req=route.request(),u=new URL(req.url());
   if(req.method()==='POST'){writes.push(JSON.parse(req.postData()||'{}'));return route.fulfill({json:{ok:true}});}
   if(u.hostname==='script.google.com'){
    const r=u.searchParams.get('recurso');
    if(r==='dia')return route.fulfill({json:dia(rol)});
    if(r==='expedientes')return route.fulfill({json:{ok:true,expedientes:exp}});
    if(r==='reglas')return route.fulfill({json:{ok:true,reglas:{nube_ejecuta_etapas:'prospecto',salida_excluir:'tres',semillero_activo:'0'},motores:[]}});
    return route.fulfill({json:{ok:true,cola:[],fabrica:[],ideas:[]}});
   }
   return estatico(route,u,rol);
  });
  await page.goto(base);
  // «Te toca» abre con lo listo para publicar, lo que espera texto y lo guardado por regla
  await aLista(page);
  await page.waitForFunction(()=>document.querySelectorAll('#salidaHoy .sal-pie').length===2,null,{timeout:30000});
  assert.equal(await page.locator('#salidaHoy h2').textContent(),'1 lista para lanzar');
  assert.match(await page.locator('#salidaHoy header p').first().innerText(),/^A 3 por semana alcanza para 1 semana\. Nada sale solo: tú das el clic de publicar\.$/);
  const pies=await page.locator('#salidaHoy .sal-pie').allTextContents();
  assert.match(pies[0],/^2 piezas más ya tienen sus imágenes aprobadas y esperan su texto/);
  assert.match(pies[1],/^1 pieza guardada \(no sale hasta que tú digas; nada se borra\): Pieza Tres\./);
  assert.equal(await page.locator('#salidaHoy .sal-ir').textContent(),'Abrir →');
  assert.equal(await page.locator('#salidaHoy .sal-cuando').textContent(),'Semana 1');
  assert.equal(await page.locator('#salidaHoy .sal-plan').count(),rol==='editor'?1:0,'el plan de salida es de los editores');
  // con montón y nada por revisar, la mesa se pliega a un renglón; se abre y se vuelve a plegar
  await page.waitForSelector('#tableroHoy[data-level="plegada"]');
  assert.equal(await page.locator('.bt-column').count(),0);
  assert.match(await page.locator('.bt-plegada').innerText(),/LA MESA EDITORIAL\s+4 publicaciones · nada por revisar/);
  await page.locator('[data-abrir-mesa]').click();await page.waitForSelector('.bt-column');
  assert.equal(await page.locator('.bt-column').count(),4);
  await page.locator('[data-plegar]').click();await page.waitForSelector('#tableroHoy[data-level="plegada"]');
  assert.ok(await page.evaluate(()=>document.documentElement.scrollHeight<3200),'«Te toca» ya no es una pared de páginas aprobadas');
  assert.ok(await page.locator('#salidaHoy .sal-foto img').evaluate(i=>i.complete&&i.naturalWidth>0),'la portada del paquete se ve');
  const box=await page.locator('#salidaHoy .sal').boundingBox();assert.ok(box.x>=0&&box.x+box.width<=width+1,'sin desbordar la pantalla');

  // «Cómo va» ya no queda tapado por la mesa y cuenta la verdad de cada pieza
  await page.locator('#puertas [data-v="prod"]').click();
  await page.waitForSelector('#linea .ln-fila',{timeout:30000});
  assert.equal(await page.locator('#vHoy').evaluate(e=>getComputedStyle(e).display),'none','la mesa no tapa «Cómo va»');
  const filas=Object.fromEntries(await page.evaluate(()=>[...document.querySelectorAll('#linea .ln-fila')].map(f=>[f.querySelector('.ln-nom b').textContent,f.querySelector('.ln-rel').innerText.replace(/\s+/g,' ')])));
  assert.match(filas['Pieza Uno'],/^LISTA Lista para lanzar: 3 imágenes y su texto\./i);
  assert.doesNotMatch(Object.values(filas).join(' '),/publícala|150%/i);
  assert.deepEqual(await page.evaluate(()=>[...document.querySelectorAll('#linea .ln-nom small')].map(x=>parseInt(x.textContent,10)).filter(n=>!(n>=0&&n<=100))),[],'ningún avance pasa de 100 %');
  assert.match(filas['Pieza Dos'],/Imágenes aprobadas\. Falta su texto\./);
  assert.match(filas['Pieza Tres'],/Guardada: no sale hasta que tú lo digas/);
  assert.match(filas['Pieza Cuatro'],/Imágenes aprobadas\. Falta su texto\./,'con el video en pausa, lo que nació para video camina como carrusel');
  assert.equal(await page.locator('#linea .ln-fila').first().locator('.ln-nom b').textContent(),'Pieza Uno','lo listo para publicar va primero');
  assert.match(await page.locator('#linea .rel').textContent(),/4 publicaciones abiertas\. 1 está lista para lanzar, 2 con imágenes aprobadas esperan su texto, 1 está guardada y espera tu decisión\./);
  assert.match(await page.locator('#universo').innerText(),/HISTORIAS DE 15 SEGUNDOS[\s\S]*Historia sintética[\s\S]*se graba cuando enciendas el video/i);

  // la hoja de publicar, desde la Línea
  await page.locator('#linea .ln-fila').first().click();
  await page.waitForSelector('.sal-hoja');
  assert.equal(await page.locator('.sal-hoja .sal-img').count(),3);
  assert.match(await page.locator('.sal-hoja .sal-ojo').innerText(),/el fondo se ve ajeno/);
  assert.equal(await page.locator('.sal-hoja a.sal-liga').getAttribute('href'),'https://drive.google.com/drive/folders/sintetica');
  assert.equal(await page.locator('#salTexto').inputValue(),TEXTO);
  const copia=async sel=>{await page.locator(sel).click();await page.waitForFunction(s=>document.querySelector(s).textContent==='Copiado ✓',sel);return page.evaluate(()=>navigator.clipboard.readText());};
  assert.equal(await copia('#salIg'),TEXTO+'\n(la liga te espera en el primer comentario)');
  assert.equal(await copia('#salFb'),TEXTO+'\n'+LIGA_FB);
  assert.equal(await copia('#salCom'),LIGA_IG);
  if(rol==='lector'){
   assert.equal(await page.locator('#salYa').count(),0,'un lector no anota publicaciones');
   assert.equal(await page.locator('#salCambio').count(),0,'ni pide cambios');
   assert.equal(writes.length,0);
  }else{
   assert.equal(await page.locator('#salCambio').count(),1,'un editor puede pedir cambio a una imagen de la pieza lista');
   assert.equal(await page.locator('#salCambioCaja').isHidden(),true,'pero no estorba: se abre sólo si lo toca');
   // el texto se puede cambiar y se copia como quedó
   await page.locator('#salTexto').fill('Mi versión del texto.');
   assert.equal(await copia('#salIg'),'Mi versión del texto.\n(la liga te espera en el primer comentario)');
   // una liga a medias no se anota
   await page.locator('#salPost').fill('instagram.com/p/x');await page.locator('#salYa').click();
   assert.match(await page.locator('#salAviso').textContent(),/no parece una dirección completa/);assert.equal(writes.length,0);
   // «Ya la publiqué»: una sola fila en PRODUCCION, sin decidir nada
   await page.locator('#salPost').fill('https://www.instagram.com/p/ABC123/');await page.locator('#salYa').click();
   await page.waitForSelector('#salOk');
   assert.equal(writes.length,1);
   const w=writes[0],det=JSON.parse(w.detalle);
   assert.deepEqual([w.accion,w.pieza,w.estado,w.enlace,w.fecha],['produccion','Pieza Uno','publicada','https://www.instagram.com/p/ABC123/','2026-11-09']);
   assert.equal(det.texto_final,'Mi versión del texto.');assert.ok(det.envio_id);
   await page.locator('#salOk').click();
   await page.waitForFunction(()=>![...document.querySelectorAll('#linea .ln-fila .ln-nom b')].some(b=>b.textContent==='Pieza Uno'),null,{timeout:30000});
   // la pieza sale de «Te toca» aunque la nube todavía no cierre su expediente, también tras recargar
   await page.reload();
   await page.waitForFunction(()=>document.querySelectorAll('#salidaHoy .sal-pie').length===2,null,{timeout:30000});
   assert.equal(await page.locator('#salidaHoy .sal-carta').count(),0);
   assert.equal(await page.locator('#salidaHoy h2').textContent(),'Todavía no hay nada listo para lanzar');
   await page.waitForSelector('.bt-column');   // sin montón, la mesa vuelve a verse entera
   assert.equal(writes.length,1,'recargar no repite la anotación');
   assert.ok(!writes.some(x=>x.accion==='decidir'));
  }
  if(process.env.SALIDA_CAPTURAS&&rol==='editor'){fs.mkdirSync(process.env.SALIDA_CAPTURAS,{recursive:true});await page.screenshot({path:path.join(process.env.SALIDA_CAPTURAS,'salida-'+width+'.png')});}
  assert.deepEqual(errors,[]);console.log(JSON.stringify({width,rol,errors:0,realWrites:0,interceptedWrites:writes.length}));
  await context.close();
 }
 /* ── El montón: se pinta sin esperar al día, el orden / ritmo / arranque son del editor y se guardan en UNA llave
       de la hoja, y lo último visto se recuerda en el aparato (sólo para quien lo guardó). ── */
 for(const width of [390,1440]){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),errors=[],writes=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{if(!localStorage.getItem('sala_clave')){localStorage.setItem('sala_clave','synthetic');localStorage.setItem('sala_rol','editor');localStorage.setItem('sala_guia','1');localStorage.setItem('sala_guia_v3','1');}});
  const lista=(nombre,orden,slug)=>({pieza:nombre,estado:'lista',portada:`laminas/${slug}/L1.png`,
   paquete:{carpeta:orden+' · '+nombre,orden,url:'https://drive.google.com/drive/folders/sintetica',formato:'Lámina',slug,sello:String(orden).repeat(12),imagenes:[{n:1,src:`laminas/${slug}/L1.png`,archivo:'01.png',dice:nombre}]},
   copy:{texto:TEXTO,instagram:TEXTO,comentario:LIGA_IG,facebook:TEXTO,revision:[]},hitos:[]});
  const hoja={'Pieza A':lista('Pieza A',1,'uno'),'Pieza B':lista('Pieza B',2,'dos'),'Pieza C':lista('Pieza C',3,'tres'),'v4:estado':{x:1}};
  const modo={dia:'lento',exp:'ok',guardar:'ok'};let diaContestado=false;
  await page.route('**/*',async route=>{
   const req=route.request(),u=new URL(req.url());
   if(req.method()==='POST'){const d=JSON.parse(req.postData()||'{}');writes.push(d);
    if(d.accion==='expediente'){if(modo.guardar==='rechaza')return route.fulfill({json:{error:'solo el agente'}});hoja[d.pieza]=d.expediente;}
    return route.fulfill({json:{ok:true}});}
   if(u.hostname==='script.google.com'){
    const r=u.searchParams.get('recurso');
    if(r==='dia'){if(modo.dia==='lento')await new Promise(x=>setTimeout(x,4000));diaContestado=true;return route.fulfill({json:dia('editor')}).catch(()=>{});}
    if(r==='expedientes'){if(modo.exp==='cuelga')return;if(modo.exp==='cae')return route.abort('failed');return route.fulfill({json:{ok:true,expedientes:hoja}});}
    if(r==='reglas')return route.fulfill({json:{ok:true,reglas:{nube_ejecuta_etapas:'prospecto',semillero_activo:'0'},motores:[]}});
    return route.fulfill({json:{ok:true,cola:[],fabrica:[],ideas:[]}});
   }
   return estatico(route,u,'editor');
  });
  const nombres=()=>page.locator('#salidaHoy .sal-carta b').allTextContents();
  const escrituras=n=>page.waitForFunction(()=>true).then(async()=>{for(let i=0;i<60&&writes.length<n;i++)await page.waitForTimeout(100);assert.equal(writes.length,n);});
  await page.goto(base);
  await aLista(page);
  // 1) el montón no esperó al día, y con una lectura en vuelo la página conserva su forma
  assert.equal(diaContestado,false,'lo listo para lanzar se pinta antes de que conteste el día');
  assert.deepEqual(await page.evaluate(()=>{const h=document.documentElement,c=getComputedStyle(h);return [h.classList.contains('trayendo'),c.display,c.position,c.fontSize,Math.round(document.body.getBoundingClientRect().width)===document.documentElement.clientWidth];}),[true,'block','static','16px',true]);
  assert.deepEqual(await nombres(),['Pieza A','Pieza B','Pieza C']);
  assert.equal(await page.locator('#salidaHoy h2').textContent(),'3 listas para lanzar');
  // 2) cambiar el orden: nada se escribe hasta «Guardar el orden»; cancelar no guarda
  await page.locator('[data-ordenar]').click();
  await page.locator('.sal-carta.ordenando[data-pieza="Pieza C"] [data-lugar]').selectOption('1');
  await page.waitForFunction(()=>document.querySelector('#salidaHoy .sal-carta b').textContent==='Pieza C');
  await page.locator('.sal-carta.ordenando[data-pieza="Pieza B"] [data-paso="-1"]').click();
  await page.waitForFunction(()=>[...document.querySelectorAll('#salidaHoy .sal-carta b')].map(b=>b.textContent).join()==='Pieza C,Pieza B,Pieza A');
  assert.equal(writes.length,0);
  await page.locator('[data-orden-ok]').click();await escrituras(1);
  assert.deepEqual([writes[0].accion,writes[0].pieza,writes[0].expediente.orden,writes[0].expediente.por_semana,writes[0].expediente.por,writes[0].clave],['expediente','salida:plan',['Pieza C','Pieza B','Pieza A'],3,'editor','synthetic']);
  await page.waitForFunction(()=>/Plan guardado en el Sheet/.test(document.querySelector('#salidaHoy .sal-estado').textContent));
  await page.locator('[data-ordenar]').click();
  await page.locator('.sal-carta.ordenando[data-pieza="Pieza A"] [data-lugar]').selectOption('1');
  await page.locator('[data-orden-no]').click();
  assert.deepEqual(await nombres(),['Pieza C','Pieza B','Pieza A']);assert.equal(writes.length,1);
  // 3) el ritmo: varios toques seguidos son UNA escritura
  await page.locator('[data-ritmo="1"]').click();await page.locator('[data-ritmo="1"]').click();
  await page.waitForFunction(()=>/A 5 por semana alcanza para 1 semana/.test(document.querySelector('#salidaHoy header').innerText));
  await escrituras(2);
  assert.deepEqual([writes[1].expediente.por_semana,writes[1].expediente.orden],[5,['Pieza C','Pieza B','Pieza A']]);
  // 4) el día de arranque pone fecha a cada una
  const futuro=new Date(Date.now()+21*864e5).toISOString().slice(0,10);
  await page.locator('#salArranque').fill(futuro);await page.locator('#salArranque').dispatchEvent('change');
  await page.waitForFunction(()=>/desde el .+ alcanza hasta el /.test(document.querySelector('#salidaHoy header').innerText));
  assert.match(await page.locator('#salidaHoy .sal-cuando').first().textContent(),/^[a-záé]{3} \d{1,2} [a-z]{3}$/);
  await escrituras(3);assert.equal(writes[2].expediente.arranque,futuro);
  await page.waitForFunction(()=>/Plan guardado en el Sheet/.test(document.querySelector('#salidaHoy .sal-estado').textContent));
  // 4b) si la primera sale hoy, «Te toca» lo dice (arranque de hoy y ritmo diario: hoy siempre toca)
  const hoy=new Date(Date.now()-7*36e5).toISOString().slice(0,10);
  await page.locator('[data-ritmo="1"]').click();await page.locator('[data-ritmo="1"]').click();
  await page.locator('#salArranque').fill(hoy);await page.locator('#salArranque').dispatchEvent('change');
  await page.waitForFunction(()=>/^Hoy toca «Pieza C»\. A 7 por semana/.test(document.querySelector('#salidaHoy header p').innerText));
  assert.match(await page.locator('#salidaHoy .sal-cuando').first().textContent(),/^Hoy · [a-záé]{3} \d{1,2} [a-z]{3}$/);
  assert.equal(await page.locator('#salidaHoy .sal-carta.hoy').count(),1);
  await page.locator('[data-ritmo="-1"]').click();await page.locator('[data-ritmo="-1"]').click();
  await page.locator('#salArranque').fill(futuro);await page.locator('#salArranque').dispatchEvent('change');
  await page.waitForFunction(()=>/^A 5 por semana, desde el /.test(document.querySelector('#salidaHoy header p').innerText));
  assert.equal(await page.locator('#salidaHoy .sal-carta.hoy').count(),0);
  for(let i=0;i<40&&!(writes.length&&writes[writes.length-1].expediente.arranque===futuro&&writes[writes.length-1].expediente.por_semana===5);i++)await page.waitForTimeout(100);
  await page.waitForFunction(()=>/Plan guardado en el Sheet/.test(document.querySelector('#salidaHoy .sal-estado').textContent));
  // 5) la hoja de la pieza dice en qué lugar sale
  await page.locator('#salidaHoy [data-publicar]').first().click();await page.waitForSelector('.sal-hoja');
  assert.match(await page.locator('.sal-sub').textContent(),/sale en el lugar 1 de 3 \(/);
  await page.evaluate(()=>cerrarCapas());
  // 6) al recargar el plan viene de la hoja; con la hoja colgada, el montón sale de lo que guardó el aparato
  modo.dia='ok';await page.reload();await aLista(page);
  await page.waitForFunction(()=>!document.querySelector('#salidaHoy .sal-nota')&&document.querySelectorAll('#salidaHoy .sal-carta').length===3);
  assert.deepEqual(await nombres(),['Pieza C','Pieza B','Pieza A']);
  assert.match(await page.locator('#salidaHoy header').innerText(),/A 5 por semana, desde el /);
  // lo que YOD OS puede leer de este aparato: cuántas hay y cuándo se vio; ni títulos ni textos
  const resumen=await page.evaluate(()=>JSON.parse(localStorage.getItem('sala_resumen_v1')));
  assert.deepEqual(Object.keys(resumen).sort(),['cuando','listas']);assert.equal(resumen.listas,3);assert.ok(Date.now()-resumen.cuando<60000);
  modo.exp='cuelga';await page.reload();await aLista(page);
  assert.deepEqual(await nombres(),['Pieza C','Pieza B','Pieza A']);
  assert.match(await page.locator('#salidaHoy .sal-nota').textContent(),/Lo último que este aparato guardó; confirmando con el Sheet/);
  // 7) si la hoja se cae lo dice y ofrece reintentar; al volver, lo recién empacado entra al final
  modo.exp='cae';await page.reload();await page.waitForSelector('#salidaHoy .sal-nota [data-releer]',{timeout:30000});await aLista(page);
  assert.match(await page.locator('#salidaHoy .sal-nota').textContent(),/El Sheet no contestó: ves lo último que este aparato guardó/);
  assert.equal(await page.locator('#salidaHoy .sal-carta').count(),3);
  hoja['Pieza D']=lista('Pieza D',4,'cuatro');modo.exp='ok';
  await page.locator('#salidaHoy .sal-nota [data-releer]').click();
  await page.waitForFunction(()=>document.querySelectorAll('#salidaHoy .sal-carta').length===4,null,{timeout:30000});
  assert.deepEqual(await nombres(),['Pieza C','Pieza B','Pieza A','Pieza D']);
  // 8) una llave que la hoja no deja escribir: se dice, y el cambio se queda en el aparato
  modo.guardar='rechaza';const antes=writes.length;
  await page.locator('[data-ritmo="-1"]').click();
  await page.waitForFunction(()=>/todavía no puede guardar el plan/.test(document.querySelector('#salidaHoy .sal-estado').textContent),null,{timeout:15000});
  assert.equal(writes.length,antes+1);
  assert.match(await page.locator('#salidaHoy header').innerText(),/A 4 por semana/);
  // 9) nunca decide ni publica, y sólo escribió el plan
  assert.deepEqual([...new Set(writes.map(w=>w.accion+':'+w.pieza))],['expediente:salida:plan']);
  // 10) otra llave en el mismo aparato no ve lo que guardó la primera
  modo.exp='cuelga';await page.evaluate(()=>localStorage.setItem('sala_clave','otra-llave'));
  await page.reload();await page.waitForSelector('#tableroHoy .bt-column,#tableroHoy .bt-plegada',{timeout:30000});await page.waitForTimeout(800);
  assert.equal(await page.locator('#salidaHoy .sal-carta').count(),0,'la copia guardada es de quien la guardó');
  assert.deepEqual(await page.evaluate(()=>[localStorage.getItem('sala_salida_local_v1'),localStorage.getItem('sala_resumen_v1')]),[null,null]);
  assert.deepEqual(errors,[]);console.log(JSON.stringify({width,recorrido:'monton',errors:0,realWrites:0,soloElPlan:writes.every(w=>w.accion==='expediente'&&w.pieza==='salida:plan')}));
  await context.close();
 }
 /* ── Pedir cambio a una imagen YA APROBADA (9-nov, DEC-08 «Las 48 Horas»): desde la hoja de una pieza lista y desde
       la mesa. Es una orden del editor en la llave `cambio:<slug>` de la hoja, atada a la versión (tira) de la pieza:
       la pieza sale del montón mientras se rehace, y la petición se puede quitar. Nunca es una marca de la mesa. ── */
 for(const width of [390,1440]){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),errors=[],writes=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{if(!localStorage.getItem('sala_clave')){localStorage.setItem('sala_clave','synthetic');localStorage.setItem('sala_rol','editor');localStorage.setItem('sala_guia','1');localStorage.setItem('sala_guia_v3','1');}});
  /* el arnés de la mesa (sustituye al pidDe real, que no se puede reasignar): `SalaTablero.pidDe(slug)` enseña la versión de cada pieza (las de PIEZAS); window.__mesaPid se cambia a mano */
  await page.addInitScript(mapa=>{window.__mesaMapa=mapa;window.__mesaPid=slug=>mapa[slug]||null;let api;Object.defineProperty(window,'SalaTablero',{configurable:true,get:()=>api,set:x=>{if(x&&typeof x==='object')Object.defineProperty(x,'pidDe',{configurable:true,get:()=>slug=>window.__mesaPid(slug),set(){}});api=x}})},Object.fromEntries(PIEZAS.map(p=>[p[1],p[0]])));
  const lista=(i,n)=>{const [pid,slug,nombre,formato]=PIEZAS[i];return {pieza:nombre,estado:'lista',portada:`laminas/${slug}/L1.png`,
   paquete:{carpeta:(i+1)+' · '+nombre,orden:i+1,url:'https://drive.google.com/drive/folders/sintetica',formato,id:pid,slug,sello:String(i+1).repeat(12),
    imagenes:Array.from({length:n},(_,k)=>({n:k+1,src:`laminas/${slug}/L${k+1}.png`,archivo:`0${k+1}.png`,dice:`${nombre} lámina ${k+1}`}))},
   copy:{texto:TEXTO,instagram:TEXTO,comentario:LIGA_IG,facebook:TEXTO,revision:[]},hitos:[]};};
  const hoja={'Pieza Uno':lista(0,3),'Pieza Tres':lista(2,1)},modo={guardar:'ok',exp:'ok'};
  await page.route('**/*',async route=>{
   const req=route.request(),u=new URL(req.url());
   if(req.method()==='POST'){const d=JSON.parse(req.postData()||'{}');writes.push(d);
    if(d.accion==='expediente'){if(modo.guardar==='rechaza')return route.fulfill({json:{error:'solo el agente'}});hoja[d.pieza]=d.expediente;}
    return route.fulfill({json:{ok:true}});}
   if(u.hostname==='script.google.com'){
    const r=u.searchParams.get('recurso');
    if(r==='dia')return route.fulfill({json:dia('editor')});
    if(r==='expedientes'){if(modo.exp==='cae')return route.abort('failed');return route.fulfill({json:{ok:true,expedientes:hoja}});}
    if(r==='reglas')return route.fulfill({json:{ok:true,reglas:{nube_ejecuta_etapas:'prospecto',semillero_activo:'0'},motores:[]}});
    return route.fulfill({json:{ok:true,cola:[],fabrica:[],ideas:[]}});
   }
   return estatico(route,u,'editor');
  });
  const nombres=()=>page.locator('#salidaHoy .sal-carta b').allTextContents();
  const escrituras=async n=>{for(let i=0;i<80&&writes.length<n;i++)await page.waitForTimeout(100);assert.equal(writes.length,n);};
  const montonDe=n=>page.waitForFunction(k=>!document.querySelector('#salidaHoy .sal-nota')&&document.querySelectorAll('#salidaHoy .sal-carta').length===k,n,{timeout:30000});
  await page.goto(base);
  await aLista(page);await montonDe(2);
  // 1) en la hoja de una pieza lista: sin nota no se pide nada
  await page.locator('#salidaHoy [data-publicar="Pieza Uno"]').click();await page.waitForSelector('.sal-hoja');
  await page.locator('#salCambio').click();
  assert.equal(await page.locator('#salCambioN option').count(),3,'una opción por imagen');
  await page.locator('#salCambioOk').click();
  assert.match(await page.locator('#salCambioAviso').textContent(),/Escribe qué debe cambiar/);assert.equal(writes.length,0);
  // 2) con nota: UNA escritura a la llave de la pieza, con su versión y la imagen; la pieza sale del montón
  await page.locator('#salCambioN').selectOption('2');
  await page.locator('#salCambioNota').fill('  Más   luminosa\ny sin letrero ');
  await page.locator('#salCambioOk').click();await escrituras(1);
  const w=writes[0];
  assert.deepEqual([w.accion,w.pieza,w.clave,w.expediente.v,w.expediente.pieza,w.expediente.tira],['expediente','cambio:uno','synthetic',1,'Pieza Uno',PIEZAS[0][0]]);
  assert.deepEqual(w.expediente.ordenes.map(o=>[o.n,o.nota,o.por]),[[2,'Más luminosa y sin letrero','editor']]);
  assert.ok(!isNaN(Date.parse(w.expediente.ordenes[0].cuando)));
  await page.waitForFunction(()=>!document.querySelector('.sal-hoja'),null,{timeout:15000});await montonDe(1);
  assert.deepEqual(await nombres(),['Pieza Tres']);
  assert.equal(await page.locator('#salidaHoy h2').textContent(),'1 lista para lanzar');
  assert.match((await page.locator('#salidaHoy .sal-cambios').innerText()).replace(/\s+/g,' '),/^1 pieza fuera del montón por un cambio: Pieza Uno · imagen 2: «Más luminosa y sin letrero»\. Pedido a Producción con la nota del editor; suele tardar varias horas\. Quitar la petición$/);
  assert.match(await page.locator('#salidaHoy .sal-estado').textContent(),/Cambio pedido\. «Pieza Uno» sale de tu montón/);
  for(let i=0;i<40&&(await page.evaluate(()=>(JSON.parse(localStorage.getItem('sala_resumen_v1')||'{}')).listas))!==1;i++)await page.waitForTimeout(100);
  assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('sala_resumen_v1')).listas),1,'YOD OS cuenta lo que sí está en el montón');
  const caja=await page.locator('#salidaHoy .sal').boundingBox();assert.ok(caja.x>=0&&caja.x+caja.width<=width+1,'sin desbordar la pantalla');
  // 3) «Cómo va» dice que se está rehaciendo y ya no la cuenta como lista
  await page.locator('#puertas [data-v="prod"]').click();await page.waitForSelector('#linea .ln-fila',{timeout:30000});
  await page.waitForFunction(()=>[...document.querySelectorAll('#linea .ln-fila')].some(f=>/Cambio pedido en la imagen 2/.test(f.innerText)),null,{timeout:30000});
  const filas=Object.fromEntries(await page.evaluate(()=>[...document.querySelectorAll('#linea .ln-fila')].map(f=>[f.querySelector('.ln-nom b').textContent,f.querySelector('.ln-rel').innerText.replace(/\s+/g,' ')])));
  assert.match(filas['Pieza Uno'],/Cambio pedido en la imagen 2, con la nota del editor\./);
  assert.match(filas['Pieza Tres'],/Lista para lanzar: 1 imagen y su texto\./);
  await page.locator('#puertas [data-v="hoy"]').click();
  // 4) al recargar, la orden viene de la hoja
  await page.reload();await aLista(page);
  await page.waitForFunction(()=>!document.querySelector('#salidaHoy .sal-nota')&&!!document.querySelector('#salidaHoy .sal-cambios'),null,{timeout:30000});
  assert.deepEqual(await nombres(),['Pieza Tres']);
  // 5) desde la mesa: la página aprobada de una pieza de UNA imagen (su tira no tiene base) ya deja pedir cambio
  await page.locator('[data-abrir-mesa]').click();await page.waitForSelector('.bt-column');
  await page.locator('#tableroHoy [data-open="tres"]').click();await page.waitForSelector('#tableroHoy [data-frame="1"]');
  await page.locator('#tableroHoy [data-frame="1"]').click();await page.waitForSelector('.bt-choice [data-reopen]');
  assert.equal(await page.locator('.bt-choice [data-reopen]').isDisabled(),false);
  assert.match(await page.locator('.bt-choice .bt-gesture-hint').textContent(),/Si algo no te convence, pide un cambio con una nota/);
  await page.locator('.bt-choice [data-reopen]').click();await page.waitForSelector('#notaT');
  await page.locator('#notaT').fill('Cambia el texto: quita el plazo');await page.locator('#notaOk').click();await escrituras(2);
  assert.deepEqual([writes[1].accion,writes[1].pieza,writes[1].expediente.tira,writes[1].expediente.pieza,writes[1].expediente.ordenes.map(o=>[o.n,o.nota])],
   ['expediente','cambio:tres',PIEZAS[2][0],'Pieza Tres',[[1,'Cambia el texto: quita el plazo']]]);
  await page.waitForSelector('.bt-choice [data-unreopen]');
  assert.match((await page.locator('.bt-choice .bt-editor-note').last().innerText()).replace(/\s+/g,' '),/^CAMBIO PEDIDO Cambia el texto: quita el plazo$/i);
  assert.match(await page.locator('.bt-choice .bt-notice').textContent(),/Tu petición quedó guardada en el Sheet\./);
  assert.match(await page.locator('.bt-choice .bt-gesture-hint').textContent(),/^Cambio pedido: Producción rehace esta página con tu nota y te la trae para aprobar \(puede tardar varias horas\)\./);
  assert.equal(await page.locator('.bt-choice [data-reopen]').count(),0,'con la orden viva no se pide otra vez');
  assert.equal(await page.locator('#salidaHoy .sal-carta').count(),0,'las dos piezas salieron del montón');
  assert.equal(await page.locator('#salidaHoy .sal-cambios li').count(),2);
  // 6) quitar la petición desde la mesa: la página sigue aprobada y la pieza vuelve al montón
  await page.locator('.bt-choice [data-unreopen]').click();await escrituras(3);
  assert.deepEqual([writes[2].pieza,writes[2].expediente.tira,writes[2].expediente.ordenes],['cambio:tres',PIEZAS[2][0],[]]);
  await page.waitForSelector('.bt-choice [data-reopen]');
  assert.match(await page.locator('.bt-choice .bt-notice').textContent(),/Petición quitada/);
  await page.evaluate(()=>cerrarCapas());await montonDe(1);
  assert.deepEqual(await nombres(),['Pieza Tres']);
  // 7) quitar la otra desde el montón
  await page.locator('#salidaHoy [data-quitar-cambio="uno"]').click();await escrituras(4);
  assert.deepEqual([writes[3].pieza,writes[3].expediente.ordenes],['cambio:uno',[]]);
  await montonDe(2);
  assert.equal(await page.locator('#salidaHoy .sal-cambios').count(),0);
  assert.match(await page.locator('#salidaHoy .sal-estado').textContent(),/Petición quitada/);
  // 8) una llave que la hoja no deja escribir: se dice, no se da por pedido y la pieza sigue en el montón
  modo.guardar='rechaza';
  await page.locator('#salidaHoy [data-publicar="Pieza Tres"]').click();await page.waitForSelector('.sal-hoja');
  await page.locator('#salCambio').click();
  assert.equal(await page.locator('#salCambioN').count(),0,'con una sola imagen no hay nada que elegir');
  await page.locator('#salCambioNota').fill('Otra pareja');await page.locator('#salCambioOk').click();await escrituras(5);
  await page.waitForFunction(()=>/Tu llave todavía no puede pedir cambios/.test(document.querySelector('#salCambioAviso').textContent),null,{timeout:15000});
  assert.equal(await page.locator('.sal-hoja').count(),1);assert.equal(await page.locator('#salCambioOk').isDisabled(),false);
  await page.evaluate(()=>cerrarCapas());
  assert.deepEqual(await nombres(),['Pieza Uno','Pieza Tres']);assert.equal(await page.locator('#salidaHoy .sal-cambios').count(),0);
  // 8b) segunda vuelta: el registro ya es de la versión rehecha y trae `paquete` (la empacada). El paquete viejo NO vuelve al montón
  modo.guardar='ok';const REHECHA='uno-nube-2026-11-10-eeeeee',antesSV=writes.length;
  hoja['cambio:uno']={v:1,pieza:'Pieza Uno',tira:REHECHA,paquete:PIEZAS[0][0],ordenes:[{n:1,nota:'Segunda vuelta',cuando:'2026-11-10T05:00:00.000Z',por:'editor'}],cuando:'2026-11-10T05:00:00.000Z',por:'editor'};
  await page.reload();await aLista(page);
  await page.waitForFunction(()=>!document.querySelector('#salidaHoy .sal-nota')&&!!document.querySelector('#salidaHoy .sal-cambios'),null,{timeout:30000});
  assert.deepEqual(await nombres(),['Pieza Tres'],'el paquete viejo no se ofrece como listo');
  const pie=()=>page.locator('#salidaHoy .sal-cambios').innerText().then(t=>t.replace(/\s+/g,' '));
  assert.match(await pie(),/Pieza Uno · imagen 1: «Segunda vuelta»/);
  const ponMesa=v=>page.evaluate(async v=>{window.__mesaPid=s=>s==='uno'?v:(window.__mesaMapa[s]||null);await SalaSalida.pintar()},v);
  // con la mesa sin saber su versión no se quita nada (no se puede confirmar que Producción no la haya rehecho) y no se escribe
  await ponMesa(null);
  assert.equal(await page.locator('#salidaHoy [data-quitar-cambio]').count(),0,'sin confirmación de la mesa no hay botón de quitar');
  assert.equal((await page.evaluate(()=>SalaSalida.quitarCambio('uno',1))).motivo,'No pude confirmar con tu mesa si Producción ya la rehízo. Actualiza e inténtalo otra vez.');
  assert.equal(writes.length,antesSV,'quitar sin confirmación no escribe');
  // F2: una orden viva de segunda vuelta no se pisa desde el paquete viejo con la mesa sin saber
  assert.equal((await page.evaluate(t=>SalaSalida.pedirCambio({slug:'uno',pieza:'Pieza Uno',tira:t,n:2,nota:'Otra imagen'}),PIEZAS[0][0])).motivo,'Esta pieza ya tiene un cambio pedido sobre otra versión. Pídelo desde tu mesa, en la versión que está ahí.');
  assert.equal(writes.length,antesSV,'pedir sobre otra versión no escribe');
  // la mesa enseña la versión rehecha, sin paquete nuevo: Producción aún no la atiende → se puede quitar
  await ponMesa(REHECHA);
  assert.match(await pie(),/Pedido a Producción con la nota del editor; suele tardar varias horas\. Quitar la petición$/);
  // F1: con el cambio pedido el paquete viejo no se ofrece para publicar ni para pedir otro cambio
  const fuera=async txt=>{await page.evaluate(()=>SalaSalida.abrir('Pieza Uno'));await page.waitForSelector('.sal-hoja');
    assert.equal(await page.locator('#salYa').count(),0,'sin «Ya la publiqué»');assert.equal(await page.locator('#salCambio').count(),0,'sin «Pedir cambio a una imagen»');
    assert.equal((await page.locator('.sal-fuera').innerText()).trim(),txt);await page.evaluate(()=>cerrarCapas())};
  await fuera('Esta pieza tiene un cambio pedido: este paquete ya no es el que va a salir.');
  // la mesa ya trae una versión todavía más nueva: 'volvio', sin botón de quitar
  await ponMesa('uno-nube-2026-11-11-ffffff');
  assert.match(await pie(),/Hay una versión nueva: cuando esté aprobada y con su paquete nuevo, vuelve aquí\./);
  assert.equal(await page.locator('#salidaHoy [data-quitar-cambio]').count(),0,'lo que ya se rehízo no se quita desde el montón');
  await fuera('Hay una versión nueva de esta pieza: este paquete ya no es el que va a salir.');
  assert.deepEqual(await nombres(),['Pieza Tres']);
  assert.equal((await page.evaluate(()=>SalaSalida.quitarCambio('uno',1))).motivo,'Producción ya la rehízo: decide la versión nueva en tu mesa.');
  assert.equal((await page.evaluate(()=>SalaSalida.quitarCambio('uno',7))).motivo,'Esa petición ya no está.');
  assert.deepEqual(await page.evaluate(()=>SalaSalida.cambioDePieza('Pieza Uno','uno').estado),'volvio');
  // pedir cambio sobre una versión que ya no es la vigente en la mesa
  assert.equal((await page.evaluate(t=>SalaSalida.pedirCambio({slug:'uno',pieza:'Pieza Uno',tira:t,n:1,nota:'x'}),PIEZAS[0][0])).motivo,'Esa versión ya no es la vigente: la versión nueva está en tu mesa.');
  await ponMesa(null);
  // motivos de rechazo, en su orden (ninguno escribe)
  const pide=o=>page.evaluate(o=>SalaSalida.pedirCambio(o),o), T3=PIEZAS[2][0];
  assert.equal((await pide({slug:'tres',pieza:'Pieza Tres',tira:'../x',n:1,nota:'x'})).motivo,'No pude identificar la pieza o su versión. Actualiza la página e inténtalo otra vez.');
  assert.equal((await pide({slug:'tres',pieza:'Pieza Tres',tira:T3,n:0,nota:'x'})).motivo,'No pude identificar la imagen.');
  assert.equal((await pide({slug:'tres',pieza:'Pieza Tres',tira:T3,n:1,nota:'   '})).motivo,'Escribe qué debe cambiar.');
  // H2: registro de segunda vuelta SIN órdenes (quitadas): la pieza no vuelve al montón y su nombre sigue en el pie
  hoja['cambio:uno']={v:1,pieza:'Pieza Uno',tira:REHECHA,paquete:PIEZAS[0][0],ordenes:[]};
  await page.reload();await aLista(page);
  await page.waitForFunction(()=>!document.querySelector('#salidaHoy .sal-nota')&&!!document.querySelector('#salidaHoy .sal-cambios'),null,{timeout:30000});
  assert.equal(await page.locator('#salidaHoy .sal-carta[data-publicar="Pieza Uno"]').count(),0);
  assert.equal(await page.locator('#salidaHoy .sal-cambios li').count(),1,'un renglón por pieza');
  assert.match(await pie(),/^1 pieza fuera del montón por un cambio.*Pieza Uno\. Hay una versión nueva/);
  assert.equal(await page.locator('#salidaHoy [data-quitar-cambio]').count(),0);
  // H5: dos registros de la misma pieza (llaves distintas): manda el que la oculta
  hoja['cambio:uno']={v:1,pieza:'Pieza Uno',tira:PIEZAS[0][0],paquete:PIEZAS[0][0],ordenes:[]};
  hoja['cambio:uno-viejo']={v:1,pieza:'Pieza Uno',tira:PIEZAS[0][0],paquete:PIEZAS[0][0],ordenes:[{n:2,nota:'La otra llave',cuando:'2026-11-10T05:00:00.000Z',por:'editor'}]};
  await page.reload();await aLista(page);
  await page.waitForFunction(()=>!document.querySelector('#salidaHoy .sal-nota')&&!!document.querySelector('#salidaHoy .sal-cambios'),null,{timeout:30000});
  assert.deepEqual(await nombres(),['Pieza Tres'],'gana el registro que oculta');
  assert.match(await pie(),/Pieza Uno · imagen 2: «La otra llave»/);
  delete hoja['cambio:uno-viejo'];delete hoja['cambio:uno'];
  // H4: el nombre que manda la mesa no es la llave del expediente: el paquete se halla por su slug
  await page.reload();await aLista(page);await montonDe(2);
  const antesH4=writes.length;
  assert.equal((await pide({slug:'tres',pieza:'Nombre que no es llave',tira:T3,n:1,nota:'x'})).ok,true);
  await escrituras(antesH4+1);
  assert.equal(writes[antesH4].expediente.paquete,T3,'`paquete` = el id del paquete de ese slug');
  hoja['cambio:tres']={v:1,pieza:'Pieza Tres',tira:T3,paquete:T3,ordenes:[]};
  // F5: una pieza SIN paquete (como «Las 48 Horas») con orden viva aparece como renglón en el pie
  hoja['cambio:dos']={v:1,pieza:'Pieza Dos',tira:PIEZAS[1][0],paquete:'',ordenes:[{n:1,nota:'Sin paquete aún',cuando:'2026-11-10T05:00:00.000Z',por:'editor'}]};
  await page.reload();await aLista(page);
  await page.waitForFunction(()=>!document.querySelector('#salidaHoy .sal-nota')&&!!document.querySelector('#salidaHoy .sal-cambios'),null,{timeout:30000});
  assert.match(await pie(),/Pieza Dos · imagen 1: «Sin paquete aún»\. Pedido a Producción con la nota del editor; suele tardar varias horas\. Quitar la petición/);
  assert.equal(await page.locator('#salidaHoy .sal-carta[data-publicar="Pieza Dos"]').count(),0);
  delete hoja['cambio:dos'];
  // (b) una pieza publicada no ofrece pedir cambio y se rechaza con su motivo
  await page.evaluate(()=>localStorage.setItem('sala_publicadas_v1',JSON.stringify({'Pieza Tres':{fecha:'2026-11-09',liga:'',sello:'3'.repeat(12)}})));
  assert.deepEqual(await page.evaluate(()=>[SalaSalida.puedePedirCambio(),SalaSalida.puedePedirCambio('Pieza Tres'),SalaSalida.puedePedirCambio('Pieza Uno')]),[true,false,true]);
  assert.equal((await pide({slug:'tres',pieza:'Pieza Tres',tira:T3,n:1,nota:'x'})).motivo,'Esta pieza ya está publicada: no se rehace.');
  await page.evaluate(()=>SalaSalida.abrir('Pieza Tres'));await page.waitForSelector('.sal-hoja');
  assert.equal(await page.locator('#salCambio').count(),0,'una pieza publicada no ofrece «Pedir cambio a una imagen»');
  assert.equal(await page.locator('#salYa').count(),0);
  await page.evaluate(()=>{localStorage.removeItem('sala_publicadas_v1');cerrarCapas()});
  // (c) sin la hoja leída no se pide ni se quita nada
  const antesC=writes.length;modo.exp='cae';await page.reload();await page.waitForSelector('#salidaHoy .sal-nota [data-releer]',{timeout:30000});await aLista(page);
  assert.equal(await page.evaluate(()=>SalaSalida.puedePedirCambio()),false);
  assert.equal((await pide({slug:'tres',pieza:'Pieza Tres',tira:T3,n:1,nota:'x'})).motivo,'Todavía no se puede pedir el cambio: falta que conteste el Sheet.');
  assert.equal((await page.evaluate(()=>SalaSalida.quitarCambio('uno',1))).motivo,'Todavía no se puede quitar la petición: falta que conteste el Sheet.');
  assert.equal(await page.locator('#salidaHoy [data-quitar-cambio]').count(),0);
  assert.equal(writes.length,antesC,'nada de lo anterior escribe');
  modo.exp='ok';
  // 9) nunca decide ni publica: sólo escribió órdenes de cambio
  assert.deepEqual([...new Set(writes.map(x=>x.accion))],['expediente']);
  assert.ok(writes.every(x=>/^cambio:(uno|tres)$/.test(x.pieza)));
  if(process.env.SALIDA_CAPTURAS){fs.mkdirSync(process.env.SALIDA_CAPTURAS,{recursive:true});await page.screenshot({path:path.join(process.env.SALIDA_CAPTURAS,'cambio-'+width+'.png')});}
  assert.deepEqual(errors,[]);console.log(JSON.stringify({width,recorrido:'cambio',errors:0,realWrites:0,ordenes:writes.length}));
  await context.close();
 }}finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
