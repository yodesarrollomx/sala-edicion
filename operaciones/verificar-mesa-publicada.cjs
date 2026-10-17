const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
const base='https://yodesarrollomx.github.io/sala-edicion/';
(async()=>{
 for(let attempt=0;attempt<30;attempt++){
  const r=await fetch(base+'datos/mesa-estado.json?espera='+Date.now());
  const d=await r.json();
  if(Array.isArray(d.publicaciones)&&d.code_sha==='ee3e9a5b54b08fa59ed6d2d7df17c8550b102d68')break;
  if(attempt===29)throw Error('No llegó la proyección del commit esperado');
  await new Promise(resolve=>setTimeout(resolve,20000));
 }
 const browser=await chromium.launch({headless:true});
 const result={tipo:'recorridos_visuales_reales_sin_escrituras',produccion_nueva_acreditada:false,run_id:process.env.GITHUB_RUN_ID,passes:[]};
 fs.mkdirSync('evidencia-mesa',{recursive:true});
 try{
 for(let k=1;k<=4;k++){
  const inicio=new Date().toISOString(),mobile=k%2===0;
  const context=await browser.newContext({viewport:{width:mobile?390:1440,height:mobile?844:1000},isMobile:mobile,hasTouch:mobile});
  const page=await context.newPage(),errors=[],blocked=[];
  await page.route('**/*',r=>{if(['GET','HEAD'].includes(r.request().method()))return r.continue();blocked.push(r.request().method());return r.abort();});
  page.on('pageerror',e=>errors.push(e.message.slice(0,200)));
  const res=await page.request.get(base+'datos/mesa-estado.json?v='+Date.now());assert.equal(res.status(),200);
  const report=await res.json();assert.ok(Array.isArray(report.publicaciones)&&report.publicaciones.length>0,'Falta inventario vigente publicado');
  await page.goto(base,{waitUntil:'domcontentloaded'});
  await page.waitForSelector('.bt-column',{timeout:60000});
  await page.waitForFunction(()=>!document.querySelector('[data-refresh]')?.disabled,{timeout:60000});
  await page.getByRole('button',{name:'Saltar',exact:true}).click({timeout:15000});
  const role=await page.evaluate(()=>ROL());assert.equal(role,'lector');
  const columns=await page.locator('.bt-column').count();
  assert.equal(columns,report.publicaciones.length);
  const expected=report.publicaciones.reduce((a,p)=>a+p.laminas.length,0);
  assert.equal(await page.locator('.bt-frame').count(),expected);
  await page.screenshot({path:'evidencia-mesa/pasada-'+k+'-mesa.jpg',type:'jpeg',quality:75,fullPage:true});
  const ids=await page.locator('[data-open]').evaluateAll(els=>els.map(e=>e.dataset.open));
  const pieces=[];
  for(const id of ids){
   await page.locator('[data-open="'+id+'"]').click();
   const fotos=page.locator('.bt-frame img');
   for(let j=0;j<await fotos.count();j++){
    await fotos.nth(j).scrollIntoViewIfNeeded();
    await fotos.nth(j).evaluate(e=>new Promise((resolve,reject)=>{
     if(e.complete)return e.naturalWidth?resolve():reject(Error('Imagen sin bytes'));
     const timer=setTimeout(()=>reject(Error('Imagen no cargada')),30000);
     e.addEventListener('load',()=>{clearTimeout(timer);e.naturalWidth?resolve():reject(Error('Imagen vacía'));},{once:true});
     e.addEventListener('error',()=>{clearTimeout(timer);reject(Error('Imagen rota'));},{once:true});
    }));
   }
   const frames=await page.locator('.bt-frame').count();assert.equal(await fotos.count(),frames);
   pieces.push({pieza:id,laminas:frames,imagenes_cargadas:frames});
   if(pieces.length===1)await page.screenshot({path:'evidencia-mesa/pasada-'+k+'-tira.jpg',type:'jpeg',quality:75,fullPage:true});
   await page.locator('.bt-nav [data-back]').click();
  }
  assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);
  result.passes.push({pasada:k,inicio,fin:new Date().toISOString(),viewport:mobile?'movil':'escritorio',role,columnas:columns,laminas:expected,piezas:pieces,mesa_run_id:report.run_id,mesa_code_sha:report.code_sha,mesa_revisada:report.revisado_en,errores:errors,escrituras:blocked.length,ok:true});
  fs.writeFileSync('evidencia-mesa/resultado.json',JSON.stringify(result,null,2));
  console.log('RECORRIDO_VISUAL '+JSON.stringify(result.passes.at(-1)));
  await context.close();
 }
 result.ok=true;
 }catch(e){result.ok=false;result.error=e.message;console.error('VERIFICACION_FALLIDA '+e.message);process.exitCode=1;}
 finally{fs.writeFileSync('evidencia-mesa/resultado.json',JSON.stringify(result,null,2));await browser.close();}
})();
