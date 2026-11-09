/* Salida de la Sala corta en el navegador: lo listo para publicar, la hoja de publicar y «Ya la publiqué».
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

(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const base='http://127.0.0.1:'+server.address().port+'/';
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
  });
  await page.goto(base);
  // «Te toca» abre con lo listo para publicar, lo que espera texto y lo guardado por regla
  await page.waitForSelector('#salidaHoy .sal-carta',{timeout:30000});
  await page.waitForFunction(()=>document.querySelectorAll('#salidaHoy .sal-pie').length===2,null,{timeout:30000});
  assert.equal(await page.locator('#salidaHoy h2').textContent(),'1 lista para publicar');
  const pies=await page.locator('#salidaHoy .sal-pie').allTextContents();
  assert.match(pies[0],/^2 piezas más ya tienen sus imágenes aprobadas y esperan su texto/);
  assert.match(pies[1],/^1 pieza guardada hasta que tú decidas: Pieza Tres\./);
  assert.equal(await page.locator('#salidaHoy .sal-ir').textContent(),rol==='editor'?'Publicar →':'Ver →');
  assert.ok(await page.locator('#salidaHoy .sal-foto img').evaluate(i=>i.complete&&i.naturalWidth>0),'la portada del paquete se ve');
  const box=await page.locator('#salidaHoy .sal').boundingBox();assert.ok(box.x>=0&&box.x+box.width<=width+1,'sin desbordar la pantalla');

  // «Cómo va» ya no queda tapado por la mesa y cuenta la verdad de cada pieza
  await page.locator('#puertas [data-v="prod"]').click();
  await page.waitForSelector('#linea .ln-fila',{timeout:30000});
  assert.equal(await page.locator('#vHoy').evaluate(e=>getComputedStyle(e).display),'none','la mesa no tapa «Cómo va»');
  const filas=Object.fromEntries(await page.evaluate(()=>[...document.querySelectorAll('#linea .ln-fila')].map(f=>[f.querySelector('.ln-nom b').textContent,f.querySelector('.ln-rel').innerText.replace(/\s+/g,' ')])));
  assert.match(filas['Pieza Uno'],/PUBLÍCALA Lista para publicar: 3 imágenes y su texto\./i);
  assert.match(filas['Pieza Dos'],/Imágenes aprobadas\. Falta su texto\./);
  assert.match(filas['Pieza Tres'],/Guardada: no sale hasta que tú lo digas/);
  assert.match(filas['Pieza Cuatro'],/Imágenes aprobadas\. Falta su texto\./,'con el video en pausa, lo que nació para video camina como carrusel');
  assert.equal(await page.locator('#linea .ln-fila').first().locator('.ln-nom b').textContent(),'Pieza Uno','lo listo para publicar va primero');
  assert.match(await page.locator('#linea .rel').textContent(),/4 publicaciones abiertas\. 1 está lista para publicar, 2 con imágenes aprobadas esperan su texto, 1 está guardada y espera tu decisión\./);
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
   assert.equal(writes.length,0);
  }else{
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
   assert.equal(await page.locator('#salidaHoy h2').textContent(),'Todavía no hay nada listo para publicar');
   assert.equal(writes.length,1,'recargar no repite la anotación');
   assert.ok(!writes.some(x=>x.accion==='decidir'));
  }
  if(process.env.SALIDA_CAPTURAS&&rol==='editor'){fs.mkdirSync(process.env.SALIDA_CAPTURAS,{recursive:true});await page.screenshot({path:path.join(process.env.SALIDA_CAPTURAS,'salida-'+width+'.png')});}
  assert.deepEqual(errors,[]);console.log(JSON.stringify({width,rol,errors:0,realWrites:0,interceptedWrites:writes.length}));
  await context.close();
 }}finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
