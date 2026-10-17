const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const base='https://yodesarrollomx.github.io/sala-edicion/',dir=(process.env.SALA_EVIDENCE_DIR||'evidencia-o1-real'),slug='dato-servilleta-3';
const result={scope:'cuatro_recorridos_visuales_de_lote_real',cuatro_ciclos_productivos_acreditados:false,run_id:process.env.GITHUB_RUN_ID,passes:[]};
const json=async path=>{const r=await fetch(base+path+'?v='+Date.now());assert.equal(r.status,200,path);return r.json()};
async function loaded(locator){await locator.evaluate(e=>e.scrollIntoView({behavior:'instant',block:'center',inline:'center'}));await locator.evaluate(e=>new Promise((resolve,reject)=>{if(e.complete)return e.naturalWidth?resolve():reject(Error('Imagen rota'));const timer=setTimeout(()=>reject(Error('Imagen sin cargar')),30000);e.onload=()=>{clearTimeout(timer);e.naturalWidth?resolve():reject(Error('Imagen vacía'))};e.onerror=()=>{clearTimeout(timer);reject(Error('Imagen rota'))}}));}
(async()=>{
 fs.mkdirSync(dir,{recursive:true});let browser,activePage;
 try{
 let target,receipt,report,runReport;
 if(process.env.SALA_CYCLE_RUN){
  const {execFileSync}=require('node:child_process');
  const gh=args=>execFileSync('gh',args,{encoding:'utf8',maxBuffer:30*1024*1024});
  const jobs=JSON.parse(gh(['api','repos/yodesarrollomx/sala-edicion/actions/runs/'+process.env.SALA_CYCLE_RUN+'/jobs?per_page=100'])).jobs;
  const mesa=jobs.find(j=>j.name==='mesa / mesa'&&j.conclusion==='success');assert.ok(mesa,'Mesa del ciclo sin éxito');
  const logs=gh(['api','repos/yodesarrollomx/sala-edicion/actions/jobs/'+mesa.id+'/logs']);
  const line=logs.split('\n').filter(x=>x.includes('estado Mesa: ')).at(-1);assert.ok(line,'Sin comprobante Mesa');
  runReport=JSON.parse(line.slice(line.indexOf('estado Mesa: ')+13).trim());
  assert.equal(runReport.run_id,process.env.SALA_CYCLE_RUN);
 }
 for(let i=0;i<60;i++){
  try{
   receipt=await json('version-online.json');report=runReport||await json('datos/mesa-estado.json');
   assert.ok(receipt.media_manifest_sha256);assert.equal(report.modelo_imagen,'HiDream-O1-Image-Dev');if(process.env.SALA_CYCLE_RUN)assert.equal(report.run_id,process.env.SALA_CYCLE_RUN);else assert.ok(report.generadas>=4&&report.tomas_obtenidas===8);
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
 const proof=await fetch('https://api.github.com/repos/yodesarrollomx/sala-edicion/actions/runs/'+report.run_id+'/jobs');
 assert.equal(proof.status,200);const jobs=(await proof.json()).jobs;
 assert.ok(jobs.some(j=>(j.name==='mesa'||j.name==='mesa / mesa')&&j.conclusion==='success'),'Mesa sin montaje confirmado');
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
 result.lote={id:target.id,mesa:report.run_id,receipt,assets,laminas_preparadas:report.laminas_preparadas,tiras_reutilizadas:report.tiras_reutilizadas,tomas_obtenidas:report.tomas_obtenidas};
 browser=await chromium.launch();
 for(let k=1;k<=Number(process.env.SALA_PASSES||4);k++){
  const mobile=process.env.SALA_MOBILE==='1'||(!process.env.SALA_MOBILE&&k%2===0),context=await browser.newContext({viewport:{width:mobile?390:1440,height:mobile?844:1000},isMobile:mobile,hasTouch:mobile});
  const page=activePage=await context.newPage(),errors=[],writes=[],start=new Date().toISOString();
  await page.route('**/*',r=>{if(['GET','HEAD'].includes(r.request().method()))return r.continue();writes.push(r.request().method());return r.abort()});
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base,{waitUntil:'domcontentloaded'});
  await page.waitForSelector('.bt-column',{timeout:60000});
  await page.waitForFunction(()=>!document.querySelector('[data-refresh]')?.disabled);
  const skip=page.getByRole('button',{name:'Saltar',exact:true});if(await skip.isVisible())await skip.click();
  assert.equal(await page.evaluate(()=>ROL()),'lector');
  const ids=await page.locator('[data-open]').evaluateAll(els=>els.map(e=>e.dataset.open));assert.ok(ids.includes(slug));
  let frames=0;
  for(const id of ids){result.ultimo_paso={pasada:k,pieza:id};await page.locator('[data-open="'+id+'"]').click();const photos=page.locator('.bt-frame img');const count=await page.locator('.bt-frame').count();assert.equal(await photos.count(),count);for(let j=0;j<count;j++)await loaded(photos.nth(j));frames+=count;await page.locator('.bt-nav [data-back]').click();}
  await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:dir+'/pasada-'+k+'-tablero.jpg',type:'jpeg',quality:80,fullPage:true});
  await page.locator('[data-open="'+slug+'"]').click();assert.equal(await page.locator('.bt-frame').count(),5);await page.screenshot({path:dir+'/pasada-'+k+'-tira.jpg',type:'jpeg',quality:85,fullPage:true});
  const options=[];
  for(const number of [2,3,4,5]){result.ultimo_paso={pasada:k,pieza:slug,lamina:number};
   await page.locator('.bt-photo[data-lamina="'+number+'"]').click();
   assert.equal(await page.locator('[data-option]').count(),2);
   for(let option=0;option<2;option++){
    await page.locator('[data-option="'+option+'"]').click();await loaded(page.locator('.bt-main-photo'));
    const src=await page.locator('.bt-main-photo').getAttribute('src');assert.ok(src.startsWith('https://github.com/yodesarrollomx/sala-edicion/releases/download/'));
    options.push({lamina:number,opcion:option+1,src});
    if(number===2)await page.screenshot({path:dir+'/pasada-'+k+'-lamina2-opcion'+(option+1)+'.jpg',type:'jpeg',quality:85,fullPage:true});
   }
   await page.locator('.bt-choice-top [data-back]').click();
  }
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  result.passes.push({pasada:k,inicio:start,fin:new Date().toISOString(),viewport:mobile?'movil':'escritorio',columnas:ids.length,laminas_recorridas:frames,opciones:options,errores:errors,escrituras:writes.length,ok:true});
  fs.writeFileSync(dir+'/resultado.json',JSON.stringify(result,null,2));console.log('PASADA_REAL '+JSON.stringify(result.passes.at(-1)));await context.close();
 }
 result.ok=true;
 }catch(e){if(activePage)await activePage.screenshot({path:dir+'/fallo.jpg',type:'jpeg',quality:80,fullPage:true}).catch(()=>{});result.ok=false;result.error=e.message;console.error('FALLO_REAL '+e.message);process.exitCode=1;}
 finally{fs.writeFileSync(dir+'/resultado.json',JSON.stringify(result,null,2));if(browser)await browser.close();}
})();
