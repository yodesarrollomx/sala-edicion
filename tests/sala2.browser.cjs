/* Primera visita: servidor, medios, inventario y una tira retenidos por separado. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=path.resolve(__dirname,'..');
const server=http.createServer((req,res)=>{const p=path.join(root,new URL(req.url,'http://localhost').pathname==='/'?'index.html':new URL(req.url,'http://localhost').pathname);try{res.setHeader('Content-Type',p.endsWith('.js')?'application/javascript':p.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(p));}catch(e){res.writeHead(404);res.end();}});

const day=role=>({fecha:'2026-10-20',rol:role,quien:'Editor sintético',propuestas:Array.from({length:5},(_,i)=>({id:'corte-'+i,tipo:'eje',titulo:'Corte '+i,video:'https://drive.google.com/file/d/syntheticvideo123/preview',laminas:[],opciones:{candidatas:[{titulo:'Conservar este corte'}]}})),decisiones:{editores:[],propuestas:{}}});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH}:{})});
 try{for(const width of [1440,390])for(const mode of ['editor','lector','clasica','timeout']){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),errors=[],writes=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(role=>{localStorage.setItem('sala_clave','synthetic');localStorage.setItem('sala_rol',role);localStorage.setItem('sala_guia','1');localStorage.setItem('sala_guia_v3','1');},mode==='lector'?'lector':'editor');
  await page.route('**/*',async route=>{
   const req=route.request(),u=new URL(req.url());
   if(req.method()==='POST'){const d=JSON.parse(req.postData()||'{}');if(d.accion==='video_revision')return route.fulfill({json:{ok:false,error:'video_sintetico_no_preparado'}});writes.push(d);return route.fulfill({json:{ok:true}});}
   if(u.hostname==='script.google.com'){
    if(u.searchParams.get('recurso')==='dia')return mode==='timeout'?route.abort():route.fulfill({json:day(mode==='lector'?'lector':'editor')});
    return route.fulfill({json:{ok:true,cola:[],reglas:{}}});
   }
   if(u.hostname!=='127.0.0.1')return route.fulfill({body:'',contentType:'application/javascript'});
   if(u.pathname==='/version-online.json')return route.fulfill({json:{}});
   if(u.pathname==='/datos/medios-publicos.json')return route.fulfill({status:404,body:''});
   if(u.pathname==='/datos/manifiesto.json')return route.fulfill({json:day('editor')});
   if(u.pathname.startsWith('/datos/'))return route.fulfill({json:u.pathname.endsWith('/index.json')?[]:{}});
   return route.continue();
  });
  await page.goto('http://127.0.0.1:'+server.address().port+(mode==='clasica'?'/?clasica=1':''));
  if(mode==='editor'){
   await page.waitForSelector('#s2dock',{state:'visible'});
   assert.equal(await page.evaluate(()=>pasos.length),5);
   assert.equal(await page.locator('body.sala-turno').count(),1);
   const box=await page.locator('.conVideo').boundingBox();assert.ok(box.height>450);assert.ok(Math.abs(box.width/box.height-9/16)<.02);
   assert.equal(await page.locator('#s2dock').evaluate(el=>getComputedStyle(el).position),'fixed');
   await page.screenshot({path:'/tmp/sala2-'+width+'.png'});
   await page.locator('#s2chg').click();await page.waitForSelector('#notaT');assert.equal(await page.locator('#notaT').inputValue(),'');
   await page.locator('#notaT').fill('Cambiar cierre');await page.locator('#s2segIn').fill('12');await page.locator('#notaOk').click();
   await page.waitForFunction(()=>idx===1);assert.equal(await page.evaluate(()=>dec['corte-0'].nota),'[0:12] Cambiar cierre');
   await page.locator('#s2no').click();await page.waitForSelector('#notaT');assert.equal(await page.locator('#notaT').inputValue(),'NO VA — ');
   await page.locator('#notaT').fill('NO VA — Rehacer');await page.locator('#notaOk').focus();await page.keyboard.press('Enter');
   await page.waitForFunction(()=>idx===2);assert.equal(await page.evaluate(()=>dec['corte-1'].nota),'NO VA — Rehacer');
   await page.waitForFunction(()=>candadoLibre());await page.locator('#s2ok').click();await page.waitForFunction(()=>idx===3);assert.equal(await page.evaluate(()=>dec['corte-2'].laminas[0]),'si');
   await page.waitForFunction(()=>candadoLibre());await page.locator('#deshacer').click();await page.waitForFunction(()=>idx===2);
   await page.evaluate(()=>{pasos[idx].p.video='';pintarCartas();});await page.waitForSelector('#zona .opciones',{state:'visible'});
   await page.locator('#puertas [data-v="prod"]').click();await page.waitForFunction(()=>document.body.dataset.vista==='prod');assert.equal(await page.locator('#s2dock').isVisible(),false);
   await page.locator('#puertas [data-v="hoy"]').click();await page.waitForSelector('#s2dock',{state:'visible'});
  }else{
   await page.waitForSelector('.bt-column');
   assert.equal(await page.locator('#s2dock').isVisible(),false);
   if(mode==='clasica')assert.equal(await page.locator('body.sala2').count(),0);
   else assert.equal(await page.evaluate(()=>DECIDE()),false);
   assert.equal(writes.length,0);
  }
  assert.deepEqual(errors,[]);console.log(JSON.stringify({width,mode,errors:0,realWrites:0,interceptedWrites:writes.length}));
  await context.close();
 }}finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
