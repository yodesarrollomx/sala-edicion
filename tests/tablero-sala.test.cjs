const test=require("node:test"),assert=require("node:assert/strict");
const board=require("../tablero-sala.js");
const fs=require("node:fs"),vm=require("node:vm");
test("dos finalistas sobreviven a recarga; una tercera no desplaza ni aprueba",()=>{
 const mem=new Map(),storage={getItem:k=>mem.has(k)?mem.get(k):null,setItem:(k,v)=>mem.set(k,v)};
 const context={quien:'editor',pid:'sintetica',n:3,version:2};
 const opts=[1,3,4].map(i=>({src:`toma${i}.jpg`,indiceOriginal:i,recibo_imagen:'r'+i}));
 let shortlist=board.preseleccion(storage,context,opts);
 assert.deepEqual(shortlist.cambiar(0).indices,[0]);assert.deepEqual(shortlist.cambiar(2).indices,[0,2]);
 assert.equal(shortlist.cambiar(1).limite,true);
 shortlist=board.preseleccion(storage,context,opts);assert.deepEqual(shortlist.leer(),[0,2]);
 assert.deepEqual(shortlist.cambiar(0).indices,[2]);assert.deepEqual(shortlist.cambiar(1).indices,[2,1]);
 for(const delta of [{quien:'editor2'},{pid:'otra'},{n:4},{version:3},{dice:'texto nuevo'}])assert.deepEqual(board.preseleccion(storage,{...context,...delta},opts).leer(),[]);
 assert.deepEqual(board.preseleccion(storage,context,[{...opts[0],recibo_imagen:'nuevo'},...opts.slice(1)]).leer(),[]);
 for(const quien of ['lector','agente'])assert.throws(()=>board.preseleccion(storage,{...context,quien},opts).cambiar(0));
});
test("una preselección sin almacenamiento confirmado no anuncia éxito",()=>{
 const ctx={quien:'editor',pid:'sintetica',n:1,version:1},opts=[{src:'a.jpg',indiceOriginal:2}];
 assert.throws(()=>board.preseleccion({getItem:()=>null,setItem(){throw Error('lleno');}},ctx,opts).cambiar(0));
 assert.throws(()=>board.preseleccion({getItem:()=>null,setItem(){}},ctx,opts).cambiar(0));
 assert.throws(()=>board.preseleccion({getItem:()=>'{inválido'},ctx,opts).leer());
 assert.equal(board.textoToma({dice:'texto base'},{dice:'texto de B'}),'texto de B');
});
test("el rechazo de cualquiera manda sobre un sí y sobre el estado histórico",()=>{
 assert.equal(board.estado({estado:"aprobada",src:"a.jpg"},["si","no"]),"rojo");
 assert.equal(board.estado({src:"a.jpg"},["si"]),"verde");
 assert.equal(board.estado({src:"a.jpg"},[]),"amarillo");
 assert.equal(board.estado({},[]),"produccion");
});
test("el tablero abre todas las tomas y sólo el clic explícito elige la opción visible",()=>{
 const source=fs.readFileSync(require.resolve("../tablero-sala.js"),"utf8");
 const start=source.indexOf("function ampliarOpciones(){"),end=source.indexOf("function vote(",start);
 assert.ok(start>=0&&end>start);
 let canWrite=true,opened,votes=[];
 const opts=[{src:"a.jpg",original:"a.png",indiceOriginal:1},{src:"b.jpg",original:"b.png",indiceOriginal:2}];
 const S={choice:{group:"synthetic",n:2,k:0},groups:[{id:"synthetic",pid:"synthetic",t:{laminas:[{n:2,estado:"rehecha"}]}}]};
 const ctx={S,dec:{synthetic:{}},options:()=>opts,markData:()=>({i:0}),eligible:()=>canWrite,fotoKey:board.fotoKey,
  abrirZoom:(src,opc)=>opened={src,...opc},vote:(mark,photo)=>votes.push({mark,photo,k:S.choice.k})};
 vm.runInNewContext(source.slice(start,end)+"\nthis.open=ampliarOpciones;",ctx);
 ctx.open();assert.equal(opened.src,"a.png");assert.equal(opened.galeria.length,2);assert.equal(votes.length,0);
 const photo={complete:true,naturalWidth:1080};opened.galeria[1].elegir(photo);
 assert.equal(votes.length,1);assert.equal(votes[0].mark,"si");assert.equal(votes[0].k,1);assert.equal(votes[0].photo,photo);
 canWrite=false;opened.galeria[0].elegir(photo);assert.equal(votes.length,1);
 ctx.open();assert.ok(opened.galeria.every(x=>typeof x.elegir!=="function"));
 canWrite=true;ctx.open();S.choice={group:"other",n:2,k:0};opened.galeria[0].elegir(photo);assert.equal(votes.length,1);
 assert.match(source,/\[data-full-photo\].*addEventListener\("click",ampliarOpciones\)/);
});
test("conteo conserva intentos y no duplica original PNG, miniatura JPG y candidata",()=>{
 const l={version:7,src:"laminas/v7/L2.jpg",versiones:Array.from({length:7},(_,i)=>({src:"laminas/v"+(i+1)+"/L2.png"})),candidatas:[{src:"laminas/v7/L2.jpg",original:"laminas/v7/L2.png"}]};
 assert.equal(board.intentos(l),7);
 assert.equal(board.intentos({src:"a.jpg",candidatas:[{src:"a.jpg",original:"a.png"},{src:"b.jpg",original:"b.png"}]}),2);
});
test("los controles dentro de la foto reciben su clic y los gestos de la imagen siguen funcionando",()=>{
 const source=fs.readFileSync(require.resolve("../tablero-sala.js"),"utf8");
 const start=source.indexOf("function bind(){"),end=source.indexOf("async function refresh(",start);
 const listeners={},captures=[],moves=[],votes=[];
 const hero={addEventListener:(name,fn)=>listeners[name]=fn,setPointerCapture:id=>captures.push(id)};
 const ctx={root:{querySelectorAll:()=>[],querySelector:q=>q===".bt-hero"?hero:null},S:{groups:[]},moveOption:n=>moves.push(n),vote:m=>votes.push(m)};
 vm.runInNewContext(source.slice(start,end)+"\nthis.bind=bind;",ctx);ctx.bind();
 const control={closest:()=>({tagName:"BUTTON"})},photo={closest:()=>null};
 listeners.pointerdown({target:control,isPrimary:true,pointerId:1,clientX:100,clientY:200});
 listeners.pointerup({target:control,pointerId:1,clientX:100,clientY:200});
 assert.deepEqual(captures,[],'capturar el botón retargeta el clic al lienzo y omite Reintentar');
 assert.deepEqual(votes,[]);assert.deepEqual(moves,[]);
 listeners.pointerdown({target:photo,isPrimary:true,pointerId:2,clientX:100,clientY:200});
 listeners.pointerup({target:photo,pointerId:2,clientX:20,clientY:200});
 assert.deepEqual(captures,[2]);assert.deepEqual(moves,[1]);
 listeners.pointerdown({target:photo,isPrimary:true,pointerId:3,clientX:100,clientY:200});
 listeners.pointerup({target:photo,pointerId:3,clientX:100,clientY:80});
 assert.deepEqual(votes,[],'desplazarse para leer nunca debe aprobar');
});
test("una foto fallida reintenta al tocarla y conserva el doble clic para abrir sus opciones exactas",()=>{
 const source=fs.readFileSync(require.resolve("../tablero-sala.js"),"utf8"),start=source.indexOf("function bind(){"),end=source.indexOf("async function refresh(",start);
 const failed={},button={dataset:{group:'synthetic',lamina:'2'},querySelector:()=>failed},opened=[],retried=[];
 const g={id:'synthetic'},ctx={root:{querySelectorAll:q=>q==='[data-lamina]'?[button]:[],querySelector:()=>null},S:{groups:[g],focus:'synthetic'},reintentarFoto:im=>retried.push(im),open:(...args)=>opened.push(args)};
 vm.runInNewContext(source.slice(start,end)+"\nthis.bind=bind;",ctx);ctx.bind();
 button.onclick();assert.deepEqual(retried,[failed]);assert.deepEqual(opened,[]);
 button.ondblclick({preventDefault(){}});assert.deepEqual(opened,[[g,2,true]]);
});

