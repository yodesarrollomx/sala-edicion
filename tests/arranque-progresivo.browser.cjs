/* Primera visita: servidor, medios, inventario y una tira retenidos por separado. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=path.resolve(__dirname,'..');
const server=http.createServer((req,res)=>{const p=path.join(root,new URL(req.url,'http://localhost').pathname==='/'?'index.html':new URL(req.url,'http://localhost').pathname);try{res.setHeader('Content-Type',p.endsWith('.js')?'application/javascript':p.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(p));}catch(e){res.writeHead(404);res.end();}});
const frames=Array.from({length:24},(_,i)=>({n:i+1,src:'laminas/fast/L'+(i+1)+'.jpg',dice:'Mensaje '+(i+1),estado:'pendiente'}));
const day=()=>({fecha:'2026-10-20',rol:'editor',quien:'Editor sintético',propuestas:['fast','slow'].map(id=>({id,tipo:'laminas',pieza:id,de_antes:null,laminas:id==='fast'?frames.map(l=>l.src):['laminas/slow/L1.jpg']})),decisiones:{editores:[],propuestas:{}}});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH}:{})});
 try{for(const width of [1440,390]){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage();
  const errors=[],writes=[],images=[],calls={};let releaseDay,releaseMedia,releaseInventory,releaseSlow;
  const gateDay=new Promise(r=>releaseDay=r),gateMedia=new Promise(r=>releaseMedia=r),gateInventory=new Promise(r=>releaseInventory=r),gateSlow=new Promise(r=>releaseSlow=r);
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{localStorage.setItem('sala_clave','synthetic');localStorage.setItem('sala_rol','editor');localStorage.setItem('sala_guia','1');});
  await page.route('**/*',async route=>{
   const req=route.request(),u=new URL(req.url());calls[u.pathname]=(calls[u.pathname]||0)+1;
   if(req.method()==='POST'){writes.push(req.url());return route.fulfill({json:{ok:true}});}
   if(u.hostname==='script.google.com'){if(u.searchParams.get('recurso')==='dia'){await gateDay;return route.fulfill({json:day()});}return route.fulfill({json:{ok:true,cola:[],reglas:{}}});}
   if(u.hostname!=='127.0.0.1')return route.fulfill({body:'',contentType:'application/javascript'});
   if(u.pathname==='/version-online.json')return route.fulfill({json:{}});
   if(u.pathname==='/datos/medios-publicos.json'){await gateMedia;return route.fulfill({status:404,body:''});}
   if(u.pathname==='/datos/manifiesto.json')return route.fulfill({json:day()});
   if(u.pathname==='/datos/mesa-estado.json'){await gateInventory;return route.fulfill({json:{revisado_en:new Date().toISOString(),publicaciones:[]}});}
   if(u.pathname==='/datos/tiras/slow.json'){await gateSlow;return route.fulfill({json:{pieza:'slow',pieza_slug:'slow',mapa:{1:1},laminas:[{n:1,src:'laminas/slow/L1.jpg',estado:'pendiente'}]}});}
   if(u.pathname==='/datos/tiras/fast.json')return route.fulfill({json:{pieza:'fast',pieza_slug:'fast',mapa:Object.fromEntries(frames.map(l=>[l.n,l.n])),laminas:frames}});
   if(u.pathname==='/datos/tiras/index.json')return route.fulfill({json:['fast','slow']});
   if(u.pathname.startsWith('/datos/'))return route.fulfill({json:{}});
   if(u.pathname.startsWith('/laminas/')){images.push(u.pathname);return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="tan"/></svg>'});}
   return route.continue();
  });
  await page.goto('http://127.0.0.1:'+server.address().port,{waitUntil:'domcontentloaded'});
  await page.waitForSelector('[data-column="fast"]');
  const visibleMs=await page.evaluate(()=>performance.now());
  await page.waitForFunction(()=>JSON.parse(localStorage.getItem('sala_mesa_local_v1')||'null')?.source==='published');
  assert.equal(await page.locator('[data-column="slow"]').count(),0);
  assert.match(await page.locator('.bt-local').innerText(),/Copia publicada/);
  assert.equal(await page.evaluate(()=>DECIDE()),false);assert.equal(writes.length,0);assert.equal(images.length,0);
  await page.locator('[data-open="fast"]').click();
  await page.locator('[data-lamina="1"]').click();assert.equal(await page.locator('[data-vote="si"]').isDisabled(),true);
  await page.locator('[data-close-choice]').click();
  releaseMedia();await page.waitForFunction(()=>SalaMedios.disponible());
  await page.waitForFunction(()=>[...document.querySelectorAll('#tableroHoy img')].some(im=>im.getAttribute('src')));
  const requested=images.length;assert.ok(requested<24,'No descargar todas las imágenes fuera de vista');
  assert.equal(calls['/datos/tiras/fast.json'],1);
  releaseSlow();releaseInventory();releaseDay();
  await page.waitForFunction(()=>!document.querySelector('.bt-local')&&DECIDE());
  await page.waitForFunction(()=>!!localStorage.getItem('sala_mesa_local_v1'));
  assert.equal(await page.locator('[data-column="slow"]').count(),0); // foco en fast se conserva
  assert.equal(writes.length,0);assert.deepEqual(errors,[]);
  console.log(JSON.stringify({width,firstVisitVisibleMs:Math.round(visibleMs),visibleBeforeServer:true,visibleBeforeMedia:true,visibleBeforeInventory:true,visibleBeforeSlowStrip:true,initialImages:0,imagesAfterMedia:requested,writes:0,errors:0}));
  await context.close();
 }}finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
