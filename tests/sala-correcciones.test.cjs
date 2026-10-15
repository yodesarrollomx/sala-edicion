const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const api=require('../sala-correcciones.js');
function fixture(){
 const map=new Map(),writes=[],rows=[];let serial=Promise.resolve(),fail=false,owner='editor',on=true,loss=false,deny=false;
 const io={storage:{getItem:k=>map.get(k)||null,setItem(k,v){if(fail)throw Error('quota');map.set(k,v);}},owner:()=>owner,authorized:()=>on,uuid:()=> 'synthetic-uuid',
  lock:(n,fn)=>{const p=serial.then(fn);serial=p.catch(()=>{});return p;},read:async()=>({produccion:rows}),post:async b=>{writes.push(b);if(deny)return {error:'solo lee'};rows.push(b);if(loss)throw Error('ACK lost');return {ok:true};}};
 const body={fecha:'2026-10-15',pieza:'ENCARGO · chinche · Fixture',detalle:JSON.stringify({id:'CHN-20261015-1100-abcd',texto:'Una corrección sintética',carta:{pid:'fixture',lamina:2,version:7}})};
 return {io,body,writes,rows,map,client:api.crear(io),setFail:v=>fail=v,setLoss:v=>loss=v,setDeny:v=>deny=v,setOwner:v=>owner=v,setOn:v=>on=v};
}
test('ACK perdido: nueva instancia concilia por lectura sin segundo append',async()=>{const f=fixture();f.setLoss(true);assert.equal((await f.client.enviar(f.body)).estado,'incierto');assert.equal(f.writes.length,1);assert.equal((await api.crear(f.io).conciliar())[0].estado,'recibido');assert.equal(f.writes.length,1);assert.equal(f.client.listar()[0].body.clave,undefined);});
test('Ventana vacía no autoriza reintento tras recarga',async()=>{const f=fixture();f.setLoss(true);await f.client.enviar(f.body);f.rows.length=0;assert.equal((await api.crear(f.io).conciliar())[0].estado,'incierto');assert.equal(f.writes.length,1);});
test('Doble clic concurrente y dos instancias conservan un POST',async()=>{const f=fixture();await Promise.all([f.client.enviar(f.body),api.crear(f.io).enviar(f.body)]);assert.equal(f.writes.length,1);assert.equal(f.client.listar().length,1);});
test('Persistencia fallida impide efecto y conserva texto en UI',async()=>{const f=fixture();f.setFail(true);assert.equal((await f.client.enviar(f.body)).estado,'local');assert.equal(f.writes.length,0);});
test('Pendiente sin sesión no es recibido; otra identidad no lo transmite',async()=>{const f=fixture();f.setOn(false);assert.equal((await f.client.enviar(f.body)).estado,'pendiente');f.setOn(true);f.setOwner('editor2');await f.client.conciliar();assert.equal(f.writes.length,0);f.setOwner('editor');await f.client.conciliar();assert.equal(f.writes.length,1);});
test('Rechazo explícito conserva texto y no se reintenta ni confirma',async()=>{const f=fixture();f.setDeny(true);assert.equal((await f.client.enviar(f.body)).estado,'rechazado');await f.client.conciliar();assert.equal(f.writes.length,1);assert.match(f.client.listar()[0].body.detalle,/corrección/);});
test('Recibo distinto o cacheado no confirma identidad',async()=>{const f=fixture();f.setLoss(true);await f.client.enviar(f.body);f.rows[0]={...f.rows[0],detalle:'otra nota'};assert.equal((await f.client.conciliar())[0].estado,'incierto');f.io.read=async()=>({cache:true,produccion:[f.writes[0]]});assert.equal((await f.client.conciliar())[0].estado,'incierto');});
test('Mismo ID con texto distinto no muta ni reenvía',async()=>{const f=fixture();await f.client.enviar(f.body);const different={...f.body,detalle:JSON.stringify({id:'CHN-20261015-1100-abcd',texto:'Otra corrección'})};assert.equal((await f.client.enviar(different)).estado,'local');assert.equal(f.writes.length,1);});
test('La chinche usa contexto capturado, no la vista actual, y sólo marca ACK',async()=>{
 const html=fs.readFileSync('index.html','utf8');const source=html.slice(html.indexOf('async function chincheClavada('),html.indexOf('// 15-sep: «quita'));
 const sent=[],marked=[];let status='incierto';const context={mandarProduccion:async(...a)=>{sent.push(a);return {estado:status};},chincheMandada:id=>marked.push(id)};vm.createContext(context);vm.runInContext(source,context);
 const ch={id:'CHN-test',texto:'Texto',contexto:{vista:'hoy',carta:{pid:'original',pieza:'Original',lamina:4,version:9,src:'v9.png'}},url:'https://example.invalid/?private=synthetic#x'};
 await context.chincheClavada(ch);assert.equal(marked.length,0);assert.equal(JSON.parse(sent[0][1]).carta.version,9);assert.equal(JSON.parse(sent[0][1]).url,'https://example.invalid/');status='recibido';await context.chincheClavada(ch);assert.deepEqual(marked,['CHN-test']);
});

test('Una nota abierta no aplica después de cambiar editor o versión',()=>{
 const source=fs.readFileSync('tablero-sala.js','utf8');const vote=source.slice(source.indexOf('function vote('),source.indexOf('async function reintentarFoto('));
 for(const change of ['editor','version']){
  let owner='editor',version=1,callback,writes=0;const d={laminas:[''],notas:['']};
  const ctx={ROL:()=>owner,api:{contexto:()=>({pid:'p',version})},S:{choice:{group:'g',n:1,k:0},groups:[{id:'g',pid:'p',t:{laminas:[{n:1,estado:'rehecha'}]}}]},eligible:()=>true,markData:()=>({i:0,nota:''}),options:()=>[{src:'fixture',indiceOriginal:0}],dec:{p:d},root:{querySelector:()=>({complete:true,naturalWidth:10})},render(){},pedirNota:fn=>callback=fn,pasos:[],lockeadas:[],guardarBorrador(){writes++;},programarSubida(){},subir(){}};
  vm.createContext(ctx);vm.runInContext(vote,ctx);ctx.vote('no');if(change==='editor')owner='editor2';else version=2;callback('Cambiar fondo');assert.equal(writes,0);assert.equal(d.laminas[0],'');assert.match(ctx.S.notice,/versión o sesión cambió/);
 }
});