test("corte se asocia por fuente vigente exacta, sin fusionar prefijos ni votos",()=>{
 const a={pid:'source-a',t:{pieza:'REEL · Pieza A'},ejes:[],decision:'si'},b={pid:'source-b',t:{pieza:'REEL · Pieza B'},ejes:[],decision:'no'};
 const p={id:'cut-a',titulo:'REEL · corte completo · para revisar',origen:'corte-de source-a'};
 const before=JSON.stringify([p,a,b]);
 assert.equal(board.grupoDeCorte(p,[a,b]),a);
 assert.equal(board.grupoDeCorte({...p,origen:'corte-de source-b'},[a,b]),b);
 for(const origen of ['corte-de source-old','corte-de source-a extra','rehecha-de source-a',''])assert.equal(board.grupoDeCorte({...p,origen},[a,b]),null);
 assert.equal(board.grupoDeCorte(p,[a,{...a}]),null);
 assert.equal(JSON.stringify([p,a,b]),before);
});


test("avanzar conserva orden aunque la actual ya esté aprobada; vuelve sólo al final",()=>{
 const list=[1,2,3,4].map(n=>({group:'a',n,pending:n!==2}));
 assert.equal(board.siguientePendiente(list,{group:'a',n:2}).n,3);
 assert.equal(board.siguientePendiente(list,{group:'a',n:4}).n,1);
 assert.equal(board.siguientePendiente(list.map(x=>({...x,pending:false})),{group:'a',n:4}),null);
 assert.equal(board.siguientePendiente([],null),null);
 assert.equal(board.siguientePendiente(list,null).n,1);
});
test("reabrir exige nota, misma sesión, versión y origen; no modifica sin confirmación",()=>{
 const source=fs.readFileSync(require.resolve('../tablero-sala.js'),'utf8');
 const a=source.indexOf('function canReopen('),b=source.indexOf('function renderChoice',a);
 let role='editor',fresh=true,context={pid:'a',lamina:1,version:2},callback,calls=[];
 const g={id:'a',p:{_consulta:true},t:{base:'original-a',laminas:[{n:1,estado:'aprobada'}]}};
 const ctx={S:{choice:{group:'a',n:1},groups:[g]},eligible:()=>fresh&&role==='editor',ROL:()=>role,api:{contexto:()=>context},pedirNota:fn=>callback=fn,reabrirAprobada:(...args)=>calls.push(args),render(){}};
 vm.runInNewContext(source.slice(a,b)+';this.request=pedirNuevaRevision;',ctx);
 ctx.request();callback(' ');assert.equal(calls.length,0);
 ctx.request();role='lector';callback('Cambiar luz');assert.equal(calls.length,0);
 role='editor';ctx.request();context={...context,version:3};callback('Cambiar luz');assert.equal(calls.length,0);
 ctx.request();g.t.base='otro';callback('Cambiar luz');assert.equal(calls.length,0);
 ctx.request();fresh=false;callback('Cambiar luz');assert.equal(calls.length,0);
 fresh=true;ctx.request();callback(' Cambiar luz ');assert.equal(calls.length,1);assert.equal(calls[0][2],'Cambiar luz');
 assert.equal(g.t.laminas[0].estado,'aprobada');
});
