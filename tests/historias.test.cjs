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
  assert.match(u.guionista,/SIEMPRE es un cliente/);assert.equal(u.ajustes.modelo_guion,'gemini-3.6-flash');   // el criterio de fábrica viaja con el primer guardado
  await p.click('#tabs [data-v=universo]');await p.fill('[data-nuevo=personajes]','Raúl Ferretero');await p.click('[data-agregar=personajes]');await p.waitForSelector('.aviso.bien');
  assert.ok(exp['v4:universo'].personajes['raul-ferretero']);assert.equal(exp['v4:universo'].ajustes.tope_clips_dia,4);
  await p.fill('#uGui','Escribe comedias de {n} partes.');await p.click('[data-accion=guardar-universo]');await p.waitForFunction(()=>document.querySelector('#uGui').value.startsWith('Escribe comedias'));
  assert.equal(exp['v4:universo'].guionista,'Escribe comedias de {n} partes.');assert.ok(exp['v4:universo'].personajes['raul-ferretero']);
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
  assert.match(await p.getAttribute('.ep a.liga','href'),/file\/d\/BBB\/view/);                 // siempre hay salida a Drive
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
test('personajes que se guardan y se cruzan, avisos y paquete',async()=>{
  const raul={nombre:'Raúl',industria:'ferretero',aspecto:'A man.',voz:'warm',quiere:'x'};
  const s2=Object.assign(JSON.parse(JSON.stringify(serie)),{id:'s2',titulo:'El local',personaje:'raul',personajes:{raul}});
  const exp={'v4:serie:s2':s2,'v4:dec:s2':{serie:'si',episodios:{'1':{v:1,marca:'si'},'2':{v:1,marca:'si'},'3':{v:0,marca:'no'}}},
    'v4:prod:s2':{episodios:{'1':{versiones:[{v:1,drive:'AAA',costo_usd_aprox:1.05}]},'2':{versiones:[{v:1,drive:'CCC',costo_usd_aprox:1.05,aviso:'no se pudo usar el retrato del personaje'}]}},
      retratos:{raul:{drive:'RET',de:'E01-v1'}},avisos:[{cuando:'x',texto:'«El local» episodio 3 v1 falló: omni_flash too_many_requests'}],
      paquete:{carpeta:'CARP',cuando:'x',con_textos:false,versiones:{'1':1,'2':1}}}};
  const {b,p,escritos,errores}=await abrir(exp);
  await p.click('[data-abrir=s2]');const t=await p.textContent('#vista');
  assert.match(t,/Ya tiene retrato/);assert.match(t,/lleva alrededor de 2\.10 USD/);assert.match(t,/La nube avisó: .*too_many_requests/);assert.match(t,/Aviso de la nube: no se pudo usar el retrato/);
  assert.match(await p.getAttribute('a[href*="drive/folders"]','href'),/folders\/CARP$/);assert.match(t,/sin textos para publicar/);
  await p.click('[data-accion=guardar-personaje]');await p.waitForSelector('.chip.si >> text=En el universo');
  assert.deepEqual({r:exp['v4:universo'].personajes.raul.referencia_drive,n:exp['v4:universo'].personajes.raul.nombre,m:!!exp['v4:universo'].personajes.marta},{r:'RET',n:'Raúl',m:true});
  // Marta (del universo) entra como invitada al episodio 3 de la serie de Raúl
  await p.locator('.ep details summary').nth(2).click();await p.check('[data-inv=marta][data-de="2"]');await p.click('[data-accion=guardar-serie]');await p.waitForSelector('.aviso.bien');
  assert.deepEqual(exp['v4:serie:s2'].episodios.map(e=>e.invitados),[[],[],['marta']]);
  assert.ok(escritos.every(e=>!/^v4:(prod|estado)/.test(e.pieza)));assert.deepEqual(errores,[]);await b.close();
});
test('«no va» deja fuera un episodio, se puede regresar, y un paquete viejo no se da por bueno',async()=>{
  const exp={'v4:serie:s1':serie,'v4:dec:s1':{serie:'si',episodios:{}},'v4:prod:s1':{episodios:{'1':{versiones:[{v:1,drive:'AAA'}]}},intentos:{}}};
  let x=await abrir(exp);await x.p.click('[data-abrir=s1]');
  const ep3=x.p.locator('.ep').nth(2);
  assert.equal(await ep3.locator('[data-marca=si]').count(),0);                    // sin video no hay nada que aprobar
  await ep3.locator('[data-marca=no]').click();await x.p.waitForSelector('.ep .chip.no');
  assert.deepEqual({v:exp['v4:dec:s1'].episodios['3'].v,m:exp['v4:dec:s1'].episodios['3'].marca},{v:0,m:'no'});
  assert.match(await x.p.locator('.ep').nth(2).textContent(),/No va · queda fuera/);
  assert.match(await x.p.textContent('.tarjeta .chip'),/1 por revisar · 0 de 2 aprobados/);     // la serie ya cuenta dos, no tres
  await x.p.locator('.ep').nth(2).locator('[data-marca=vuelve]').click();
  await x.p.waitForFunction(()=>/En fila para producir/.test(document.querySelectorAll('.ep')[2].textContent));
  assert.equal(exp['v4:dec:s1'].episodios['3'].marca,'');assert.deepEqual(x.errores,[]);await x.b.close();
  // todo decidido, pero el paquete que hay es de la versión anterior del episodio 1
  const hecho={'v4:serie:s1':serie,'v4:dec:s1':{serie:'si',episodios:{'1':{v:2,marca:'si'},'2':{v:1,marca:'si'},'3':{v:0,marca:'no'}}},
    'v4:prod:s1':{episodios:{'1':{versiones:[{v:1,drive:'AAA'},{v:2,drive:'BBB'}]},'2':{versiones:[{v:1,drive:'CCC'}]}},
      paquete:{carpeta:'CARP',con_textos:true,versiones:{'1':1,'2':1}}}};
  x=await abrir(hecho);assert.match(await x.p.textContent('#vista'),/Todo aprobado · la nube arma el paquete/);
  await x.p.click('[data-abrir=s1]');assert.match(await x.p.textContent('#vista'),/es el anterior/);await x.b.close();
  hecho['v4:prod:s1'].paquete.versiones={'1':2,'2':1};
  x=await abrir(hecho);assert.match(await x.p.textContent('#vista'),/Paquete listo en Drive/);assert.deepEqual(x.errores,[]);await x.b.close();
});
