const {chromium}=require('playwright'); const fs=require('fs');
(async()=>{
const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1366,height:900}});const errors=[];
await page.route('**/*',r=>r.request().method()==='GET'||r.request().method()==='HEAD'?r.continue():r.abort());
page.on('pageerror',e=>errors.push(e.message.slice(0,200)));
await page.goto('https://yodesarrollomx.github.io/sala-edicion/',{waitUntil:'domcontentloaded'});
await page.waitForTimeout(18000);
const state=await page.evaluate(()=>({title:document.title,columns:document.querySelectorAll('.bt-column').length,frames:document.querySelectorAll('.bt-frame').length,empty:document.querySelector('.bt-empty')?.innerText,heading:document.querySelector('.bt-heading')?.innerText,role:typeof ROL==='function'?ROL():null,data:typeof D!=='undefined'&&D?{fecha:D.fecha,props:D.propuestas?.length,todas:D._todas?.length,respaldo:D._respaldo}:null,tiras:typeof TIRAS!=='undefined'?Object.keys(TIRAS).length:null}));
const m=await (await fetch('https://yodesarrollomx.github.io/sala-edicion/datos/manifiesto.json?audit='+Date.now())).json();
state.manifiesto={fecha:m.fecha,props:m.propuestas?.length,todas:m._todas?.length,tipos:m.propuestas?.map(p=>({tipo:p.tipo,laminas:p.laminas?.length,opciones:p.opciones?.length}))};state.errors=errors;
fs.mkdirSync('evidencia',{recursive:true});await page.screenshot({path:'evidencia/mesa-publica.png',fullPage:true});
fs.writeFileSync('evidencia/diagnostico.json',JSON.stringify(state,null,2));console.log('DIAGNOSTICO '+JSON.stringify(state));await browser.close();
})().catch(e=>{console.error(e.message);process.exit(1)});
