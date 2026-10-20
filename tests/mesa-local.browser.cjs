/* Reapertura real de navegador con servidor retenido y datos sintéticos. Sin red de negocio. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=path.resolve(__dirname,'..');
const server=http.createServer((req,res)=>{
 const pathname=new URL(req.url,'http://localhost').pathname;
 const file=path.join(root,pathname==='/'?'index.html':pathname);
 if(!file.startsWith(root+path.sep)){res.writeHead(403);return res.end();}
 try{const content=fs.readFileSync(file);res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(content);}catch(e){res.writeHead(404);res.end();}
});
const frames=[1,2].map(n=>({n,src:'laminas/synthetic/L'+n+'.jpg',dice:'Mensaje '+n,estado:'pendiente'}));
const day=()=>({fecha:'2026-10-20',rol:'editor',quien:'Editor sintético',ultima_revision:'2026-10-20T00:00:00Z',propuestas:[{id:'synthetic-v1',tipo:'laminas',pieza:'Publicación sintética',de_antes:null,laminas:frames.map(f=>f.src)}],decisiones:{editores:[],propuestas:{}}});
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const base='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH}:{})});
 try{
 for(const width of [1440,390]){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage();
  const errors=[],writes=[];let hold=false,release=null,reject=false,networkFail=false,freshTitle='Publicación sintética';
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{
   if(!localStorage.getItem('test-initialized')){
    localStorage.setItem('sala_clave','synthetic-session');localStorage.setItem('sala_rol','editor');
    localStorage.setItem('sala_guia','1');localStorage.setItem('test-initialized','1');
   }
  });
  await page.route('**/*',async route=>{
   const req=route.request(),u=new URL(req.url());
   if(u.hostname==='script.google.com'){
    if(req.method()==='POST'){writes.push(req.postData());return route.fulfill({json:{ok:true}});}
    if(u.searchParams.get('recurso')==='dia'){
     if(networkFail)return route.abort('failed');
     if(hold)await new Promise(r=>release=r);
     const d=day();d.propuestas[0].pieza=freshTitle;
     return route.fulfill({json:reject?{error:'clave incorrecta'}:d}).catch(()=>{});
    }
    return route.fulfill({json:{ok:true,cola:[],reglas:{}}});
   }
   if(u.hostname!=='127.0.0.1')return route.fulfill({body:'',contentType:'application/javascript'});
   if(u.pathname==='/version-online.json')return route.fulfill({json:{}});
   if(u.pathname==='/datos/medios-publicos.json')return route.fulfill({status:404,body:''});
   if(u.pathname.startsWith('/datos/')){
    let value={};
    if(u.pathname==='/datos/manifiesto.json')value=day();
    if(u.pathname==='/datos/mesa-estado.json')value={revisado_en:new Date().toISOString(),publicaciones:[]};
    if(u.pathname==='/datos/tiras/synthetic-v1.json')value={pieza:freshTitle,pieza_slug:'synthetic',mapa:{1:1,2:2},laminas:frames};
    if(u.pathname.endsWith('/index.json'))value=u.pathname==='/datos/tiras/index.json'?['synthetic-v1']:[];
    return route.fulfill({json:value});
   }
   if(u.pathname.startsWith('/laminas/'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="tan"/></svg>'});
   return route.continue();
  });
  await page.goto(base+'?clasica=1',{waitUntil:'domcontentloaded'});
  await page.waitForSelector('.bt-column');
  await page.waitForFunction(()=>!!localStorage.getItem('sala_mesa_local_v1'));
  const snapshot=await page.evaluate(()=>localStorage.getItem('sala_mesa_local_v1'));
  assert.ok(!snapshot.includes('synthetic-session'));
  await page.evaluate(()=>{dec['synthetic-v1'].laminas[0]='no';dec['synthetic-v1'].notas[0]='Conservar mi nota';guardarBorrador();});
  hold=true;
  await page.reload({waitUntil:'domcontentloaded'});
  await page.waitForSelector('.bt-local');await page.waitForSelector('.bt-column');
  await page.waitForFunction(()=>performance.getEntriesByName('sala-mesa-local-visible').length>0);
  const elapsed=await page.evaluate(()=>performance.getEntriesByName('sala-mesa-local-visible')[0].startTime);
  // Registrar latencia, no convertir la carga variable del runner en una garantía de producción.
  // La compuerta funcional es mostrar/navegar ANTES de liberar cualquier respuesta del día.
  assert.ok(Number.isFinite(elapsed));
  assert.equal(await page.evaluate(()=>DECIDE()),false);
  if(process.env.SALA_CACHE_EVIDENCE_DIR){fs.mkdirSync(process.env.SALA_CACHE_EVIDENCE_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.SALA_CACHE_EVIDENCE_DIR,'mesa-local-'+width+'.png'),fullPage:false});}
  await page.locator('[data-open="synthetic"]').click();await page.locator('[data-lamina="1"]').click();
  assert.equal(await page.locator('[data-vote="si"]').isDisabled(),true);
  const draft=await page.evaluate(()=>localStorage.getItem('sala2-2026-10-20'));
  assert.equal(JSON.parse(draft).dec['synthetic-v1'].notas[0],'Conservar mi nota');
  await page.evaluate(()=>guardarBorrador());
  assert.equal(await page.evaluate(()=>localStorage.getItem('sala2-2026-10-20')),draft);
  assert.equal(writes.length,0);
  freshTitle='Publicación actualizada';hold=false;assert.ok(release);release();
  await page.waitForFunction(()=>!document.querySelector('.bt-local'));
  assert.equal(await page.evaluate(()=>DECIDE()),true);
  assert.equal(await page.evaluate(()=>dec['synthetic-v1'].notas[0]),'Conservar mi nota');
  assert.equal(await page.evaluate(()=>dec['synthetic-v1'].laminas[0]),'no');
  assert.equal(writes.length,0);
  // Red caída conserva la copia y la nota; un respaldo no se convierte en mesa vigente.
  networkFail=true;
  await page.reload({waitUntil:'domcontentloaded'});await page.waitForSelector('.bt-local');
  await page.waitForFunction(()=>document.querySelector('#estado').textContent.includes('sin conexión'));
  assert.equal(await page.locator('.bt-column').count(),1);
  assert.equal(await page.evaluate(()=>DECIDE()),false);
  assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('sala2-2026-10-20')).dec['synthetic-v1'].notas[0]),'Conservar mi nota');
  assert.equal(writes.length,0);networkFail=false;
  // Rechazo explícito invalida la copia, no la confunde con ausencia de red.
  hold=true;release=null;await page.reload({waitUntil:'domcontentloaded'});await page.waitForSelector('.bt-local');
  await page.waitForFunction(()=>typeof D==='object'&&D!==null);
  while(!release)await new Promise(r=>setTimeout(r,10));
  reject=true;hold=false;release();
  await page.waitForSelector('#btnGoogleYa');
  assert.equal(await page.locator('.bt-column').count(),0);
  assert.equal(await page.evaluate(()=>localStorage.getItem('sala_mesa_local_v1')),null);
  assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('sala2-2026-10-20')).dec['synthetic-v1'].notas[0]),'Conservar mi nota');
  // Otra sesión del mismo dispositivo nunca pinta la copia anterior.
  await page.evaluate(saved=>{localStorage.setItem('sala_mesa_local_v1',saved);localStorage.setItem('sala_rol','editor2');},snapshot);
  reject=false;hold=true;release=null;
  await page.reload({waitUntil:'domcontentloaded'});await page.waitForSelector('.bt-local');
  assert.match(await page.locator('.bt-local').innerText(),/Copia publicada/);
  assert.equal(await page.evaluate(()=>DECIDE()),false);
  await page.waitForFunction(()=>JSON.parse(localStorage.getItem('sala_mesa_local_v1')||'null')?.source==='published');
  assert.notEqual(await page.evaluate(()=>JSON.parse(localStorage.getItem('sala_mesa_local_v1')).owner),JSON.parse(snapshot).owner);
  assert.deepEqual(errors,[]);assert.equal(writes.length,0);
  if(release){hold=false;release();}
  console.log(JSON.stringify({width,cachedVisibleMs:Math.round(elapsed),writes:0,errors:0,draftPreserved:true,rejectionCleared:true}));
  await context.close();
 }
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
