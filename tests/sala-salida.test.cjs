/* Salida de la Sala corta: la parte sin pantalla de sala-salida.js. */
const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');
const s=require('../sala-salida.js');
const paquete=(orden,n=2)=>({orden,sello:'a'.repeat(12),imagenes:Array.from({length:n},(_,i)=>({n:i+1,src:`laminas/x/L${i+1}.png`}))});

test('sólo cuenta como lista la pieza con paquete que no ha salido, en el orden de sus carpetas',()=>{
  const exp={'Tres':{paquete:paquete(3)},'Uno':{paquete:paquete(1)},'Sin paquete':{estado:'en camino'},'Ya salió':{paquete:paquete(2)},'Vacío':{paquete:{imagenes:[]}}};
  assert.deepEqual(s.listas(exp,n=>n==='Ya salió').map(x=>x.nombre),['Uno','Tres']);
  assert.deepEqual(s.listas({},()=>false),[]);
  assert.equal(s.paquete(null),null);assert.equal(s.paquete({paquete:'x'}),null);
});

test('el texto común se separa de lo que cada red agrega',()=>{
  const c={texto:'Hola.\nAdiós.',instagram:'Hola.\nAdiós.\n(la liga te espera en el primer comentario)',facebook:'Hola.\nAdiós.\nhttps://x.test/?a=1',comentario:'https://x.test/?b=2',revision:['Ojo con la 3','',5]};
  assert.deepEqual(s.partes(c),{texto:'Hola.\nAdiós.',ig:'\n(la liga te espera en el primer comentario)',fb:'\nhttps://x.test/?a=1',comentario:'https://x.test/?b=2',revision:['Ojo con la 3']});
  assert.deepEqual(s.partes({texto:'A',instagram:'otra cosa'}),{texto:'A',ig:'',fb:'',comentario:'',revision:[]});
  assert.deepEqual(s.partes(undefined),{texto:'',ig:'',fb:'',comentario:'',revision:[]});
});

test('la liga de la publicación es opcional, pero si viene es una dirección https completa',()=>{
  for(const ok of ['','  ','https://www.instagram.com/p/ABC123/','https://www.facebook.com/1/posts/2'])assert.equal(s.ligaValida(ok),true,ok);
  for(const mal of ['instagram.com/p/x','http://x.test/p','javascript:alert(1)','https://x.test/a b','https://x.test/"><script>','https://'])assert.equal(s.ligaValida(mal),false,mal);
});

test('el estado de una pieza en la línea',()=>{
  const carrusel=['guion','laminas','copy','publicada'],reel=['guion','laminas','voz','escenas','corte','copy','publicada'];
  const exp={'Con paquete':{paquete:paquete(1)}};
  assert.equal(s.estado('X',new Set(),carrusel,exp,false),'guion');
  assert.equal(s.estado('X',new Set(['guion']),carrusel,exp,false),'laminas');
  assert.equal(s.estado('X',new Set(['guion','laminas']),carrusel,exp,false),'texto');
  assert.equal(s.estado('X',new Set(['guion','laminas']),reel,exp,false),'video');
  assert.equal(s.estado('Con paquete',new Set(['guion','laminas']),carrusel,exp,false),'lista');
  assert.equal(s.estado('Con paquete',new Set(['guion']),carrusel,exp,false),'laminas','sin imágenes aprobadas un paquete viejo no la vuelve lista');
  assert.equal(s.estado('Con paquete',new Set(),carrusel,exp,true),'publicada');
});

