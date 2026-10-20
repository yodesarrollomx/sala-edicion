const test=require('node:test'),assert=require('node:assert/strict'),{webcrypto}=require('node:crypto');
const cache=require('../mesa-local.js');
const day={fecha:'2026-10-20',propuestas:[],rol:'editor',clave_nueva:'synthetic-secret',decisiones:{propuestas:{}}};
const groups=[{id:'demo',pid:'demo-v1',p:{id:'demo-v1'},t:{laminas:[]},ejes:[]}];
const storage=()=>{const map=new Map();return {map,getItem:k=>map.get(k)||null,setItem:(k,v)=>map.set(k,v),removeItem:k=>map.delete(k)}};
test('copia completa sin credenciales; no modifica las fuentes',()=>{
 const s=storage(),before=JSON.stringify(day);assert.equal(cache.write(s,'owner',day,groups,1000),true);
 const saved=cache.read(s,'owner',1001);assert.deepEqual(saved.groups,groups);assert.equal(saved.day.clave_nueva,undefined);
 assert.equal(s.getItem(cache.KEY).includes('synthetic-secret'),false);assert.equal(JSON.stringify(day),before);
});
test('aislamiento por endpoint, sesión y rol, sin claves literales en el identificador',async()=>{
 const identity={endpoint:'https://example.invalid',role:'editor',keys:['synthetic-session']};
 const a=await cache.scope(identity,webcrypto);assert.match(a,/^[a-f0-9]{64}$/);
 for(const other of [{...identity,role:'editor2'},{...identity,keys:['otra']},{...identity,endpoint:'https://other.invalid'}])assert.notEqual(await cache.scope(other,webcrypto),a);
 assert.equal(await cache.scope({...identity,keys:[]},webcrypto),null);
 const s=storage();cache.write(s,a,day,groups);assert.equal(cache.read(s,'otro'),null);assert.equal(s.getItem(cache.KEY),null);
});
test('caducidad, formato corrupto, futuro y versión desconocida se descartan',()=>{
 const s=storage();cache.write(s,'o',day,groups,1000);assert.equal(cache.read(s,'o',1000+cache.TTL),null);
 for(const raw of ['{',JSON.stringify({schema:9}),JSON.stringify({schema:1,owner:'o',savedAt:1e12})]){s.setItem(cache.KEY,raw);assert.equal(cache.read(s,'o',1000),null);}
});
test('sin almacenamiento, sin crypto o cuota llena conserva el flujo normal',async()=>{
 const s={getItem(){throw Error('privado')},setItem(){throw Error('cuota')},removeItem(){throw Error('privado')}};
 assert.equal(cache.read(s,'o'),null);assert.equal(cache.write(s,'o',day,groups),false);
 assert.equal(await cache.scope({keys:['x']},{}),null);
});
test('respaldo, respuesta rechazada o grupos inválidos nunca reemplazan la última copia',()=>{
 const s=storage();cache.write(s,'o',day,groups);const before=s.getItem(cache.KEY);
 for(const bad of [{...day,_respaldo:true},{...day,error:'rechazo'},{...day,fecha:''}])assert.equal(cache.write(s,'o',bad,groups),false);
 assert.equal(cache.write(s,'o',day,[{}]),false);assert.equal(s.getItem(cache.KEY),before);
});
test('tamaño acotado y limpieza afectan sólo a la copia, nunca borradores ni cola',()=>{
 const s=storage();s.setItem('sala_cola','cola');s.setItem('sala2-2026-10-20','borrador');
 assert.equal(cache.write(s,'o',{...day,large:'x'.repeat(cache.MAX)},groups),false);
 cache.clear(s);assert.equal(s.getItem('sala_cola'),'cola');assert.equal(s.getItem('sala2-2026-10-20'),'borrador');
});
