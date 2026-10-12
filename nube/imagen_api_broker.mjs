import {createHash,timingSafeEqual} from 'node:crypto';
import {mkdir,readFile,writeFile,rename} from 'node:fs/promises';
import {join,isAbsolute} from 'node:path';
const MODEL='gpt-image-1.5',MAX_BODY=24000;
const hash=v=>createHash('sha256').update(v).digest('hex');
export function createSalaImageBroker({env=process.env,fetchImpl=globalThis.fetch,now=Date.now}={}){
 const enabled=env.SALA_IMAGE_ENABLED==='true'&&!!env.SALA_IMAGE_TOKEN&&!!env.OPENAI_API_KEY&&env.YOD_PERSISTENT_STORAGE_CONFIRMED==='true'&&isAbsolute(env.YOD_STATE_DIR||'');
 const root=enabled?join(env.YOD_STATE_DIR,'sala-images'):null;
 const cap=Number(env.SALA_IMAGE_DAILY_LIMIT||60);let serial=Promise.resolve();
 const send=(res,status,data)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(JSON.stringify(data));};
 async function read(p){try{return JSON.parse(await readFile(p,'utf8'));}catch(e){if(e.code==='ENOENT')return null;throw e;}}
 async function save(p,value){const tmp=p+'.tmp';await writeFile(tmp,JSON.stringify(value),{mode:0o600});await rename(tmp,p);}
 async function generate(id,prompt){
  await mkdir(root,{recursive:true,mode:0o700});
  const p=join(root,id+'.json'),sha=hash(prompt),old=await read(p);
  if(old?.phase==='confirmed'){
   if(old.recipe_sha!==sha)return {status:409,body:{ok:false,error:'request_recipe_conflict'}};
   return {status:200,body:old.result};
  }
  if(old&&['inflight','uncertain'].includes(old.phase))return {status:409,body:{ok:false,error:'generation_uncertain_do_not_repeat'}};
  if(old?.retry_after>now())return {status:429,body:{ok:false,error:'provider_quota',retry_after:old.retry_after}};
  const day=new Date(now()).toISOString().slice(0,10),budgetPath=join(root,'budget.json');
  const previous=await read(budgetPath),budget=previous?.day===day?previous:{day,attempts:0};
  if(!Number.isInteger(cap)||cap<1||cap>80||budget.attempts>=cap)return {status:429,body:{ok:false,error:'daily_limit'}};
  budget.attempts++;await save(budgetPath,budget);
  await save(p,{phase:'inflight',recipe_sha:sha,started:now()});
  let r;
  try{r=await fetchImpl('https://api.openai.com/v1/images/generations',{method:'POST',
   headers:{'Authorization':'Bearer '+env.OPENAI_API_KEY,'Content-Type':'application/json','Idempotency-Key':id},
   body:JSON.stringify({model:MODEL,prompt,size:'1024x1536',quality:'high',n:1,output_format:'png'}),signal:AbortSignal.timeout(220000)});
  }catch{
   await save(p,{phase:'uncertain',recipe_sha:sha});return {status:503,body:{ok:false,error:'generation_uncertain_do_not_repeat'}};
  }
  if(!r.ok){
   const status=r.status===429?429:503;
   await save(p,{phase:'blocked',recipe_sha:sha,provider_status:r.status,retry_after:now()+3600000});
   return {status,body:{ok:false,error:'provider_unavailable',provider_status:r.status}};
  }
  let data;
  try{
   const raw=await r.text();if(raw.length>24*1024*1024)throw Error('too_large');
   data=JSON.parse(raw).data?.[0]?.b64_json;
   if(typeof data!=='string'||data.length<100||!/^[A-Za-z0-9+/=]+$/.test(data))throw Error('invalid_image');
  }catch{
   await save(p,{phase:'uncertain',recipe_sha:sha});return {status:503,body:{ok:false,error:'generation_uncertain_do_not_repeat'}};
  }
  const result={ok:true,model:MODEL,mime:'image/png',image:data,request_id:id,recipe_sha:sha,generated_at:new Date(now()).toISOString()};
  await save(p,{phase:'confirmed',recipe_sha:sha,result});
  return {status:200,body:result};
 }
 async function handle(req,res){
  const token=String(req.headers.authorization||'').replace(/^Bearer /,'');
  if(!env.SALA_IMAGE_TOKEN||!timingSafeEqual(Buffer.from(hash(token),'hex'),Buffer.from(hash(env.SALA_IMAGE_TOKEN),'hex'))){send(res,401,{ok:false,error:'unauthorized'});return;}
  if(req.method==='GET'&&req.url==='/sala/image/status'){send(res,enabled?200:503,{ok:enabled,model:MODEL,configured:enabled});return;}
  const match=req.method==='GET'&&/^\/sala\/image\/result\/([a-f0-9]{64})$/.exec(req.url||'');
  if(match&&enabled){
   try{
    const receipt=await read(join(root,match[1]+'.json'));
    if(receipt?.phase==='confirmed'){send(res,200,receipt.result);return;}
    send(res,receipt?409:404,{ok:false,error:receipt?.phase==='uncertain'||receipt?.phase==='inflight'?'generation_uncertain_do_not_repeat':'not_confirmed'});return;
   }catch{send(res,503,{ok:false,error:'receipt_unavailable'});return;}
  }
  if(req.method!=='POST'||req.url!=='/sala/image'){send(res,404,{ok:false,error:'not_found'});return;}
  if(!enabled){send(res,503,{ok:false,error:'broker_not_configured'});return;}
  let body;
  try{
   let raw='';for await(const chunk of req){raw+=chunk.toString();if(Buffer.byteLength(raw)>MAX_BODY)throw Error('large');}
   body=JSON.parse(raw);
   if(!body||Object.keys(body).some(k=>!['request_id','prompt'].includes(k))||!/^[a-f0-9]{64}$/.test(body.request_id||'')||typeof body.prompt!=='string'||body.prompt.length<1||body.prompt.length>5000)throw Error('invalid');
  }catch{send(res,400,{ok:false,error:'invalid_request'});return;}
  const task=serial.then(()=>generate(body.request_id,body.prompt));serial=task.catch(()=>{});
  try{const r=await task;send(res,r.status,r.body);}catch{send(res,503,{ok:false,error:'receipt_unavailable_do_not_repeat'});}
 }
 return {handles:url=>typeof url==='string'&&url.startsWith('/sala/image'),handle};
}
