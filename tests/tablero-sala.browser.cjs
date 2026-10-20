/* Recorrido aislado: sólo datos sintéticos; ninguna escritura en Google. */
const {chromium}=require("playwright"),assert=require("node:assert/strict"),fs=require("node:fs"),crypto=require("node:crypto");
const out="tests/evidencia-tablero";fs.mkdirSync(out,{recursive:true});
const base=(process.env.SALA_TEST_URL||'http://127.0.0.1:8765/').replace(/\/?$/,'/');
const chincheSource=fs.readFileSync(process.env.SALA_CHINCHE_SOURCE||'../atlas/chinche.js','utf8');
const titles=["Tres perspectivas","Doble camino","El diseño invisible","Ruta propia","El entregable","La mesa"];
const tiras={};const propuestas=titles.map((pieza,k)=>{
 const id="synthetic-"+k;
 tiras[id]={pieza,pieza_slug:id,base:id+"-base",promesa:"Entender la decisión de diseño",decidir:[2,3,4,5,6],mapa:{"1":2,"2":3,"3":4,"4":5,"5":6},
 laminas:Array.from({length:6},(_,i)=>({n:i+1,src:"laminas/"+id+"/L"+(i+1)+".jpg",dice:"Una decisión concreta para la lámina "+(i+1),ve:"Personas comparan maquetas sobre una mesa",estado:i===0?"aprobada":"rehecha",
 version:i===1?7:1,versiones:i===1?Array.from({length:7},(_,v)=>({v:v+1,src:"laminas/"+id+"/v"+(v+1)+".png",marca:v===0?"no":""})):[],
 candidatas:i===1?[{src:"laminas/"+id+"/bad.jpg",motor:"cpu"},{src:"laminas/"+id+"/L2.jpg",motor:"hidream_demo",modelo:"HiDream-I1-Dev",titulo:"A",dice:"Texto específico de la toma A"},{src:"laminas/"+id+"/B.jpg",motor:"hidream_demo",modelo:"HiDream-I1-Dev",titulo:"B",dice:"Texto específico de la toma B"}]:[]}))};
 return {id,tipo:"laminas",pieza,titulo:pieza,laminas:tiras[id].laminas.slice(1).map(x=>x.src)};
});
function day(role){return {fecha:"2026-10-13",rol:role,quien:"Alejandro",version:"synthetic",propuestas:JSON.parse(JSON.stringify(propuestas)),decisiones:{editores:[],propuestas:{}}};}
const svg='<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1350"><rect width="1080" height="1350" fill="#c5b7a3"/><rect x="90" y="480" width="900" height="360" rx="30" fill="#f5edde"/><path d="M180 750 440 550 650 710 870 610" stroke="#b88159" stroke-width="35" fill="none"/><circle cx="330" cy="300" r="90" fill="#565b54"/><circle cx="720" cy="300" r="85" fill="#626964"/></svg>';
const jpegSamples=[
 '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBT/wAARCABaAEgDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAf/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAf/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwClgJUoAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/2Q==',
 '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBT/wAARCABaAEgDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAb/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFgEBAQEAAAAAAAAAAAAAAAAAAAQG/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwDAQACEQMRAD8AnwE7HgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/9k='
].map(x=>Buffer.from(x,'base64'));
const mediaManifest={schema:1,repo:'yodesarrollomx/sala-edicion',entries:{}},mediaAssets=new Map();
for(const [i,name] of ['L2','B'].entries()){
 const bytes=jpegSamples[i],sha=crypto.createHash('sha256').update(bytes).digest('hex'),tag='sala-media-'+'b'.repeat(64)+'-mesa';
 const url='https://github.com/yodesarrollomx/sala-edicion/releases/download/'+tag+'/'+sha+'.jpg';
 mediaManifest.entries['laminas/synthetic-0/'+name+'.jpg']={sha256:sha,bytes:bytes.length,mime:'image/jpeg',release_id:101,asset_id:201+i,tag,url};
 mediaAssets.set(url,bytes);
}
const mediaRaw=JSON.stringify(mediaManifest),mediaPin=crypto.createHash('sha256').update(mediaRaw).digest('hex');
async function prepare(browser,width,role="editor",mobile=false,embedded=false,media={mode:'legacy'}){
 const context=await browser.newContext({viewport:{width,height:mobile?844:1000},isMobile:mobile,hasTouch:mobile});
 const page=await context.newPage(),writes=[],errors=[],releaseReads=[];
 const visibleDay=()=>{
  const value=media.emptyDay?{...day(role),propuestas:[]}:day(role);
  if(media.cuts)value.propuestas.push(...[0,1,9].map(n=>({id:'synthetic-cut-'+n,tipo:'eje',titulo:'REEL · Pieza '+n+' · corte completo · para revisar',origen:'corte-de synthetic-'+n,laminas:[],opciones:{candidatas:[{titulo:'Conservar este corte'}]}})));
  return value;
 };
 page.on("pageerror",e=>errors.push(String(e)));
 await page.addInitScript(({role})=>{
  window.SpeechRecognition=class{constructor(){window.__dictado=this;}start(){}stop(){this.onend&&this.onend();}};

  localStorage.setItem("sala_clave","synthetic-session-key");localStorage.setItem("sala_rol",role);
  localStorage.setItem("sala_guia_v3","1");localStorage.setItem("sala_guia","1");
 },{role});
 await page.route("**/*",async route=>{
  const req=route.request(),u=new URL(req.url());
  if(u.pathname==='/yod-portal/chinche.js'){await route.fulfill({contentType:'application/javascript',body:chincheSource});return;}

  if(u.hostname==="script.google.com"||u.hostname==="script.googleusercontent.com"){
   if(req.method()==="POST"){const body=JSON.parse(req.postData()||"{}");writes.push(body);await route.fulfill({json:{ok:true}});return;}
   const resource=u.searchParams.get("recurso");
   await route.fulfill({json:resource==="dia"?visibleDay():resource==="cola"?{ok:true,cola:[{pieza:"synthetic-1",etapa:"voz",estado:"corriendo",item:"2"}]}:resource==="entrada"?{ok:true,rol:role}: {ok:true,reglas:{},propuestas:[]}});return;
  }
  if(mediaAssets.has(req.url())){releaseReads.push(req.url());await route.fulfill({contentType:'image/jpeg',body:mediaAssets.get(req.url())});return;}
  if(u.hostname!=="127.0.0.1"){await route.fulfill({status:200,contentType:req.resourceType()==="stylesheet"?"text/css":"application/javascript",body:""});return;}
  if(u.pathname==='/version-online.json'){await route.fulfill({json:media.mode==='legacy'?{}:{media_manifest_sha256:media.mode==='badpin'?'0'.repeat(64):mediaPin}});return;}
  if(u.pathname==='/datos/medios-publicos.json'){
   if(media.mode==='legacy'||media.mode==='missing'){await route.fulfill({status:404,body:''});return;}
   await route.fulfill({contentType:'application/json',body:mediaRaw});return;
  }
  if(/\/laminas\/.*\.(jpg|png)$/.test(u.pathname)){await route.fulfill({contentType:"image/svg+xml",body:svg});return;}
  if(u.pathname==="/fixture-parent"){await route.fulfill({contentType:"text/html",body:'<html><body style="margin:0"><iframe src="/?embed=1&clasica=1" style="width:100%;height:650px;border:0" title="Sala en el portal"></iframe></body></html>'});return;}
  if(u.pathname.includes("/datos/")){
   let value={};
   if(u.pathname==="/datos/mesa-estado.json"&&media.emptyDay)value={revisado_en:new Date().toISOString(),publicaciones:Object.entries(tiras).map(([id,t])=>({id,laminas:t.laminas.map(l=>({n:l.n,estado:"aprobada",...(l.n===2?{toma:3}:{})}))}))};
   else if(u.pathname==="/datos/manifiesto.json")value=visibleDay();
   else if(u.pathname==="/datos/tiras/index.json")value=Object.keys(tiras);
   else if(u.pathname.startsWith("/datos/tiras/"))value=tiras[u.pathname.split("/").pop().replace(".json","")]||{};
   else if(u.pathname==="/datos/piezas.json")value={};
   else if(u.pathname.endsWith("/index.json"))value=[];
   await route.fulfill({json:value});return;
  }
  await route.continue();
 });
 await page.goto(base+(embedded?"fixture-parent":"?clasica=1"));
 const view=embedded?page.frames().find(f=>f.parentFrame()):page;
 await view.waitForSelector(".bt-column",{timeout:30000});
 await view.waitForFunction(()=>!document.querySelector("[data-refresh]")?.disabled&&!document.querySelector(".bt-local"));
 // La bienvenida, si estaba visible, se cierra con su botón sin tocar datos.
 await view.evaluate(()=>{if(typeof cerrarCapas==="function")cerrarCapas();});
 return {page,view,context,writes,errors,releaseReads};
}
const sessions=new WeakMap();
async function touch(page,points,type){let session=sessions.get(page);if(!session){session=await page.context().newCDPSession(page);sessions.set(page,session);}await session.send("Input.dispatchTouchEvent",{type,touchPoints:points.map((p,i)=>({id:i+1,...p}))});}
(async()=>{
 const b=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH,args:["--no-sandbox"]}:{})});
 try{
  // Corte y fuente comparten columna por identidad, aun con prefijo REEL común.
  const cuts=await prepare(b,1440,'editor',false,false,{mode:'legacy',cuts:true});
  for(const n of [0,1])assert.equal(await cuts.page.locator('[data-column="synthetic-'+n+'"] [data-eje="synthetic-cut-'+n+'"]').count(),1);
  assert.equal(await cuts.page.locator('[data-column="corte:synthetic-cut-9"] [data-eje="synthetic-cut-9"]').count(),1);
  assert.equal(await cuts.page.locator('[data-column="reel"]').count(),0);
  assert.equal(cuts.writes.length,0);assert.deepEqual(cuts.errors,[]);
  await cuts.context.close();
  // Compositor real, micrófono sintético y endpoint de negocio interceptado.
  const capture=await prepare(b,390,'editor',true),cp=capture.page;
  await cp.waitForFunction(()=>window.YODChinche);
  await cp.locator('[data-open="synthetic-0"]').click();await cp.locator('[data-lamina="2"]').click();
  await cp.locator('[data-next-option]').click();
  assert.equal((await cp.evaluate(()=>SalaTablero.contexto())).toma,2);
  await cp.evaluate(()=>YODChinche.anotar({sinCaptura:true,css:'.bt-main-photo'}));
  await cp.locator('.chn-mic').click();
  await cp.evaluate(()=>window.__dictado.onresult({results:[Object.assign([{transcript:'Corregir el fondo'}],{isFinal:true}),Object.assign([{transcript:'parcial no enviar'}],{isFinal:false})]}));
  assert.equal(await cp.locator('.chn-txt').inputValue(),'Corregir el fondo');
  await cp.locator('[data-ok]').click();assert.equal(capture.writes.length,0);
  await cp.locator('[data-ok]').click();assert.equal(capture.writes.length,0);
  // Cambia la navegación subyacente: el sobre conserva la toma originalmente señalada.
  await cp.evaluate(()=>document.querySelector('[data-prev-option]').click());
  assert.equal(await cp.locator('.chn-aviso:visible').count(),1,'los avisos de revisión no se superponen');
  await cp.screenshot({path:out+'/00-correccion-dictada.png',fullPage:true});
  await cp.locator('[data-ok]').click();
  await cp.waitForFunction(()=>JSON.parse(localStorage.getItem('sala_produccion_v1')||'[]').some(r=>r.estado==='recibido'));
  const produced=capture.writes.filter(x=>x.accion==='produccion');assert.equal(produced.length,1);
  const note=JSON.parse(produced[0].detalle);assert.equal(note.carta.pid,'synthetic-0');assert.equal(note.carta.lamina,2);assert.equal(note.carta.version,7);assert.equal(note.carta.toma,2);assert.equal(note.captura.texto_revisado,true);
  assert.equal(capture.writes.filter(x=>x.accion==='decidir').length,0,'clavar no aprueba');
  assert.equal(capture.errors.length,0,capture.errors.join('\n'));await capture.context.close();
  // Preselección real de UI: recarga del mismo navegador, cero efectos de negocio.
  for(const width of [1440,390]){
   const shortlist=await prepare(b,width,'editor',width===390),sp=shortlist.page;
   async function abrirFinalistas(){await sp.locator('[data-open="synthetic-0"]').click();await sp.locator('[data-lamina="2"]').click();}
   await abrirFinalistas();
   await sp.locator('[data-finalista="0"]').click();await sp.locator('[data-finalista="1"]').click();
   assert.equal(await sp.locator('[data-finalista][aria-pressed="true"]').count(),2);
   assert.equal(shortlist.writes.length,0);
   await sp.reload();await sp.waitForSelector('.bt-column');await sp.evaluate(()=>cerrarCapas());await abrirFinalistas();
   assert.equal(await sp.locator('[data-finalista][aria-pressed="true"]').count(),2);
   const finalStyle=await sp.locator('[data-finalista]').first().evaluate(el=>({bg:getComputedStyle(el).backgroundColor,color:getComputedStyle(el).color}));
   assert.equal(finalStyle.bg,'rgb(35, 78, 66)','finalistas seleccionadas deben contrastar con texto blanco');
   assert.equal(finalStyle.color,'rgb(255, 255, 255)');
   await sp.locator('[data-next-option]').click();
   assert.equal(await sp.locator('.bt-choice-copy h2').innerText(),'Texto específico de la toma B');
   await sp.locator('[data-compare]').click();
   await sp.screenshot({path:out+'/00-finalistas-'+width+'.png',fullPage:true});
   assert.ok(await sp.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1));
   await sp.locator('[data-finalista="0"]').click();
   assert.equal(await sp.locator('[data-finalista][aria-pressed="true"]').count(),1);
   assert.equal(shortlist.writes.length,0,'preseleccionar, comparar y recargar nunca votan ni producen');
   assert.deepEqual(shortlist.errors,[]);await shortlist.context.close();
  }
  const d=await prepare(b,1440),p=d.page;
  assert.equal(await p.locator(".bt-column").count(),6);
  assert.equal(await p.locator(".bt-frame").count(),36);
  assert.equal(await p.locator(".bt-frame.verde").count(),6);
  assert.ok(await p.locator(".bt-attempts").first().isVisible());
  await p.waitForSelector(".bt-counts .bt-dot.produccion");
  await p.screenshot({path:out+"/01-tablero-desktop.png",fullPage:true});
  await p.locator('[data-open="synthetic-0"]').click();
  await p.waitForSelector('#tableroHoy[data-level="publicacion"]');
  assert.equal(await p.locator(".bt-frame").count(),6);
  await p.locator('[data-info="intencion"]').click();
  await p.waitForSelector('.velo[data-id="tablero-intencion"]');
  assert.match(await p.locator('.velo[data-id="tablero-intencion"]').innerText(),/Entender la decisión/);
  await p.keyboard.press("Escape");
  await p.locator('[data-history="2"]').click();
  await p.waitForSelector('.velo[data-id="tablero-historial"]');
  assert.match(await p.locator('.velo[data-id="tablero-historial"]').innerText(),/10 intentos/);
  assert.equal(await p.locator('.velo[data-id="tablero-historial"] img[src*="bad"]').count(),0);
  await p.keyboard.press("Escape");
  await p.locator('[data-info="guion"]').click();
  await p.waitForSelector('.velo[data-id="guia-tira"]');
  assert.equal(await p.locator('.velo[data-id="guia-tira"] .sb-cuadro').count(),6);
  await p.keyboard.press("Escape");
  await p.waitForSelector('#tableroHoy[data-level="publicacion"]');
  await p.screenshot({path:out+"/02-publicacion-desktop.png",fullPage:true});
  await p.locator('[data-lamina="2"]').click();
  await p.waitForSelector(".bt-choice");
  assert.match(await p.locator(".bt-pager").innerText(),/1 de 2/);
  assert.equal(await p.locator('.bt-image-stage figure').count(),2,'escritorio compara al abrir');
  assert.equal(d.writes.length,0,'comparar no guarda ninguna decisión');
  await p.screenshot({path:out+'/03-comparacion-editorial.png',fullPage:true});
  await p.locator('[data-compare]').click();
  await p.locator('[data-page="3"]').click();
  assert.equal(await p.locator('[data-page="3"]').getAttribute('aria-current'),'page');
  await p.locator('[data-page="2"]').click();
  assert.equal(d.writes.length,0,'cambiar de página no decide');
  await p.locator("[data-full-photo]").click();
  await p.waitForSelector(".zoom.galeria .zg");
  await p.locator(".zoom .zg-sig").click();
  await p.waitForFunction(()=>document.querySelector(".zoom img")?.naturalWidth>0);
  assert.match(await p.locator(".zoom .zg-cual").innerText(),/2 de 2/);
  assert.equal(d.writes.filter(x=>x.accion==="decidir").length,0);
  await p.keyboard.press("ArrowLeft");assert.match(await p.locator(".zoom .zg-cual").innerText(),/1 de 2/);
  await p.keyboard.press("ArrowRight");assert.match(await p.locator(".zoom .zg-cual").innerText(),/2 de 2/);
  await p.waitForFunction(()=>document.querySelector(".zoom img")?.naturalWidth>0);
  await p.locator(".zoom .zg-elegir").click();
  await p.waitForFunction(()=>document.querySelector('[data-page="3"]')?.getAttribute("aria-current")==="page");
  assert.equal(d.writes.filter(x=>x.accion==="decidir").length,1);
  const chosen=d.writes.find(x=>x.accion==="decidir").propuestas["synthetic-0"];
  assert.equal(chosen.laminas[0],"si");
  assert.match(chosen.notas[0],/\[toma elegida: 3\]/);
  assert.notEqual(chosen.laminas[1],"si");
  await p.screenshot({path:out+"/03-carrusel-desktop.png",fullPage:true});
  await p.locator("[data-close-choice]").click();
  await p.waitForSelector('#tableroHoy[data-level="publicacion"]');
  await p.locator('[data-lamina="3"]').click();
  await p.locator('[data-vote="no"]').click();
  await p.locator("#notaT").fill("Cambiar sólo la iluminación");
  await p.locator("#notaOk").click();
  await p.waitForFunction(()=>document.querySelector(".bt-choice-copy .bt-dot")?.textContent==="Cambio pedido");
  assert.equal(d.writes.filter(x=>x.accion==="decidir").length,2);
  assert.equal(d.writes.filter(x=>x.accion==="decidir")[1].propuestas["synthetic-0"].laminas[1],"no");
  await p.locator("[data-close-choice]").click();
  await p.waitForSelector('#tableroHoy[data-level="publicacion"]');
  await p.keyboard.press("Escape");
  await p.waitForSelector('#tableroHoy[data-level="tablero"]');
  assert.equal(await p.locator(".bt-column").count(),6);
  assert.deepEqual(d.errors,[]);
  await d.context.close();

  const m=await prepare(b,390,"editor",true),q=m.page;
  assert.ok(await q.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1));
  assert.equal(await q.locator('.bt-frames').first().evaluate(el=>getComputedStyle(el).display),'flex');
  assert.ok(await q.locator('.bt-frames').first().evaluate(el=>el.scrollWidth>el.clientWidth),'la mesa móvil conserva la tira horizontal');
  await q.screenshot({path:out+"/04-tablero-movil.png",fullPage:true});
  await q.locator('[data-open="synthetic-0"]').click();
  await q.locator('[data-lamina="2"]').click();
  await q.waitForFunction(()=>document.querySelector(".bt-main-photo")?.naturalWidth>0);
  assert.equal(await q.locator(".bt-image-stage figure").count(),1,"móvil abre una toma legible");
  const h=await q.locator(".bt-hero").boundingBox(),x=Math.round(h.x+h.width/2),y=Math.round(h.y+h.height*.75);
  await touch(q,[{x,y}],"touchStart");
  await touch(q,[{x,y:y-130}],"touchMove");
  await touch(q,[],"touchEnd");
  assert.equal(m.writes.filter(x=>x.accion==="decidir").length,0,"deslizar hacia arriba sólo desplaza; no aprueba");
  await q.locator("[data-vote=si]").click();
  await q.waitForFunction(()=>document.querySelector('[data-page="3"]')?.getAttribute("aria-current")==="page");
  assert.equal(m.writes.filter(x=>x.accion==="decidir").length,1);
  await q.screenshot({path:out+"/05-carrusel-movil.png",fullPage:true});
  await q.locator("[data-close-choice]").click();
  await q.waitForSelector('#tableroHoy[data-level="publicacion"]');
  await q.locator('.bt-pan').evaluate(el=>el.scrollIntoView({block:'start'}));
  const area=await q.locator(".bt-pan").boundingBox(),cx=Math.round(area.x+area.width/2),cy=Math.round(Math.max(0,area.y)+80);
  assert.ok(await q.evaluate(({x,y})=>!!document.elementFromPoint(x,y)?.closest('.bt-pan'),{x:cx,y:cy}),'el gesto empieza en una superficie visible del tablero');
  await touch(q,[{x:cx-80,y:cy},{x:cx+80,y:cy}],"touchStart");
  await touch(q,[{x:cx-40,y:cy},{x:cx+40,y:cy}],"touchMove");
  await touch(q,[],"touchEnd");
  await q.waitForSelector('#tableroHoy[data-level="tablero"]');
  assert.deepEqual(m.errors,[]);
  await m.context.close();

  const embedded=await prepare(b,820,"editor",false,true),frame=embedded.view;
  assert.equal(await frame.locator(".bt-column").count(),6);
  await frame.locator('[data-open="synthetic-0"]').click();await frame.locator('[data-lamina="2"]').click();
  await frame.waitForSelector(".bt-choice");
  assert.ok(await frame.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await embedded.page.screenshot({path:out+"/06-sala-en-portal.png",fullPage:true});
  assert.deepEqual(embedded.errors,[]);await embedded.context.close();
  for(const role of ["lector","agente"]){
   const r=await prepare(b,390,role,true),page=r.page;
   await page.locator('[data-open="synthetic-0"]').click();await page.locator('[data-lamina="2"]').click();
   assert.ok(await page.locator('[data-vote="si"]').isDisabled());assert.ok(await page.locator('[data-vote="no"]').isDisabled());
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1),'El aviso largo de sólo lectura no debe ensanchar el viewport');
   await page.locator('[data-full-photo]').scrollIntoViewIfNeeded();
   assert.equal(await page.locator('[data-full-photo]').evaluate(el=>{
    const r=el.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2;
    return document.elementFromPoint(x,y)===el;
   }),true,'El botón Ampliar debe recibir el toque real');
   await page.screenshot({path:out+'/07-'+role+'-antes-ampliar.png',fullPage:true});
   await page.locator('[data-full-photo]').click();await page.waitForSelector('.zoom.galeria');
   assert.equal(await page.evaluate(()=>getComputedStyle(document.body).overflow),"hidden");
   assert.equal(await page.locator('.zoom .zg-elegir').isVisible(),false);
   await page.locator('.zoom .zg-sig').click();assert.match(await page.locator('.zoom .zg-cual').innerText(),/2 de 2/);
   assert.equal(r.writes.filter(x=>x.accion==="decidir").length,0);
   await r.context.close();
  }
  for(const [width,mobile,embedded] of [[1440,false,false],[390,true,false],[820,false,true]]){
   const media={mode:'public'},r=await prepare(b,width,'editor',mobile,embedded,media),view=r.view;
   await view.locator('[data-open="synthetic-0"]').click();await view.locator('[data-lamina="2"]').click();
   const choice=view.getByRole('dialog',{name:'Elegir fotografía de lámina 2',exact:true}),zoom=view.locator('.zoom.galeria');
   await view.waitForFunction(()=>document.querySelector('.bt-choice .bt-main-photo')?.naturalWidth===72);
   assert.equal(await choice.locator('.bt-main-photo').getAttribute('src'),mediaManifest.entries['laminas/synthetic-0/L2.jpg'].url);
   await choice.locator('[data-full-photo]').click();await view.waitForFunction(()=>document.querySelector('.zoom.galeria img')?.naturalWidth===72);
   await zoom.locator('.zg-sig').click();
   await view.waitForFunction(url=>document.querySelector('.zoom.galeria img')?.src===url&&document.querySelector('.zoom.galeria img')?.naturalWidth===72,mediaManifest.entries['laminas/synthetic-0/B.jpg'].url);
   assert.equal(r.writes.length,0,'ver/zoom/galería no escribe decisiones');
   await zoom.locator('.zx').click();
   media.mode='badpin';await view.evaluate(()=>SalaMedios.cargar());
   await choice.locator('[data-vote="si"]').click();
   assert.equal(r.writes.length,0,'ni una imagen ya descargada permite aprobar si el pin falló');
   assert.match(await choice.locator('.bt-notice').innerText(),/Espera a que cargue/);
   media.mode='public';await choice.locator('.bt-hero .bt-retry-label').waitFor();await choice.locator('.bt-hero .bt-retry-label').click();
   await view.waitForFunction(()=>SalaMedios.estado()==='listo');
   await view.waitForFunction(()=>document.querySelector('.bt-choice .bt-main-photo')?.naturalWidth===72);
   assert.equal(await view.evaluate(()=>SalaMedios.estado()),'listo');
   assert.ok(r.releaseReads.length>=2);assert.deepEqual(r.errors,[]);
   await r.context.close();
  }
  for(const [width,mobile] of [[1440,false],[390,true]]){
   const r=await prepare(b,width,'editor',mobile,false,{mode:'legacy',emptyDay:true}),view=r.view;
   assert.equal(await view.locator('.bt-column').count(),6,'día vacío conserva seis tiras confirmadas');
   assert.equal(await view.locator('.bt-frame.verde').count(),36);
   assert.equal(await view.evaluate(()=>D.propuestas.length),0,'inventario no inventa propuestas ni votos');
   await view.locator('[data-open="synthetic-0"]').click();await view.locator('[data-lamina="2"]').click();
   assert.equal(await view.locator('[data-vote]:enabled').count(),0);
   assert.equal(await view.locator('[data-reopen]:enabled').count(),1,'una aprobación con origen confirmado admite una nueva petición');
   assert.match(await view.locator('.bt-main-photo').getAttribute('src'),/B.jpg/);
   assert.equal(r.writes.length,0,'abrir historial no emite decisiones');
   await view.locator('[data-reopen]').click();
   await view.locator('#notaT').fill('Revisar contraste: petición explícita sintética');
   await view.locator('#notaOk').click();
   await view.waitForFunction(()=>dec['synthetic-0-base']?.laminas[1]==='no');
   assert.equal(await view.evaluate(()=>dec['synthetic-0-base'].notas[1]),'Revisar contraste: petición explícita sintética');
   assert.equal(await view.evaluate(()=>TIRAS['synthetic-0'].laminas[1].estado),'rehecha','la solicitud no reescribe la historia');
   assert.deepEqual(r.errors,[]);
   await r.context.close();
  }
  const missing=await prepare(b,390,'editor',true,false,{mode:'missing'});
  await missing.view.locator('[data-open="synthetic-0"]').click();await missing.view.locator('[data-lamina="2"]').dblclick();
  const missingChoice=missing.view.getByRole('dialog',{name:'Elegir fotografía de lámina 2',exact:true});
  assert.ok(await missingChoice.locator('[data-vote="si"]').isEnabled(),'la cuenta editora puede intentar aprobar; la imagen debe cerrar la compuerta');
  await missingChoice.locator('[data-vote="si"]').click();assert.equal(missing.writes.length,0);
  assert.match(await missingChoice.locator('.bt-notice').innerText(),/Espera a que cargue/);
  assert.equal(await missing.view.evaluate(()=>SalaMedios.estado()),'error');
  await missing.context.close();
  fs.writeFileSync(out+"/resultado.json",JSON.stringify({ok:true,publicaciones_sinteticas:6,laminas:36,escritorio:1440,movil:390,seleccion_indice_original:true,swipe_sin_voto:true,pinch_alejar:true,embed_portal:true,lector_agente_sin_votos:true},null,2));
  console.log("PASS tablero/tira/carrusel, roles, selección, swipe, pinch y conservación");
 }finally{await b.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
