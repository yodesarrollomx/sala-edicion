const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const base='https://yodesarrollomx.github.io/sala-edicion/',dir='evidencia-o1-real',slug='dato-servilleta-3';
const result={scope:'cuatro_recorridos_visuales_de_lote_real',cuatro_ciclos_productivos_acreditados:false,run_id:process.env.GITHUB_RUN_ID,passes:[]};
const json=async path=>{const r=await fetch(base+path+'?v='+Date.now());assert.equal(r.status,200,path);return r.json()};
async function loaded(locator){await locator.scrollIntoViewIfNeeded();await locator.evaluate(e=>new Promise((resolve,reject)=>{if(e.complete)return e.naturalWidth?resolve():reject(Error('Imagen rota'));const timer=setTimeout(()=>reject(Error('Imagen sin cargar')),30000);e.onload=()=>{clearTimeout(timer);e.naturalWidth?resolve():reject(Error('Imagen vacía'))};e.onerror=()=>{clearTimeout(timer);reject(Error('Imagen rota'))}}));}
(async()=>{
 fs.mkdirSync(dir,{recursive:true});let browser;
 try{
 let target,receipt,report;
 for(let i=0;i<60;i++){
  try{
   receipt=await json('version-online.json');report=await json('datos/mesa-estado.json');
   assert.ok(receipt.media_manifest_sha256);assert.equal(report.run_id,'39073527776');
   const mf=await json('datos/manifiesto.json');
   for(const p of mf.propuestas||[]){
    if(!p.id.startsWith(slug+'-'))continue;
    const t=await json('datos/tiras/'+p.id+'.json');
    if((t.laminas||[]).length===5&&[2,3,4,5].every(n=>(t.laminas.find(l=>Number(l.n)===n)?.candidatas||[]).filter(c=>c.modelo==='HiDream-O1-Image-Dev').length===2)){target={id:p.id,t};break;}
   }
   if(target)break;
  }catch(e){result.espera=e.message;}
  if(i===59)throw Error('Lote real aún no está publicado y montado en el respaldo de la sala: '+(result.espera||'sin tarjeta'));
  await new Promise(r=>setTimeout(r,20000));
 }
 const mr=await fetch(base+'datos/medios-publicos.json?v='+Date.now()),raw=Buffer.from(await mr.arrayBuffer());assert.equal(mr.status,200);
 assert.equal(crypto.createHash('sha256').update(raw).digest('hex'),receipt.media_manifest_sha256);
 const manifest=JSON.parse(raw),candidates=target.t.laminas.flatMap(l=>[2,3,4,5].includes(Number(l.n))?(l.candidatas||[]):[]);
 assert.equal(candidates.length,8);
 const assets=[];
 for(const c of candidates){
  const logical=c.src||c.original,entry=manifest.entries[logical];assert.ok(entry,'Imagen nueva sin manifiesto: '+logical);
  const r=await fetch(entry.url),bytes=Buffer.from(await r.arrayBuffer());assert.equal(r.status,200);assert.equal(bytes.length,entry.bytes);assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),entry.sha256);
  assets.push({logical,sha256:entry.sha256,bytes:bytes.length,url:entry.url,modelo:c.modelo});
 }
 result.lote={id:target.id,mesa:report.run_id,receipt,assets};
 browser=await chromium.launch();
 for(let k=1;k<=4;k++){
  const mobile=k%2===0,context=await browser.newContext({viewport:{width:mobile?390:1440,height:mobile?844:1000},isMobile:mobile,hasTouch:mobile});
  const page=await context.newPage(),errors=[],writes=[],start=new Date().toISOString();
  await page.route('**/*',r=>{if(['GET','HEAD'].includes(r.request().method()))return r.continue();writes.push(r.request().method());return r.abort()});
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base,{waitUntil:'domcontentloaded'});
  await page.waitForSelector('.bt-column',{timeout:60000});
  await page.waitForFunction(()=>!document.querySelector('[data-refresh]')?.disabled);
  const skip=page.getByRole('button',{name:'Saltar',exact:true});if(await skip.isVisible())await skip.click();
  assert.equal(await page.evaluate(()=>ROL()),'lector');
  const ids=await page.locator('[data-open]').evaluateAll(els=>els.map(e=>e.dataset.open));assert.ok(ids.includes(slug));
  let frames=0;
  for(const id of ids){await page.locator('[data-open="'+id+'"]').click();const photos=page.locator('.bt-frame img');const count=await page.locator('.bt-frame').count();assert.equal(await photos.count(),count);for(let j=0;j<count;j++)await loaded(photos.nth(j));frames+=count;await page.locator('.bt-nav [data-back]').click();}
  await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:dir+'/pasada-'+k+'-tablero.jpg',type:'jpeg',quality:80,fullPage:true});
  await page.locator('[data-open="'+slug+'"]').click();assert.equal(await page.locator('.bt-frame').count(),5);await page.screenshot({path:dir+'/pasada-'+k+'-tira.jpg',type:'jpeg',quality:85,fullPage:true});
  const options=[];
  for(const number of [2,3,4,5]){
   await page.locator('.bt-photo[data-lamina="'+number+'"]').click();
   assert.equal(await page.locator('[data-option]').count(),2);
   for(let option=0;option<2;option++){
    await page.locator('[data-option="'+option+'"]').click();await loaded(page.locator('.bt-main-photo'));
    const src=await page.locator('.bt-main-photo').getAttribute('src');assert.ok(src.startsWith('https://github.com/yodesarrollomx/sala-edicion/releases/download/'));
    options.push({lamina:number,opcion:option+1,src});
    if(number===2)await page.screenshot({path:dir+'/pasada-'+k+'-lamina2-opcion'+(option+1)+'.jpg',type:'jpeg',quality:85,fullPage:true});
   }
   await page.locator('.bt-nav [data-back]').click();
  }
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  result.passes.push({pasada:k,inicio:start,fin:new Date().toISOString(),viewport:mobile?'movil':'escritorio',columnas:ids.length,laminas_recorridas:frames,opciones:options,errores:errors,escrituras:writes.length,ok:true});
  fs.writeFileSync(dir+'/resultado.json',JSON.stringify(result,null,2));console.log('PASADA_REAL '+JSON.stringify(result.passes.at(-1)));await context.close();
 }
 result.ok=true;
 }catch(e){result.ok=false;result.error=e.message;console.error('FALLO_REAL '+e.message);process.exitCode=1;}
 finally{fs.writeFileSync(dir+'/resultado.json',JSON.stringify(result,null,2));if(browser)await browser.close();}
})();
