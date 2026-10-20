/* Última mesa de consulta. No es identidad, autorización ni cola de decisiones. */
(function(root){
  'use strict';
  const KEY='sala_mesa_local_v1', MAX=2*1024*1024, TTL=7*24*60*60*1000;
  const secret=/^(?:clave(?:_.*)?|token|access_token|refresh_token|authorization|password)$/i;
  const copy=x=>JSON.parse(JSON.stringify(x,(key,value)=>secret.test(key)?undefined:value));
  async function scope(identity,crypto){
    if(!identity||!identity.keys.length||!crypto||!crypto.subtle)return null;
    const bytes=new TextEncoder().encode(JSON.stringify([identity.endpoint,identity.role,[...identity.keys].sort()]));
    return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
  }
  function valid(x,owner,now){
    return !!(x&&x.schema===1&&x.owner===owner&&Number.isFinite(x.savedAt)&&x.savedAt<=now+60000&&now-x.savedAt<TTL&&
      x.day&&(!x.day._respaldo||x.source==='published')&&!x.day.error&&/^\d{4}-\d{2}-\d{2}$/.test(x.day.fecha||'')&&Array.isArray(x.day.propuestas)&&
      Array.isArray(x.groups)&&x.groups.every(g=>g&&typeof g.id==='string'&&typeof g.pid==='string'&&g.p&&g.t&&Array.isArray(g.t.laminas)&&Array.isArray(g.ejes)));
  }
  function clear(storage){try{storage.removeItem(KEY);}catch(e){}}
  function read(storage,owner,now=Date.now()){
    try{
      const raw=storage.getItem(KEY);if(!raw)return null;
      if(!owner||raw.length>MAX){clear(storage);return null;}
      const x=JSON.parse(raw);if(!valid(x,owner,now)){clear(storage);return null;}
      return copy(x);
    }catch(e){clear(storage);return null;}
  }
  function write(storage,owner,day,groups,now=Date.now(),source='server'){
    try{
      if(!owner)return false;
      const x=copy({schema:1,owner,savedAt:now,source,day,groups});
      if(!valid(x,owner,now))return false;
      const raw=JSON.stringify(x);if(raw.length>MAX)return false;
      storage.setItem(KEY,raw);return true;
    }catch(e){return false;}
  }
  const api={KEY,MAX,TTL,scope,read,write,clear};
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.SalaMesaLocal=api;
})(typeof window==='undefined'?{}:window);
