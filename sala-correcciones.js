/* Transporte de correcciones: append una vez; conciliación sólo por lectura. */
(function(root){
'use strict';
const KEY='sala_produccion_v1';
function detalle(value){try{const d=JSON.parse(value);if(d&&typeof d==='object'&&!Array.isArray(d))return d;}catch(_){}return {texto:String(value||'')};}
function mensaje(r){return ({recibido:'Recibido en Producción. Puedes seguir el encargo en Tus recados.',pendiente:'Guardado en este aparato; pendiente de enviar con tu sesión.',incierto:'Guardado aquí; falta confirmar la recepción. Se comprobará sin repetir el envío.',rechazado:'Producción rechazó el envío; tu texto se conserva.',local:'No se pudo guardar el envío en este aparato. Conserva el texto y vuelve a intentarlo.'})[r.estado]||'Pendiente de confirmar.';}
function crear(io){
 const read=()=>JSON.parse(io.storage.getItem(KEY)||'[]');
 function save(rows){const raw=JSON.stringify(rows);io.storage.setItem(KEY,raw);if(io.storage.getItem(KEY)!==raw)throw Error('No se conservó el envío');}
 function put(item){const rows=read(),i=rows.findIndex(x=>x.id===item.id);if(i<0)rows.push(item);else rows[i]=item;save(rows);}
 const locks=io.lock||((name,fn)=>navigator.locks?navigator.locks.request(name,fn):Promise.reject(Error('Navegador sin bloqueo de envíos')));
 async function intentar(id){return locks('sala-produccion',async()=>{
  const item=read().find(x=>x.id===id);if(!item)return {estado:'local'};
  if(item.estado==='recibido'||item.estado==='rechazado'||item.quien!==io.owner()||!io.authorized())return item;
  if(item.estado==='incierto'){
   try{const day=await io.read();if(!day||day.error||day.ok===false||day.cache===true||!Array.isArray(day.produccion))return item;
    if(day.produccion.some(f=>f.pieza===item.body.pieza&&String(f.fecha).slice(0,10)===item.body.fecha&&f.detalle===item.body.detalle)){item.estado='recibido';item.recibido_en=new Date().toISOString();put(item);}
   }catch(_){}return item;
  }
  item.estado='incierto';put(item); // Persistir ANTES de cualquier efecto; una recarga no reenvía.
  try{const result=await io.post(item.body);
   if(result&&result.ok===true){item.estado='recibido';item.recibido_en=new Date().toISOString();}
   else if(result&&/solo lee|solo el agente|clave incorrecta|no autorizado/i.test(String(result.error||''))){item.estado='rechazado';item.error=String(result.error).slice(0,200);}
   put(item);
  }catch(_){}return item;
 });}
 async function enviar(body){
  const d=detalle(body.detalle),id=d.envio_id||((d.id||io.uuid())+':'+body.pieza);
  d.envio_id=id;
  try{await locks('sala-produccion',async()=>{const old=read().find(x=>x.id===id);if(old){if(old.body.detalle!==JSON.stringify(d)||old.body.pieza!==body.pieza)throw Error('ID con contenido distinto');return;}
   const clean={accion:'produccion',fecha:body.fecha,pieza:body.pieza,estado:body.estado||'pendiente',detalle:JSON.stringify(d),enlace:body.enlace||''};
   put({id,creado:new Date().toISOString(),chinche:d.id||null,quien:body.quien||io.owner(),estado:'pendiente',body:clean});});
   return await intentar(id);
  }catch(e){return {id,estado:'local',error:String(e.message||e)};}
 }
 async function conciliar(){const out=[];for(const item of read()){if(!['recibido','rechazado'].includes(item.estado))out.push(await intentar(item.id));}return out;}
 return {enviar,conciliar,listar:read};
}
const api={crear,mensaje,detalle};if(typeof module==='object'&&module.exports)module.exports=api;else root.SalaCorrecciones=api;
})(globalThis);