test('la Sala nunca publica ni decide desde esta pantalla',()=>{
  const fuente=fs.readFileSync(require.resolve('../sala-salida.js'),'utf8');
  // tres escrituras y sólo tres: anotar «publicada», guardar el plan de salida y pedir (o quitar) un cambio.
  // Las dos últimas son llaves de los editores en EXPEDIENTES; ninguna es una marca de la mesa.
  assert.deepEqual((fuente.match(/accion:'([a-z_]+)'/g)||[]).sort(),["accion:'expediente'","accion:'expediente'","accion:'produccion'"]);
  assert.match(fuente,/accion:'expediente',clave:CLAVE\(\),pieza:PLAN_LLAVE,expediente:plan\}/,'un expediente es el plan');
  assert.match(fuente,/accion:'expediente',clave:CLAVE\(\),pieza:CAMBIO_LLAVE\+slug,expediente:registro\}/,'el otro, la orden de cambio de una pieza');
  assert.equal(s.PLAN_LLAVE,'salida:plan');assert.equal(s.CAMBIO_LLAVE,'cambio:');
  assert.match(fuente,/function puedePedirCambio\(nombre\)\{ return !!\(DECIDE\(\)&&vivo&&!\(nombre&&esPublicada\(nombre\)\)\) \}/,'sólo un editor, con la hoja ya leída y la pieza sin publicar');
  assert.match(fuente,/async function pedirCambio\(pedido\)\{[\s\S]{0,400}?if\(!DECIDE\(\)\)[\s\S]{0,120}?if\(!vivo\)/,'pedir exige editor y hoja leída');
  assert.match(fuente,/async function quitarCambio\(slug,n\)\{[\s\S]{0,300}?if\(!DECIDE\(\)\)[\s\S]{0,120}?if\(!vivo\)/,'quitar exige editor y hoja leída');
  assert.ok(!/graph\.facebook|instagram\.com\/api|accion:'decidir'/.test(fuente));
  assert.ok(fuente.includes("correcciones().enviar("),'la anotación viaja por el transporte que no repite envíos');
  assert.match(fuente,/function cambiarPlan\(cambio,ya\)\{\s*if\(!DECIDE\(\)\) return;/,'sólo un editor cambia el plan');
});

test('con plan, el montón sale en el orden del editor; lo que el plan no nombra va al final por su carpeta',()=>{
  const exp={'Tres':{paquete:paquete(3)},'Uno':{paquete:paquete(1)},'Dos':{paquete:paquete(2)},'Cuatro':{paquete:paquete(4)},'Ya salió':{paquete:paquete(5)}};
  const plan=s.planLimpio({orden:['Cuatro','Ya salió','No existe','Dos']});
  assert.deepEqual(s.listas(exp,n=>n==='Ya salió',plan).map(x=>x.nombre),['Cuatro','Dos','Uno','Tres']);
  assert.deepEqual(s.listas(exp,()=>false,s.planLimpio(null)).map(x=>x.nombre),['Uno','Dos','Tres','Cuatro','Ya salió'],'sin plan manda el número de la carpeta');
  assert.deepEqual(s.listas(exp,()=>false).map(x=>x.nombre),['Uno','Dos','Tres','Cuatro','Ya salió']);
});

test('mover una pieza la deja en su lugar sin revolver las demás',()=>{
  const l=['a','b','c','d'];
  assert.deepEqual(s.mover(l,'d',1),['d','a','b','c']);
  assert.deepEqual(s.mover(l,'a',3),['b','c','a','d']);
  assert.deepEqual(s.mover(l,'b',99),['a','c','d','b']);
  assert.deepEqual(s.mover(l,'c',-5),['c','a','b','d']);
  assert.deepEqual(s.mover(l,'no está',2),l);
  assert.deepEqual(l,['a','b','c','d'],'no cambia la lista que recibe');
});

test('el calendario de salida reparte por semana y empieza el día de arranque o el siguiente que toque',()=>{
  // 16-nov-2026 es lunes
  assert.deepEqual(s.fechasDeSalida(5,3,'2026-11-16'),['2026-11-16','2026-11-18','2026-11-20','2026-11-23','2026-11-25']);
  assert.deepEqual(s.fechasDeSalida(3,3,'2026-11-19'),['2026-11-20','2026-11-23','2026-11-25'],'arrancando en jueves, la primera sale el viernes');
  assert.deepEqual(s.fechasDeSalida(3,7,'2026-11-21'),['2026-11-21','2026-11-22','2026-11-23']);
  assert.deepEqual(s.fechasDeSalida(2,1,'2026-11-16'),['2026-11-18','2026-11-25']);
  assert.deepEqual(s.fechasDeSalida(4,2,'2026-12-29'),['2026-12-29','2026-12-31','2027-01-05','2027-01-07'],'cruza el año');
  for(const mal of ['','mañana','2026-13-40',null,undefined]) assert.deepEqual(s.fechasDeSalida(3,3,mal),[],String(mal));
  assert.equal(s.fechasDeSalida(24,3,'2026-11-16').length,24);
  assert.deepEqual([s.alcance(24,3),s.alcance(25,3),s.alcance(1,7),s.alcance(0,3),s.alcance(10,99)],[8,9,1,0,4]);
});

test('un plan que llega mal de la hoja o del aparato queda en uno utilizable',()=>{
  assert.deepEqual(s.planLimpio(undefined),{v:1,orden:[],por_semana:3,arranque:'',cuando:'',por:''});
  assert.deepEqual(s.planLimpio('texto'),s.planLimpio(null));
  assert.deepEqual(s.planLimpio([1,2]),s.planLimpio(null));
  const p=s.planLimpio({orden:['A',' A ','',7,null,{x:1},'B'],por_semana:'5',arranque:'2026-11-16',cuando:'2026-11-10T01:00:00.000Z',por:'editor',clave:'no se copia',extra:true});
  assert.deepEqual(p,{v:1,orden:['A','B'],por_semana:5,arranque:'2026-11-16',cuando:'2026-11-10T01:00:00.000Z',por:'editor'});
  for(const ps of [0,8,-1,'x',null,2.6e9]) assert.equal(s.planLimpio({por_semana:ps}).por_semana,3,String(ps));
  assert.equal(s.planLimpio({arranque:'16/11/2026'}).arranque,'');
  assert.equal(s.planLimpio({orden:Array.from({length:900},(_,i)=>'p'+i)}).orden.length,500);
});

test('lo que se guarda en el aparato alcanza para volver a pintar y abrir, y no lleva nada que parezca llave',()=>{
  const e={estado:'lista',portada:'laminas/x/L1.png',hitos:[{que:'historia larga'}],clave:'secreta',
    paquete:{orden:2,formato:'Carrusel',url:'https://drive.google.com/drive/folders/abc',sello:'s1',id:'pieza-nube-2026-11-09-abc123',slug:'pieza',carpeta_id:'abc',token:'t',imagenes:[{n:1,src:'laminas/x/L1.png',dice:'Hola',drive:'id1',archivo:'01.png'}]},
    copy:{texto:'T',instagram:'T ig',facebook:'T fb',comentario:'https://x.test/',revision:['ojo'],por:'consejo',password:'p'}};
  const g=s.paraGuardar([{nombre:'Pieza',e,p:e.paquete}]);
  assert.deepEqual(g,{Pieza:{estado:'lista',portada:'laminas/x/L1.png',
    paquete:{orden:2,formato:'Carrusel',url:'https://drive.google.com/drive/folders/abc',sello:'s1',id:'pieza-nube-2026-11-09-abc123',slug:'pieza',imagenes:[{n:1,src:'laminas/x/L1.png',dice:'Hola'}]},
    copy:{texto:'T',instagram:'T ig',facebook:'T fb',comentario:'https://x.test/',revision:['ojo']}}});
  assert.ok(s.paquete(g.Pieza),'lo guardado sigue contando como paquete');
  assert.deepEqual(s.partes(g.Pieza.copy),s.partes(e.copy));
  assert.ok(!/secreta|"t"|"p"|historia larga/.test(JSON.stringify(g)));
});

test('la orden de cambio se lee igual que en la nube (mismo contrato que nube/sala_cambios.py)',()=>{
  const contrato=JSON.parse(fs.readFileSync(require.resolve('./fixtures/cambios-casos.json'),'utf8'));
  assert.ok(contrato.casos.length>=12);
  for(const caso of contrato.casos){
    const c=s.cambioLimpio(caso.registro), leidas=Object.fromEntries(c.ordenes.map(o=>[String(o.n),o.nota]));
    assert.deepEqual(leidas,caso.ordenes,caso.caso);
    if(Object.keys(caso.ordenes).length) assert.equal(c.tira,caso.tira,caso.caso);
    assert.deepEqual(s.ordenesVigentes(caso.registro,caso.tira||'x'),c.tira&&c.tira===caso.tira?c.ordenes:[],caso.caso);
  }
});

test('una orden vale para la versión para la que se pidió; pedir otra imagen se suma y repetir la misma la reemplaza',()=>{
  const T='48-horas-arranque-2026-09-24-e98d7d', ahora='2026-11-10T03:40:00.000Z';
  const uno=s.conOrden(null,{pieza:'Las 48 Horas',tira:T,n:1,nota:'  Quita   el plazo\n',quien:'editor',ahora});
  assert.deepEqual(uno,{v:1,pieza:'Las 48 Horas',tira:T,paquete:'',ordenes:[{n:1,nota:'Quita el plazo',cuando:ahora,por:'editor'}],cuando:ahora,por:'editor'});
  assert.deepEqual(s.ordenesVigentes(uno,T).map(o=>o.n),[1]);
  assert.deepEqual(s.ordenesVigentes(uno,'48-horas-nube-2026-11-10-abc123'),[],'cuando la mesa la rehace nace otra tira: la orden ya no aplica');
  assert.deepEqual(s.ordenesVigentes(uno,''),[]);
  const dos=s.conOrden(uno,{tira:T,n:3,nota:'Más luminosa',quien:'editor2',ahora:'b'});
  assert.deepEqual(dos.ordenes.map(o=>[o.n,o.nota,o.por]),[[1,'Quita el plazo','editor'],[3,'Más luminosa','editor2']]);
  assert.equal(dos.pieza,'Las 48 Horas','el nombre de la pieza se conserva');
  const otraNota=s.conOrden(dos,{tira:T,n:1,nota:'Mejor otra frase',quien:'editor',ahora:'c'});
  assert.deepEqual(otraNota.ordenes.map(o=>[o.n,o.nota]),[[1,'Mejor otra frase'],[3,'Más luminosa']]);
  const otraVersion=s.conOrden(dos,{tira:'48-horas-nube-2026-11-10-abc123',n:2,nota:'Otra pareja',quien:'editor',ahora:'d'});
  assert.deepEqual(otraVersion.ordenes.map(o=>o.n),[2],'con otra versión de la pieza se empieza de cero');
  assert.deepEqual(s.conOrden(uno,{tira:T,n:2,nota:'   ',quien:'editor',ahora:'e'}).ordenes.map(o=>o.n),[1],'sin nota no hay orden');
  assert.deepEqual(s.conOrden(null,{tira:'../x',n:1,nota:'x',quien:'editor',ahora:'f'}).ordenes,[],'sin una tira válida no hay orden');
  const quitada=s.sinOrden(dos,1,'editor','g');
  assert.deepEqual(quitada.ordenes.map(o=>o.n),[3]);assert.equal(quitada.tira,T);
  assert.deepEqual(s.sinOrden(quitada,3,'editor','h').ordenes,[]);
  assert.deepEqual(s.sinOrden(null,1,'editor','i'),{v:1,pieza:'',tira:'',paquete:'',ordenes:[],cuando:'i',por:'editor'});
});

test('la orden guarda la versión empacada cuando se pidió (`paquete`): sólo un id válido; la misma versión la conserva',()=>{
  const T1='uno-nube-2026-11-01-aaaaaa', T2='uno-nube-2026-11-10-bbbbbb', ahora='2026-11-10T03:40:00.000Z';
  assert.equal(s.cambioLimpio({tira:T1,paquete:T1,ordenes:[]}).paquete,T1);
  for(const mal of ['../x','','a b',7,null,undefined,{},[T1],'x'.repeat(201)]) assert.equal(s.cambioLimpio({tira:T1,paquete:mal}).paquete,'',String(mal));
  assert.equal(s.cambioLimpio(null).paquete,'');
  const uno=s.conOrden(null,{pieza:'Uno',tira:T1,paquete:T1,n:1,nota:'a',quien:'editor',ahora});
  assert.equal(uno.paquete,T1);
  const misma=s.conOrden(uno,{pieza:'Uno',tira:T1,paquete:'otro-id',n:2,nota:'b',quien:'editor',ahora});
  assert.equal(misma.paquete,T1,'misma tira: se conserva el paquete de la primera vez');
  assert.equal(s.conOrden({tira:T1,ordenes:[{n:1,nota:'a'}]},{tira:T1,paquete:T1,n:2,nota:'b',quien:'e',ahora}).paquete,T1,'si el previo no traía paquete, toma el del pedido');
  const otra=s.conOrden(uno,{pieza:'Uno',tira:T2,paquete:T1,n:1,nota:'c',quien:'editor',ahora});
  assert.deepEqual([otra.tira,otra.paquete,otra.ordenes.length],[T2,T1,1],'otra tira: empieza de cero con el paquete del pedido');
  assert.equal(s.conOrden(uno,{tira:T2,n:1,nota:'c',quien:'editor',ahora}).paquete,'','otra tira sin paquete en el pedido: queda vacío');
  assert.equal(s.sinOrden(otra,1,'editor','z').paquete,T1,'quitar la petición conserva tira y paquete');
  assert.equal(s.sinOrden(otra,1,'editor','z').tira,T2);
});

test('retiro: qué pasa con una pieza frente a su orden de cambio (todas las ramas)',()=>{
  const P1='p-aaa', P2='p-bbb', viva=(tira,paquete)=>({tira,paquete,ordenes:[{n:1,nota:'x'}]}), muerta=(tira,paquete)=>({tira,paquete,ordenes:[]});
  const casos=[
    // [descripción, cambio, empacada, enMesa, esperado]
    ['registro inválido (nulo)',null,P1,P1,''],['registro inválido (texto)','x',P1,'',''],['sin tira',{ordenes:[{n:1,nota:'x'}]},P1,P1,''],
    ['tira = empacada, viva, mesa igual',viva(P1,P1),P1,P1,'pedido'],['tira = empacada, viva, mesa sin saber',viva(P1,P1),P1,'','pedido'],
    ['tira = empacada, viva, la mesa ya trae otra versión',viva(P1,P1),P1,P2,'volvio'],
    ['tira = empacada, quitada',muerta(P1,P1),P1,P1,''],['tira = empacada, quitada, mesa otra',muerta(P1,P1),P1,P2,'volvio'],['tira = empacada, quitada, mesa sin saber',muerta(P1,P1),P1,'',''],
    ['segunda vuelta: paquete = empacada, viva, mesa en la rehecha',viva(P2,P1),P1,P2,'pedido'],
    ['segunda vuelta: viva, mesa sin saber',viva(P2,P1),P1,'','pedido'],
    ['segunda vuelta: viva, la mesa ya trae otra más nueva',viva(P2,P1),P1,'p-ccc','volvio'],
    ['segunda vuelta: quitada',muerta(P2,P1),P1,P2,'volvio'],
    ['paquete viejo ofrecido: tira rehecha sin paquete guardado',viva(P2,''),P1,P2,''],
    ['historia: el paquete ya es más nuevo que la orden',viva(P1,P1),P2,P2,''],
    ['historia: quitada y paquete más nuevo',muerta(P1,P1),P2,P2,''],
    ['sin paquete, viva, mesa en esa tira',viva(P1,''),'',P1,'pedido'],['sin paquete, viva, mesa sin saber',viva(P1,''),'','','pedido'],
    ['sin paquete, viva, la mesa trae otra (rehecha)',viva(P1,''),'',P2,''],['sin paquete, quitada',muerta(P1,''),'',P1,''],
  ];
  for(const [d,c,emp,mesa,esp] of casos) assert.equal(s.retiro(c,emp,mesa),esp,d);
  assert.equal(s.retiro(viva(P1,P1),undefined,undefined),'pedido','sin empacada ni mesa (undefined)');
  assert.equal(s.retiro(undefined,P1,P1),'');
  assert.equal(s.retiro({tira:'P0',paquete:'P0',ordenes:[]},'P0','T1'),'volvio');
  assert.equal(s.retiro({tira:'P0',paquete:'P0',ordenes:[]},'P0',''),'');
});

test('el índice carga la salida y la mesa sólo se pinta en «Te toca»',()=>{
  const html=fs.readFileSync(require.resolve('../index.html'),'utf8'),css=fs.readFileSync(require.resolve('../tablero-sala.css'),'utf8');
  assert.ok(/<script src="sala-salida\.js\?v=[^"]+"><\/script>/.test(html));assert.ok(/href="sala-salida\.css\?v=[^"]+"/.test(html));
  assert.ok(html.indexOf('id="salidaHoy"')<html.indexOf('id="tableroHoy"'));
  assert.ok(css.includes('body.sala-tablero[data-vista="hoy"] #vHoy{display:block'));
  assert.ok(!/body\.sala-tablero #vHoy\{display:block/.test(css),'sin [data-vista] la mesa tapa «Cómo va» y Ajustes');
});
