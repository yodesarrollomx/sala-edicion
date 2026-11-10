// La pantalla Historias contra un Apps Script de mentira: lee, edita, decide y respeta dueños.
const {test,after}=require('node:test');const assert=require('node:assert');const path=require('node:path');const fs=require('node:fs');
const {chromium}=require('playwright');
const RAIZ=path.resolve(__dirname,'..');
// Un recorrido que falla deja su navegador abierto y el proceso nunca termina (así se colgó la revisión del 9-nov):
// todos se anotan aquí y se cierran al final, pase lo que pase.
const NAVEGADORES=[];
after(async()=>{ for(const b of NAVEGADORES) await b.close().catch(()=>{}) });
const serie={id:'s1',titulo:'El terreno',trama:'Una línea',vertice:'ppp',personaje:'marta',lugar:'terreno',creada:'2026-11-09T00:00:00Z',
  episodios:[1,2,3].map(n=>({n,titulo:'E'+n,accion:'She walks.',dialogo:'Hola '+n,gancho:'A hand.',bloque:15,continua:false}))};
async function abrir(exp,opts={}){
  const b=await chromium.launch();NAVEGADORES.push(b);const p=await b.newPage({viewport:{width:390,height:844}});p.setDefaultTimeout(8000);const escritos=[];const errores=[];const retenidas=[];
  opts.soltar=()=>{opts.lento=false;for(const f of retenidas.splice(0))f()};
  p.on('pageerror',e=>errores.push(String(e)));p.on('dialog',d=>{errores.push('diálogo: '+d.message());d.dismiss()});
  await p.route('**/*',r=>{const u=new URL(r.request().url());
    if(u.hostname==='sala.test'){const f=path.join(RAIZ,decodeURIComponent(u.pathname));
      return fs.existsSync(f)&&fs.statSync(f).isFile()?r.fulfill({body:fs.readFileSync(f),contentType:f.endsWith('.json')?'application/json':'text/html'}):r.fulfill({status:404,body:''})}
    if(u.hostname==='gas.test'){
      if(r.request().method()==='GET') return r.fulfill({contentType:'application/json',body:JSON.stringify(opts.caida?{error:'clave incorrecta'}:{ok:true,expedientes:exp})});
      const d=JSON.parse(r.request().postData());escritos.push(d);
      if(opts.soloLee) return r.fulfill({contentType:'application/json',body:JSON.stringify({error:'solo el agente'})});
      if(opts.fallaEn&&escritos.length===opts.fallaEn) return r.fulfill({contentType:'application/json',body:JSON.stringify({error:'la hoja no contestó'})});
      exp[d.pieza]=d.expediente;
      const ok=()=>r.fulfill({contentType:'application/json',body:JSON.stringify({ok:true})});
      if(!opts.lento) return ok();
      return new Promise(res=>{retenidas.push(()=>res(ok()))})}
    return r.fulfill({status:204,body:''})});
  await p.addInitScript(([gas,clave])=>{localStorage.setItem('sala_gas',gas);if(clave)localStorage.setItem('sala_clave',clave)},['https://gas.test/exec',opts.sinLlave?'':'k']);
  await p.goto('https://sala.test/historias.html');await p.waitForSelector('#vista > *');
  return {b,p,escritos,errores,opts};
}
const abre=(p,clave)=>p.click(`[data-seccion="${clave}"] > summary`);
test('sin series: usa la semilla, guarda ajustes y universo sin perder nada',async()=>{
  const exp={'La Servilleta':{pieza:'x'}};const {b,p,escritos,errores}=await abrir(exp);
  assert.match(await p.textContent('#vista'),/Todavía no hay series/);
  await p.click('#tabs [data-v=ajustes]');await p.fill('#ajTope','4');assert.match(await p.textContent('#ajCosto'),/4\.20 USD/);
  await p.click('[data-accion=guardar-ajustes]');await p.waitForSelector('.aviso.bien');
  // el universo se guarda partido: cada clase del mundo en su propia celda y lo demás en v4:universo; el mundo va primero
  assert.deepEqual(escritos.map(e=>e.pieza),['v4:mundo:personajes','v4:mundo:lugares','v4:mundo:objetos','v4:universo']);assert.ok(escritos.every(e=>e.accion==='expediente'));
  const u=exp['v4:universo'],M=c=>exp['v4:mundo:'+c];
  assert.equal(u.ajustes.tope_clips_dia,4);assert.ok(M('personajes').marta&&u.vertices.ppp&&u.formato.estilo);assert.equal(u.historias,undefined);
  assert.deepEqual([u.personajes,u.lugares,u.objetos],[undefined,undefined,undefined]);
  assert.match(u.guionista,/SIEMPRE es un cliente/);assert.equal(u.ajustes.modelo_guion,'gemini-3.6-flash');   // el criterio de fábrica viaja con el primer guardado
  assert.equal(u.version,2);assert.ok(M('objetos').servilleta&&M('lugares').terreno&&u.encuadres.seguimiento&&u.temporada.length===5&&/CONTINUIDAD/.test(u.canon));   // el canon de fábrica viaja completo
  await p.click('[data-accion=guardar-ajustes]');await p.waitForSelector('.aviso.bien');assert.match(await p.textContent('#aviso'),/No había cambios/);assert.equal(escritos.length,4);
  await p.click('#tabs [data-v=universo]');await abre(p,'sec:personajes');
  await p.fill('[data-nuevo=personajes]','Raúl Ferretero');await p.click('[data-agregar=personajes]');await p.waitForSelector('.aviso.bien');
  assert.ok(M('personajes')['raul-ferretero']);assert.equal(exp['v4:universo'].ajustes.tope_clips_dia,4);
  assert.deepEqual(escritos.slice(4).map(e=>e.pieza),['v4:mundo:personajes']);         // sólo viaja lo que cambió
  assert.ok(await p.isVisible('[data-nuevo=personajes]'));                    // la sección sigue abierta después de repintar
  assert.ok(await p.isVisible('#u-personajes-raul-ferretero-aspecto'));       // y la ficha nueva queda abierta para llenarla
  await p.fill('#u-personajes-raul-ferretero-aspecto','A tall man of fifty.');await p.selectOption('#u-personajes-raul-ferretero-objeto','plano');
  await abre(p,'sec:guionista');await p.fill('#uGui','Escribe comedias de {n} partes.');
  await abre(p,'sec:reglas');await p.fill('#uCan','El mundo es una sola cuadra.');
  await p.click('[data-accion=guardar-universo]');await p.waitForSelector('.aviso.bien');
  const g=exp['v4:universo'];
  assert.equal(g.guionista,'Escribe comedias de {n} partes.');assert.equal(g.canon,'El mundo es una sola cuadra.');
  assert.deepEqual({a:M('personajes')['raul-ferretero'].aspecto,o:M('personajes')['raul-ferretero'].objeto},{a:'A tall man of fifty.',o:'plano'});
  assert.equal(await p.inputValue('#uGui'),'Escribe comedias de {n} partes.');
  // no se quita lo que la temporada usa; sí lo que nadie usa
  await abre(p,'u:personajes:marta');await p.click('[data-quitar=personajes][data-k=marta]');assert.match(await p.textContent('#aviso'),/No se quita: lo usa la temporada/);assert.ok(M('personajes').marta);
  await p.click('[data-quitar=personajes][data-k=raul-ferretero]');await p.waitForSelector('.aviso.bien');assert.equal(M('personajes')['raul-ferretero'],undefined);
  // una imagen propia tiene que ser la liga de un archivo: la de una carpeta no se guarda y se dice
  const antes=escritos.length;
  await p.fill('#u-personajes-marta-referencia_drive','https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWx');
  await p.click('[data-accion=guardar-universo]');await p.waitForSelector('.aviso.mal');
  assert.match(await p.textContent('#aviso'),/la imagen de «Marta» no es la liga de un archivo de Drive/);assert.equal(escritos.length,antes);
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
  assert.ok(await p.isVisible('[data-ep="0"][data-campo=dialogo]'));                // lo que estaba abierto sigue abierto después de guardar
  await p.fill('[data-ep="0"][data-campo=dialogo]','Vivo en Hermosillo.');await p.click('[data-accion=guardar-serie]');
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
test('guardado partido: si una parte no llega se dice, nada queda a medias y el reintento completa',async()=>{
  const exp={};const x=await abrir(exp,{fallaEn:3});const {p}=x;       // la tercera escritura (los objetos) falla una vez
  await p.click('#tabs [data-v=ajustes]');await p.fill('#ajTope','3');await p.click('[data-accion=guardar-ajustes]');await p.waitForSelector('.aviso.mal');
  assert.match(await p.textContent('#aviso'),/Se guardó una parte, pero no todo: vuelve a tocar el botón de guardar\. la hoja no contestó/);
  assert.equal(await p.evaluate(()=>document.querySelector('#vista').inert),false);
  assert.deepEqual(Object.keys(exp).sort(),['v4:mundo:lugares','v4:mundo:personajes']);       // el mundo va primero; el universo aún no se tocó
  await p.click('#tabs [data-v=universo]');await abre(p,'sec:objetos');
  assert.ok(await p.isVisible('[data-seccion="u:objetos:servilleta"]'));                      // lo que faltó sigue viéndose: sale de la semilla, no un mundo vacío
  x.opts.fallaEn=0;await p.click('#tabs [data-v=ajustes]');await p.fill('#ajTope','3');
  await p.click('[data-accion=guardar-ajustes]');await p.waitForSelector('.aviso.bien');
  assert.deepEqual(x.escritos.slice(3).map(e=>e.pieza),['v4:mundo:objetos','v4:universo']);    // el reintento sólo manda lo que faltaba
  assert.equal(exp['v4:universo'].ajustes.tope_clips_dia,3);assert.ok(exp['v4:mundo:objetos'].servilleta);
  assert.deepEqual(x.errores,[]);await x.b.close();
});
test('personajes que se guardan y se cruzan, avisos y paquete',async()=>{
  const raul={nombre:'Raúl',industria:'ferretero',aspecto:'A man.',voz:'warm',quiere:'x'};
  const s2=Object.assign(JSON.parse(JSON.stringify(serie)),{id:'s2',titulo:'El local',personaje:'raul',personajes:{raul}});
  const exp={'v4:serie:s2':s2,'v4:dec:s2':{serie:'si',episodios:{'1':{v:1,marca:'si'},'2':{v:1,marca:'si'},'3':{v:0,marca:'no'}}},
    'v4:prod:s2':{episodios:{'1':{versiones:[{v:1,drive:'AAA',costo_usd_aprox:1.05}]},'2':{versiones:[{v:1,drive:'CCC',costo_usd_aprox:1.05,aviso:'no se pudo usar el retrato del personaje'}]}},
      avisos:[{cuando:'x',texto:'«El local» episodio 3 v1 falló: omni_flash too_many_requests'}],
      paquete:{carpeta:'CARP',cuando:'x',con_textos:false,versiones:{'1':1,'2':1}}},
    'v4:canon':{personajes:{'s2:raul':{drive:'RET-RAUL-0000000000000001',huella:'x',de:'s2:E01-v1'}}}};
  const {b,p,escritos,errores}=await abrir(exp);
  await p.click('[data-abrir=s2]');const t=await p.textContent('#vista');
  assert.match(t,/Imagen lista \(salió del piloto\)/);assert.match(t,/lleva alrededor de 2\.10 USD/);assert.match(t,/La nube avisó: .*too_many_requests/);assert.match(t,/Aviso de la nube: no se pudo usar el retrato/);
  assert.match(await p.getAttribute('a[href*="drive/folders"]','href'),/folders\/CARP$/);assert.match(t,/sin textos para publicar/);
  await p.click('[data-pasar=personajes][data-k=raul]');await p.waitForSelector('.mundo .chip.si >> text=En el universo');
  const P=exp['v4:mundo:personajes'];
  assert.deepEqual({r:P.raul.referencia_drive,n:P.raul.nombre,m:!!P.marta},{r:'RET-RAUL-0000000000000001',n:'Raúl',m:true});   // pasa al universo con su misma imagen
  // Marta (del universo) entra como invitada al episodio 3 de la serie de Raúl
  await p.locator('.ep details summary').nth(2).click();await p.check('[data-inv][data-de="2"][value=marta]');
  await p.check('[data-obj][data-de="2"][value=servilleta]');await p.selectOption('[data-ep="2"][data-campo=encuadre]','mesa');await p.fill('[data-ep="2"][data-campo=tono]','Laughing.');
  await p.selectOption('#sObj','plano');await p.click('[data-accion=guardar-serie]');await p.waitForSelector('.aviso.bien');
  const guardada=exp['v4:serie:s2'];
  assert.deepEqual(guardada.episodios.map(e=>e.invitados||[]),[[],[],['marta']]);          // lo que no se tocó queda como estaba
  assert.deepEqual({o:guardada.episodios[2].objetos,e:guardada.episodios[2].encuadre,t:guardada.episodios[2].tono,s:guardada.objeto,l:guardada.episodios[2].lugar},{o:['servilleta'],e:'mesa',t:'Laughing.',s:'plano',l:undefined});
  assert.match(await p.textContent('.mundo'),/La servilleta[\s\S]*objeto/);                 // el mundo de la serie enseña lo que ahora usa
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
test('canon: universo viejo recibe lo nuevo, temporada editable, fichas propias de la serie y candado al guardar',async()=>{
  // un universo guardado antes del canon (versión 1): al abrirlo ya trae encuadres, objetos y temporada, y al guardar queda en versión 2
  const viejo={version:1,ajustes:{tope_clips_dia:5},formato:{estilo:'viejo'},vertices:{ppp:{nombre:'Plan de Potencial'}},personajes:{marta:{nombre:'Marta',aspecto:'vieja'},mia:{nombre:'Mía'}},lugares:{terreno:{nombre:'El terreno'}}};
  const mateo={nombre:'Mateo',industria:'agricultor',aspecto:'A man of 38.',voz:'calm'};
  const s3=Object.assign(JSON.parse(JSON.stringify(serie)),{id:'s3',titulo:'El olivo',personaje:'mateo',lugar:'solar',personajes:{mateo},lugares:{solar:{nombre:'El solar',aspecto:'A lot.'}}});
  const exp={'v4:universo':viejo,'v4:serie:s3':s3,'v4:dec:s3':{serie:'si'},
    'v4:canon':{carpeta:'CANON-DRIVE',personajes:{'s3:mateo':{drive:'FICHA-MATEO'},marta:{drive:'FICHA-MARTA'}},fallas:{'lugares:s3:solar':{huella:'h',dia:'2026-11-09',motivo:'Gemini imagen 400: no'}}}};
  const x=await abrir(exp,{lento:true});const {p}=x;
  await p.click('#tabs [data-v=universo]');
  assert.match(await p.getAttribute('a[href*="drive/folders"]','href'),/folders\/CANON-DRIVE$/);
  await abre(p,'sec:temporada');await abre(p,'t:el-de-la-esquina');
  assert.match(await p.textContent('[data-seccion="t:el-de-la-esquina"] summary'),/Sin escribir todavía/);
  await p.fill('#tp1','Don Carlos mide antes de contestar.');await p.check('[data-tl="1"][data-lista=guinos][value=servilleta]');await p.selectOption('#tl1','cafe');
  await abre(p,'sec:personajes');await abre(p,'u:personajes:marta');
  assert.match(await p.textContent('[data-seccion="u:personajes:marta"]'),/verla en Drive[\s\S]*la pintó la nube/);
  assert.match(await p.getAttribute('[data-seccion="u:personajes:marta"] a','href'),/file\/d\/FICHA-MARTA\/view/);
  await p.fill('#u-personajes-marta-referencia_drive','https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWx/view');
  // mientras se guarda, la pantalla no deja teclear (lo tecleado a media espera se perdería al repintar)
  await p.click('[data-accion=guardar-universo]');
  assert.equal(await p.evaluate(()=>document.querySelector('#vista').inert),true);assert.match(await p.textContent('#aviso'),/Guardando/);
  x.opts.soltar();await p.waitForSelector('.aviso.bien');assert.equal(await p.evaluate(()=>document.querySelector('#vista').inert),false);
  const u=exp['v4:universo'],P=exp['v4:mundo:personajes'];
  assert.equal(u.version,2);assert.equal(u.ajustes.tope_clips_dia,5);assert.ok(P.mia&&P.sofia&&exp['v4:mundo:objetos'].servilleta&&u.encuadres.rostro);
  assert.equal(u.personajes,undefined);                                                      // un universo viejo queda partido al primer guardado
  assert.match(u.formato.estilo,/long take/);assert.match(P.marta.vestuario,/Olive-green/);
  assert.deepEqual({p:u.temporada[1].premisa,g:u.temporada[1].guinos.includes('servilleta'),l:u.temporada[1].lugar},{p:'Don Carlos mide antes de contestar.',g:true,l:'cafe'});
  assert.match(P.marta.referencia_drive,/1AbCdEfGhIjKlMnOpQrStUvWx/);
  assert.match(await p.textContent('[data-seccion="u:personajes:marta"]'),/la pusiste tú/);          // la imagen de Dirección manda sobre la pintada
  // subir una historia en la temporada y agregar otra
  const n=x.escritos.length;
  await p.click('[data-subir="1"]');await p.waitForSelector('.aviso.bien');assert.equal(exp['v4:universo'].temporada[0].id,'el-de-la-esquina');
  await p.fill('[data-nuevo-t]','La azotea');await p.click('[data-agregar-t]');await p.waitForSelector('.aviso.bien');
  assert.deepEqual(exp['v4:universo'].temporada.map(t=>t.id).slice(-1),['la-azotea']);
  assert.deepEqual(x.escritos.slice(n).map(e=>e.pieza),['v4:universo','v4:universo']);          // mover la temporada no reescribe el mundo
  // la serie: su mundo con la ficha pintada por la nube, y sus fichas propias se editan ahí mismo
  await p.click('#tabs [data-v=series]');await p.click('[data-abrir=s3]');
  // con la serie aprobada: lo que la nube no pudo pintar se dice con su motivo, y se avisa que el episodio espera sus imágenes
  assert.match(await p.textContent('.mundo'),/Mateo[\s\S]*protagonista[\s\S]*Imagen lista \(la pintó la nube\)[\s\S]*El solar[\s\S]*La nube no pudo pintar su imagen: Gemini imagen 400: no\. Cambia su ficha o pon tu propia imagen; si no se deja, apaga/);
  assert.match(await p.textContent('#vista'),/Un episodio no se produce hasta que lo que sale en él tenga su imagen/);
  await abre(p,'propias:s3');await abre(p,'su:personajes:mateo');await p.fill('#su-personajes-mateo-vestuario','Linen shirt and straw hat.');
  await p.fill('#su-personajes-mateo-referencia_drive','una foto que tengo por ahí');
  await p.click('[data-accion=guardar-serie]');await p.waitForSelector('.aviso.mal');assert.match(await p.textContent('#aviso'),/la imagen de «Mateo» no es la liga de un archivo/);
  assert.equal(exp['v4:serie:s3'].personajes.mateo.vestuario,undefined);                     // con una liga que no sirve no se guarda nada
  await p.fill('#su-personajes-mateo-referencia_drive','');
  await p.click('[data-accion=guardar-serie]');await p.waitForSelector('.aviso.bien');
  assert.equal(exp['v4:serie:s3'].personajes.mateo.vestuario,'Linen shirt and straw hat.');
  await abre(p,'su:lugares:solar');await p.click('[data-quitar=lugares][data-k=solar][data-de=su]');assert.match(await p.textContent('#aviso'),/esta serie lo usa/);assert.ok(exp['v4:serie:s3'].lugares.solar);
  await p.click('[data-pasar=lugares][data-k=solar]');await p.waitForSelector('.aviso.bien');assert.equal(exp['v4:mundo:lugares'].solar.nombre,'El solar');
  assert.ok(x.escritos.every(e=>!/^v4:(prod|estado|canon)/.test(e.pieza)));assert.deepEqual(x.errores,[]);await x.b.close();
});
