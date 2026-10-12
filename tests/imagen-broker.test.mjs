import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm,readFile,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {Readable} from 'node:stream';
import {createSalaImageBroker} from '../nube/imagen_api_broker.mjs';
const ID='a'.repeat(64),IMG=Buffer.alloc(100,7).toString('base64');
async function setup(fn,extra={}){
 const dir=await mkdtemp(join(tmpdir(),'sala-broker-test-'));
 const fetchImpl=extra.fetchImpl||(async()=>({ok:true,status:200,text:async()=>JSON.stringify({data:[{b64_json:IMG}]})}));
 try{await fn(createSalaImageBroker({env:{SALA_IMAGE_ENABLED:'true',SALA_IMAGE_TOKEN:'synthetic-token',OPENAI_API_KEY:'synthetic-provider-key',YOD_PERSISTENT_STORAGE_CONFIRMED:'true',YOD_STATE_DIR:dir,...extra},fetchImpl}),dir);}
 finally{await rm(dir,{recursive:true,force:true});}
}
async function call(broker,{method='POST',url='/sala/image',token='synthetic-token',body={request_id:ID,prompt:'Synthetic scene'}}={}){
 const req=Readable.from([JSON.stringify(body)]);Object.assign(req,{method,url,headers:{authorization:'Bearer '+token}});
 let status,raw;const res={writeHead(s){status=s;},end(s){raw=s;}};
 await broker.handle(req,res);return {status,body:JSON.parse(raw)};
}
test('autenticación antes de solicitar proveedor',async()=>{let calls=0;
 await setup(async b=>{assert.equal((await call(b,{token:'wrong'})).status,401);assert.equal(calls,0);},{fetchImpl:async()=>{calls++;}});
});
test('modelo y formato fijos sin claves en respuesta',async()=>{let payload;
 await setup(async b=>{const r=await call(b);assert.equal(r.status,200);assert.equal(r.body.model,'gpt-image-1.5');assert.equal(r.body.image,IMG);assert.ok(!JSON.stringify(r.body).includes('synthetic-provider-key'));},{fetchImpl:async(url,o)=>{assert.equal(url,'https://api.openai.com/v1/images/generations');payload=JSON.parse(o.body);return{ok:true,text:async()=>JSON.stringify({data:[{b64_json:IMG}]})};}});
 assert.deepEqual([payload.model,payload.n,payload.quality,payload.output_format],['gpt-image-1.5',1,'high','png']);
});
test('solicitud repetida y lectura de recibo no generan otra imagen',async()=>{let calls=0;
 await setup(async b=>{assert.equal((await call(b)).status,200);assert.equal((await call(b)).status,200);
  assert.equal((await call(b,{method:'GET',url:'/sala/image/result/'+ID})).status,200);
  assert.equal((await call(b,{body:{request_id:ID,prompt:'Other recipe'}})).status,409);
  assert.equal(calls,1);},{fetchImpl:async()=>{calls++;return{ok:true,text:async()=>JSON.stringify({data:[{b64_json:IMG}]})};}});
});
test('fallo de transporte deja incertidumbre durable y no repite',async()=>{let calls=0;
 await setup(async(b,dir)=>{assert.equal((await call(b)).status,503);assert.equal((await call(b)).status,409);
  assert.equal((await call(b,{method:'GET',url:'/sala/image/result/'+ID})).body.error,'generation_uncertain_do_not_repeat');
  assert.equal(JSON.parse(await readFile(join(dir,'sala-images',ID+'.json'),'utf8')).phase,'uncertain');assert.equal(calls,1);
 },{fetchImpl:async()=>{calls++;throw Error('Synthetic network failure');}});
});
test('429 y límite diario permanecen explícitos',async()=>{
 await setup(async b=>assert.equal((await call(b)).status,429),{fetchImpl:async()=>({ok:false,status:429})});
 await setup(async b=>{assert.equal((await call(b)).status,200);assert.equal((await call(b,{body:{request_id:'b'.repeat(64),prompt:'Second scene'}})).status,429);},{SALA_IMAGE_DAILY_LIMIT:'1'});
});
test('campos extras, receta larga y configuración ausente no llaman proveedor',async()=>{let calls=0;
 await setup(async b=>{
  assert.equal((await call(b,{body:{request_id:ID,prompt:'Scene',model:'other'}})).status,400);
  assert.equal((await call(b,{body:{request_id:ID,prompt:'x'.repeat(5001)}})).status,400);assert.equal(calls,0);
 },{fetchImpl:async()=>{calls++;}});
 await setup(async b=>assert.equal((await call(b,{method:'GET',url:'/sala/image/status'})).status,503),{OPENAI_API_KEY:''});
});
test('una solicitud pendiente de otro proceso no se repite al reiniciar',async()=>{
 await setup(async(b,dir)=>{
  const {mkdir}=await import('node:fs/promises');await mkdir(join(dir,'sala-images'));
  await writeFile(join(dir,'sala-images',ID+'.json'),JSON.stringify({phase:'inflight',recipe_sha:'old'}));
  assert.equal((await call(b)).status,409);
 });
});

test('diagnóstico de crédito expone código sin mensaje privado',async()=>{
 await setup(async b=>{
  const r=await call(b);assert.equal(r.status,429);assert.equal(r.body.provider_code,'insufficient_quota');
  assert.ok(!JSON.stringify(r).includes('PRIVATE-ERROR-MESSAGE'));
  const status=await call(b,{method:'GET',url:'/sala/image/status'});
  assert.equal(status.body.provider_error.provider_code,'insufficient_quota');
 },{fetchImpl:async()=>({ok:false,status:429,text:async()=>JSON.stringify({error:{code:'insufficient_quota',type:'quota',message:'PRIVATE-ERROR-MESSAGE'}})})});
});
