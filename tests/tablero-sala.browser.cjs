/* Recorrido aislado: sólo datos sintéticos; ninguna escritura en Google. */
const {chromium}=require("playwright"),assert=require("node:assert/strict"),fs=require("node:fs");
const out="tests/evidencia-tablero";fs.mkdirSync(out,{recursive:true});
const titles=["Tres perspectivas","Doble camino","El diseño invisible","Ruta propia","El entregable","La mesa"];
const tiras={};const propuestas=titles.map((pieza,k)=>{
 const id="synthetic-"+k;
 tiras[id]={pieza,pieza_slug:id,base:id+"-base",promesa:"Entender la decisión de diseño",decidir:[2,3,4,5,6],mapa:{"1":2,"2":3,"3":4,"4":5,"5":6},
 laminas:Array.from({length:6},(_,i)=>({n:i+1,src:"laminas/"+id+"/L"+(i+1)+".jpg",dice:"Una decisión concreta para la lámina "+(i+1),ve:"Personas comparan maquetas sobre una mesa",estado:i===0?"aprobada":"rehecha",
 version:i===1?7:1,versiones:i===1?Array.from({length:7},(_,v)=>({v:v+1,src:"laminas/"+id+"/v"+(v+1)+".png",marca:v===0?"no":""})):[],
 candidatas:i===1?[{src:"laminas/"+id+"/bad.jpg",motor:"cpu"},{src:"laminas/"+id+"/L2.jpg",motor:"hidream_demo",modelo:"HiDream-I1-Dev",titulo:"A"},{src:"laminas/"+id+"/B.jpg",motor:"hidream_demo",modelo:"HiDream-I1-Dev",titulo:"B"}]:[]}))};
 return {id,tipo:"laminas",pieza,titulo:pieza,laminas:tiras[id].laminas.slice(1).map(x=>x.src)};
});
function day(role){return {fecha:"2026-10-13",rol:role,quien:"Alejandro",version:"synthetic",propuestas:JSON.parse(JSON.stringify(propuestas)),decisiones:{editores:[],propuestas:{}}};}
const svg='<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1350"><rect width="1080" height="1350" fill="#c5b7a3"/><rect x="90" y="480" width="900" height="360" rx="30" fill="#f5edde"/><path d="M180 750 440 550 650 710 870 610" stroke="#b88159" stroke-width="35" fill="none"/><circle cx="330" cy="300" r="90" fill="#565b54"/><circle cx="720" cy="300" r="85" fill="#626964"/></svg>';
async function prepare(browser,width,role="editor",mobile=false){
 const context=await browser.newContext({viewport:{width,height:mobile?844:1000},isMobile:mobile,hasTouch:mobile});
 const page=await context.newPage(),writes=[],errors=[];
 page.on("pageerror",e=>errors.push(String(e)));
 await page.addInitScript(({role})=>{
  localStorage.setItem("sala_clave","synthetic-session-key");localStorage.setItem("sala_rol",role);
  localStorage.setItem("sala_guia_v3","1");localStorage.setItem("sala_guia","1");
 },{role});
 await page.route("**/*",async route=>{
  const req=route.request(),u=new URL(req.url());
  if(u.hostname==="script.google.com"||u.hostname==="script.googleusercontent.com"){
   if(req.method()==="POST"){const body=JSON.parse(req.postData()||"{}");writes.push(body);await route.fulfill({json:{ok:true}});return;}
   const resource=u.searchParams.get("recurso");
   await route.fulfill({json:resource==="dia"?day(role):resource==="cola"?{ok:true,cola:[{pieza:"synthetic-1",etapa:"voz",estado:"corriendo",item:"2"}]}:resource==="entrada"?{ok:true,rol:role}: {ok:true,reglas:{},propuestas:[]}});return;
  }
  if(u.hostname!=="127.0.0.1"){await route.fulfill({status:200,contentType:req.resourceType()==="stylesheet"?"text/css":"application/javascript",body:""});return;}
  if(/\/laminas\/.*\.(jpg|png)$/.test(u.pathname)){await route.fulfill({contentType:"image/svg+xml",body:svg});return;}
  if(u.pathname.includes("/datos/")){
   let value={};
   if(u.pathname==="/datos/manifiesto.json")value=day(role);
   else if(u.pathname==="/datos/tiras/index.json")value=Object.keys(tiras);
   else if(u.pathname.startsWith("/datos/tiras/"))value=tiras[u.pathname.split("/").pop().replace(".json","")]||{};
   else if(u.pathname==="/datos/piezas.json")value={};
   else if(u.pathname.endsWith("/index.json"))value=[];
   await route.fulfill({json:value});return;
  }
  await route.continue();
 });
 await page.goto("http://127.0.0.1:8765/");
 await page.waitForSelector(".bt-column",{timeout:30000});
 // La bienvenida, si estaba visible, se cierra con su botón sin tocar datos.
 await page.evaluate(()=>{if(typeof cerrarCapas==="function")cerrarCapas();});
 return {page,context,writes,errors};
}
const sessions=new WeakMap();
async function touch(page,points,type){let session=sessions.get(page);if(!session){session=await page.context().newCDPSession(page);sessions.set(page,session);}await session.send("Input.dispatchTouchEvent",{type,touchPoints:points});}
(async()=>{
 const b=await chromium.launch({headless:true});
 try{
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
  await p.locator("[data-next-option]").click();
  await p.waitForFunction(()=>document.querySelector(".bt-main-photo")?.naturalWidth>0);
  await p.locator('[data-vote="si"]').click();
  await p.waitForFunction(()=>document.querySelector(".bt-choice-copy .bt-dot")?.textContent==="Aprobada");
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
  assert.ok(await q.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await q.screenshot({path:out+"/04-tablero-movil.png",fullPage:true});
  await q.locator('[data-open="synthetic-0"]').click();
  await q.locator('[data-lamina="2"]').click();
  await q.waitForFunction(()=>document.querySelector(".bt-main-photo")?.naturalWidth>0);
  const h=await q.locator(".bt-hero").boundingBox(),x=Math.round(h.x+h.width/2),y=Math.round(h.y+h.height*.75);
  await touch(q,[{x,y}],"touchStart");
  await touch(q,[{x,y:y-130}],"touchMove");
  await touch(q,[],"touchEnd");
  await q.waitForFunction(()=>document.querySelector(".bt-choice-copy .bt-dot")?.textContent==="Aprobada");
  assert.equal(m.writes.filter(x=>x.accion==="decidir").length,1);
  await q.screenshot({path:out+"/05-carrusel-movil.png",fullPage:true});
  await q.locator("[data-close-choice]").click();
  await q.waitForSelector('#tableroHoy[data-level="publicacion"]');
  const area=await q.locator(".bt-pan").boundingBox(),cx=Math.round(area.x+area.width/2),cy=Math.round(area.y+80);
  await touch(q,[{x:cx-80,y:cy},{x:cx+80,y:cy}],"touchStart");
  await touch(q,[{x:cx-40,y:cy},{x:cx+40,y:cy}],"touchMove");
  await touch(q,[],"touchEnd");
  await q.waitForSelector('#tableroHoy[data-level="tablero"]');
  assert.deepEqual(m.errors,[]);
  await m.context.close();

  for(const role of ["lector","agente"]){
   const r=await prepare(b,390,role,true),page=r.page;
   await page.locator('[data-open="synthetic-0"]').click();await page.locator('[data-lamina="2"]').click();
   assert.ok(await page.locator('[data-vote="si"]').isDisabled());assert.ok(await page.locator('[data-vote="no"]').isDisabled());
   assert.equal(r.writes.filter(x=>x.accion==="decidir").length,0);
   await r.context.close();
  }
  fs.writeFileSync(out+"/resultado.json",JSON.stringify({ok:true,publicaciones_sinteticas:6,laminas:36,escritorio:1440,movil:390,seleccion_indice_original:true,swipe_aprobar:true,pinch_alejar:true,lector_agente_sin_votos:true},null,2));
  console.log("PASS tablero/tira/carrusel, roles, selección, swipe, pinch y conservación");
 }finally{await b.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
