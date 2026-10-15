/* Transporte de derivados públicos. La identidad editorial sigue siendo la ruta lógica. */
(function(root){
"use strict";
const REPO="yodesarrollomx/sala-edicion",MAX_BYTES=25*1024*1024;
const plain=x=>!!x&&typeof x==="object"&&!Array.isArray(x);
const keys=(x,wanted)=>plain(x)&&Object.keys(x).sort().join("|")===wanted.slice().sort().join("|");
const isImage=src=>/^laminas\//.test(String(src||""));
function parsear(text){
 const value=JSON.parse(text),stack=[];
 for(const token of text.match(/"(?:[^"\\]|\\[\s\S])*"|[{}\[\],:]|[^{}\[\],:\s]+/g)||[]){
  const top=stack[stack.length-1];
  if(token==="{")stack.push({seen:new Set(),key:true});
  else if(token==="[")stack.push(null);
  else if(token==="}"||token==="]")stack.pop();
  else if(token===","&&top)top.key=true;
  else if(token===":"&&top)top.key=false;
  else if(top?.key&&token[0]==='"'){const key=JSON.parse(token);if(top.seen.has(key))throw Error("duplicate");top.seen.add(key);}
 }
 return value;
}
function validar(data){
 if(!keys(data,["schema","repo","entries"])||data.schema!==1||data.repo!==REPO||!plain(data.entries))throw Error("manifest");
 const out=Object.create(null),releases=new Map(),assets=new Map();
 for(const [path,e] of Object.entries(data.entries)){
  const ext=path.match(/^laminas\/(?:[A-Za-z0-9_-]+\/)*[A-Za-z0-9_.-]+\.(png|jpg|jpeg|webp)$/);
  if(!ext||path.length>512||path.split("/").some(p=>p==="."||p==="..")||!keys(e,["sha256","bytes","mime","release_id","asset_id","tag","url"]))throw Error("entry");
  const mime={png:"image/png",jpg:"image/jpeg",jpeg:"image/jpeg",webp:"image/webp"}[ext[1]];
  if(typeof e.sha256!=="string"||!/^[a-f0-9]{64}$/.test(e.sha256)||!Number.isSafeInteger(e.bytes)||e.bytes<1||e.bytes>MAX_BYTES||e.mime!==mime||
    !Number.isSafeInteger(e.release_id)||e.release_id<1||!Number.isSafeInteger(e.asset_id)||e.asset_id<1||
    typeof e.tag!=="string"||!/^sala-media-[0-9a-f]{64}-(mesa|arranque)$/.test(e.tag)||
    e.url!=="https://github.com/"+REPO+"/releases/download/"+e.tag+"/"+e.sha256+"."+ext[1])throw Error("entry");
  const identity=JSON.stringify([e.sha256,e.bytes,e.mime,e.release_id,e.tag,e.url]);
  if(releases.has(e.release_id)&&releases.get(e.release_id)!==e.tag||assets.has(e.asset_id)&&assets.get(e.asset_id)!==identity)throw Error("identity");
  releases.set(e.release_id,e.tag);assets.set(e.asset_id,identity);
  out[path]=Object.freeze({...e});
 }
 return Object.freeze(out);
}
function crear(env){
 let state="pendiente",entries=Object.create(null),flight=null;
 const ready=()=>state==="legado"||state==="listo";
 const resolver=src=>isImage(src)&&!ready()?"":entries[src]?.url||src;
 const vista=(src,legacy)=>{
  if(isImage(src)&&!ready())return "";
  if(entries[src])return entries[legacy]?.url||entries[src].url;
  return resolver(legacy);
 };
 const fuentes=(src,legacy)=>{
  if(isImage(src)&&!ready())return [];
  const light=String(src||"").replace(/\.png$/i,".jpg");
  if(entries[src]||entries[light])return [...new Set([entries[light]?.url,entries[src]?.url].filter(Boolean))];
  return [...new Set(legacy.filter(Boolean).map(resolver).filter(Boolean))];
 };
 const reintentar=url=>Object.values(entries).some(e=>e.url===url)?url:url+(url.includes("?")?"&":"?")+"reintentar="+Date.now();
 async function cargar(){
  if(flight)return flight;
  state="pendiente";
  flight=(async()=>{
   const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),12000);
   try{
    const nonce=Date.now(),opts={cache:"no-store",signal:controller.signal,credentials:"omit"};
    const [manifest,receipt]=await Promise.all([env.fetch("datos/medios-publicos.json?v="+nonce,opts),env.fetch("version-online.json?v="+nonce,opts)]);
    let pin;
    if(receipt.ok){const value=await receipt.json();if(!plain(value))throw Error("receipt");pin=value.media_manifest_sha256;}
    else if(receipt.status!==404)throw Error("receipt");
    if(pin!==undefined&&!/^[a-f0-9]{64}$/.test(pin))throw Error("pin");
    if(manifest.status===404){if(pin!==undefined)throw Error("missing");entries=Object.create(null);state="legado";return state;}
    if(!manifest.ok||!pin)throw Error("manifest");
    const bytes=await manifest.arrayBuffer();
    if(bytes.byteLength>2*1024*1024||!env.crypto?.subtle)throw Error("manifest");
    const hash=Array.from(new Uint8Array(await env.crypto.subtle.digest("SHA-256",bytes)),b=>b.toString(16).padStart(2,"0")).join("");
    if(hash!==pin)throw Error("pin");
    const decoded=new TextDecoder("utf-8",{fatal:true}).decode(bytes);
    entries=validar(parsear(decoded));state="listo";
   }catch(e){entries=Object.create(null);state="error";}
   finally{clearTimeout(timer);}
   return state;
  })();
  try{return await flight;}finally{flight=null;}
 }
 return Object.freeze({cargar,resolver,vista,fuentes,reintentar,disponible:ready,estado:()=>state});
}
const api={validar,crear};
if(typeof module==="object"&&module.exports)module.exports=api;
if(root&&root.document)root.SalaMedios=crear({fetch:(...args)=>root.fetch(...args),crypto:root.crypto});
})(typeof window!=="undefined"?window:null);
