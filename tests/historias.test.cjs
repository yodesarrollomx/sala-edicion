// La pantalla Historias contra un Apps Script de mentira: lee, edita, decide y respeta dueños.
const {test}=require('node:test');const assert=require('node:assert');const path=require('node:path');const fs=require('node:fs');
const {chromium}=require('playwright');
const RAIZ=path.resolve(__dirname,'..');
const serie={id:'s1',titulo:'El terreno',trama:'Una línea',vertice:'ppp',personaje:'marta',lugar:'terreno',creada:'2026-11-09T00:00:00Z',
  episodios:[1,2,3].map(n=>({n,titulo:'E'+n,accion:'She walks.',dialogo:'Hola '+n,gancho:'A hand.',bloque:15,continua:false}))};
async function abrir(exp,opts={}){
  const b=await chromium.launch();const p=await b.newPage({viewport:{width:390,height:844}});const escritos=[];const errores=[];
  p.on('pageerror',e=>errores.push(String(e)));p.on('dialog',d=>{errores.push('diálogo: '+d.message());d.dismiss()});
  await p.route('**/*',r=>{const u=new URL(r.request().url());
    if(u.hostname==='sala.test'){const f=path.join(RAIZ,decodeURIComponent(u.pathname));
      return fs.existsSync(f)&&fs.statSync(f).isFile()?r.fulfill({body:fs.readFileSync(f),contentType:f.endsWith('.json')?'application/json':'text/html'}):r.fulfill({status:404,body:''})}
    if(u.hostname==='gas.test'){
      if(r.request().method()==='GET') return r.fulfill({contentType:'application/json',body:JSON.stringify(opts.caida?{error:'clave incorrecta'}:{ok:true,expedientes:exp})});
      const d=JSON.parse(r.request().postData());escritos.push(d);
      if(opts.soloLee) return r.fulfill({contentType:'application/json',body:JSON.stringify({error:'solo el agente'})});
      exp[d.pieza]=d.expediente;return r.fulfill({contentType:'application/json',body:JSON.stringify({ok:true})})}
    return r.fulfill({status:204,body:''})});
  await p.addInitScript(([gas,clave])=>{localStorage.setItem('sala_gas',gas);if(clave)localStorage.setItem('sala_clave',clave)},['https://gas.test/exec',opts.sinLlave?'':'k']);
  await p.goto('https://sala.test/historias.html');await p.waitForSelector('#vista > *');
  return {b,p,escritos,errores};
}
test('sin series: usa la semilla, guarda ajustes y universo sin perder nada',async()=>{
  const exp={'La Servilleta':{pieza:'x'}};const {b,p,escritos,errores}=await abrir(exp);
  assert.match(await p.textContent('#vista'),/Todavía no hay series/);
  await p.click('#tabs [data-v=ajustes]');await p.fill('#ajTope','4');assert.match(await p.textContent('#ajCosto'),/4\.20 USD/);
  await p.click('[data-accion=guardar-ajustes]');await p.waitForSelector('.aviso.bien');
  const u=escritos[0].expediente;assert.equal(escritos[0].pieza,'v4:universo');assert.equal(escritos[0].accion,'expediente');
  assert.equal(u.ajustes.tope_clips_dia,4);assert.ok(u.personajes.marta&&u.vertices.ppp&&u.formato.estilo);assert.equal(u.historias,undefined);
  await p.click('#tabs [data-v=universo]');await p.fill('[data-nuevo=personajes]','Raúl Ferretero');await p.click('[data-agregar=personajes]');await p.waitForSelector('.aviso.bien');
  assert.ok(exp['v4:universo'].personajes['raul-ferretero']);assert.equal(exp['v4:universo'].ajustes.tope_clips_dia,4);
  assert.deepEqual(errores,[]);await b.close();
});
test('serie: aprueba, ve el video, pide cambio sobre la versión vigente y nunca escribe producción',async()=>{
  const exp={'v4:serie:s1':serie,'v4:prod:s1':{episodios:{'1':{versiones:[{v:1,drive:'AAA'},{v:2,drive:'BBB'}]}},intentos:{}},
             'v4:dec:s1':{episodios:{'1':{v:1,marca:'cambio',nota:'vieja'}}}};
  const {b,p,escritos,errores}=await abrir(exp);
  assert.match(await p.textContent('#vista'),/espera tu decisión/);await p.click('[data-abrir=s1]');
  await p.click('[data-serie=si]');await p.waitForSelector('.aviso.bien');assert.equal(exp['v4:dec:s1'].serie,'si');
  assert.match(await p.textContent('.ep'),/Listo para que lo veas/);            // la marca de la v1 ya no aplica a la v2
  await p.click('[data-ver]');assert.match(await p.getAttribute('iframe.video','src'),/file\/d\/BBB\/preview/);
  await p.click('[data-pedir="0"]');await p.click('[data-marca=cambio]');assert.match(await p.textContent('#aviso'),/Escribe qué/);
  await p.fill('[data-nota="1"]','que sonría menos');await p.click('[data-marca=cambio]');await p.waitForSelector('.chip.azul');
  assert.deepEqual({v:exp['v4:dec:s1'].episodios['1'].v,m:exp['v4:dec:s1'].episodios['1'].marca,n:exp['v4:dec:s1'].episodios['1'].nota},{v:2,m:'cambio',n:'que sonría menos'});
  assert.ok(escritos.every(e=>!/^v4:(prod|estado)/.test(e.pieza)));
  assert.deepEqual(errores,[]);await b.close();
});
test('edición: cuenta palabras, bloquea aprobar si no cabe y guarda el texto',async()=>{
  const exp={'v4:serie:s1':JSON.parse(JSON.stringify(serie))};const {b,p,escritos,errores}=await abrir(exp);
  await p.click('[data-abrir=s1]');await p.click('.ep details summary');
  await p.fill('[data-ep="0"][data-campo=dialogo]',Array(40).fill('palabra').join(' '));
  assert.match(await p.textContent('[data-cuenta="0"]'),/40 de 38/);
  await p.click('[data-accion=guardar-serie]');await p.waitForSelector('.aviso.bien');
  assert.equal(exp['v4:serie:s1'].episodios[0].dialogo.split(' ').length,40);
  assert.ok(await p.isDisabled('[data-serie=si]'));assert.match(await p.textContent('#vista'),/no cabe en 15 segundos/);
  await p.click('.ep details summary');await p.fill('[data-ep="0"][data-campo=dialogo]','Vivo en Hermosillo.');await p.click('[data-accion=guardar-serie]');
  await p.waitForFunction(()=>/ubicación vetada/.test(document.querySelector('#vista').textContent));
  assert.equal(escritos.filter(e=>e.pieza==='v4:dec:s1').length,0);assert.deepEqual(errores,[]);await b.close();
});
test('sin llave, hoja caída y rol que sólo lee: avisa y no finge',async()=>{
  let x=await abrir({},{sinLlave:true});assert.match(await x.p.textContent('#aviso'),/No has entrado/);await x.b.close();
  x=await abrir({},{caida:true});assert.match(await x.p.textContent('#aviso'),/No pude leer la hoja/);
  await x.p.click('#tabs [data-v=ajustes]');await x.p.click('[data-accion=guardar-ajustes]');
  assert.match(await x.p.textContent('#aviso'),/no guardo a ciegas/);assert.equal(x.escritos.length,0);await x.b.close();
  x=await abrir({'v4:serie:s1':serie},{soloLee:true});await x.p.click('[data-abrir=s1]');await x.p.click('[data-serie=no]');
  await x.p.waitForSelector('.aviso.mal');assert.match(await x.p.textContent('#aviso'),/sólo la llave de Dirección/);
  assert.match(await x.p.textContent('#vista'),/espera tu decisión/);await x.b.close();
});
