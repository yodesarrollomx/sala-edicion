'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const story=require('./fixtures/ppp-storyboard.json');
const stable=value=>JSON.stringify(value,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);
const hash=value=>crypto.createHash('sha256').update(value).digest('hex');
const copy=value=>JSON.parse(JSON.stringify(value));
const actor='owner@example.test',worker='synthetic-worker',caseId='CASE-QA',boardId='PPP-QA',presentationId='PRS-PPP-QA';
function fixture(){
 const props=new Map(),files=new Map(),permits=[];let serial=0,revoked=false,corruptPermit=false,folderAccess='PRIVATE',failCreate=false,failIndex=false,locked=false;
 const folder={getSharingAccess:()=>folderAccess,getId:()=> 'private-folder',getFilesByName:name=>{const a=[...files.values()].filter(f=>f.name===name);return {hasNext:()=>a.length>0,next:()=>a.shift()};},createFile:(name,body)=>{
  const id='file-'+(++serial),f={name,access:'PRIVATE',getSharingAccess:()=>f.access,getId:()=>id,getBlob:()=>({getDataAsString:()=>body}),setContent:s=>{body=s;}};files.set(id,f);
  if(failCreate&&name===`presentation-${presentationId}.json`){failCreate=false;throw Error('lost-create-response');}return f;
 }};
 const sign=(operation,payload)=>{const proof={tipo:'despacho-v1',operation,payload:copy(payload),worker:{id:worker,nonce:'synthetic-nonce'}};proof.worker.signature=crypto.createHmac('sha256','isolated-test-key').update(stable({operation,payload:proof.payload,worker_id:worker})).digest('hex');return proof;};
 const context={console:{log(){}},Date,JSON,Math,Error,Array,String,Number,isFinite,
  Utilities:{DigestAlgorithm:{SHA_256:'sha256'},Charset:{UTF_8:'utf8'},computeDigest:(_,s)=>[...crypto.createHash('sha256').update(s).digest()],getUuid:()=>`synthetic-uuid-${++serial}`,newBlob:s=>({getBytes:()=>Buffer.from(s)})},
  PropertiesService:{getScriptProperties:()=>({getProperty:k=>props.get(k)||null,setProperty:(k,v)=>{if(failIndex&&k==='YOD_PRES_INDEX_V1'&&JSON.parse(v).extensionFileId){failIndex=false;throw Error('lost-index-write');}props.set(k,v);}})},
  DriveApp:{Access:{PRIVATE:'PRIVATE'},getFolderById:()=>folder,createFolder:()=>folder,getFileById:id=>{if(!files.has(id))throw Error('not_found');return files.get(id);}},MimeType:{PLAIN_TEXT:'text/plain'},
  LockService:{getScriptLock:()=>({tryLock:()=>{assert.equal(locked,false,'no nested locks');locked=true;return true;},waitLock(){assert.equal(locked,false);locked=true;},releaseLock(){locked=false;}})},
  PORTERO_EXEC:'https://portero.invalid/exec',PORTERO_RESPALDO:'https://unused.invalid/exec',CODIGO_SALA:'MK',filas:()=>[],json:x=>x,
  UrlFetchApp:{fetch:(url,options)=>{
   if(url==='https://portero.invalid/exec'&&options?.payload){
    const request=JSON.parse(options.payload);permits.push(copy(request));assert.equal(request.operation,'presentationPermit');assert.deepEqual(request.worker,request.payload.proof.worker,'original worker proof is preserved');
    const proof=request.payload.proof,p=proof.payload,valid=sign(proof.operation,p).worker.signature===proof.worker.signature&&!revoked&&p.actor_id===actor&&p.case_id===caseId&&p.board_case_id===boardId&&p.worker_id===worker;
    const reply=valid?{ok:true,actor:{owner:true,email:actor},case_id:caseId,board_case_id:boardId,operation:proof.operation,payload_hash:hash(stable(p))}:{ok:false,error:'unauthorized'};
    if(corruptPermit)reply.payload_hash='wrong';return {getResponseCode:()=>200,getContentText:()=>JSON.stringify(reply)};
   }
   if(url.startsWith('https://portero.invalid/exec?'))return {getResponseCode:()=>200,getContentText:()=>JSON.stringify({ok:true,correo:'direccion@aurumarquitectos.com',rol:'admin',boards:'*'})};
   return {getResponseCode:()=>200,getContentText:()=>JSON.stringify({schema:1,presentations:[]})};
  }}
 };
 vm.createContext(context);for(const name of ['PresentacionesDominio.gs','PresentacionesStoryboard.gs','PresentacionesYOD.gs','PresentacionesAgente.gs'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../gas',name),'utf8'),context);
 props.set('YOD_PRES_FOLDER_V1','private-folder');props.set('YOD_PRES_INDEX_V1',JSON.stringify({schema:1,records:[]}));
 const common={case_id:caseId,board_case_id:boardId,worker_id:worker,actor_id:actor};
 const makeRegister=(overrides={})=>{
  const version={presentation_version_id:'PV-QA-1',parent_version_id:null,job_id:'JOB-QA-1',source:{case_id:caseId,ppp_id:boardId,viewed_scenario_id:'viewed-a',ppp_revision:12,source_revision:'source-4',snapshot_hash:'a'.repeat(64),model_type:'vertical'},method_version:'presentacion-yod-3.0.0',renderer_version:'YOD-SB-1.0.0',storyboard:copy(story)};
  const p={...common,presentation_id:presentationId,request_id:'register-qa-1',registration:{op:'register_storyboard',id:presentationId,requestId:'register-qa-1',data:{expectedRevision:0,version}},lease:{job_id:version.job_id,worker_id:worker,actor_id:actor,lease_epoch:1,lease_expires_at:new Date(Date.now()+60000).toISOString(),request_id:'register-qa-1',source_hash:version.source.snapshot_hash},...overrides};return p;
 };
 const receipt=(p=makeRegister())=>({...common,presentation_id:p.presentation_id,request_id:p.request_id,job_id:p.registration.data.version.job_id,presentation_version_id:p.registration.data.version.presentation_version_id,source_hash:p.registration.data.version.source.snapshot_hash});
 const call=(op,p)=>context.yodPresentacionesPost_({proof:sign(op,p)});
 return {context,props,files,permits,common,makeRegister,receipt,call,sign,revoke:()=>revoked=true,corruptPermit:()=>corruptPermit=true,expose:()=>folderAccess='ANYONE',failRecord:()=>failCreate=true,failIndex:()=>failIndex=true};
}

test('signed registration uses the existing private folder and catalogue and reads its exact receipt back',()=>{
 const f=fixture(),p=f.makeRegister(),r=f.call('presentationRegister',p);
 assert.equal(r.ok,true);assert.equal(r.request_id,p.request_id);assert.equal(r.presentation_id,presentationId);assert.equal(r.presentation_version_id,'PV-QA-1');
 assert.equal(r.source.ppp_revision,12);assert.equal(r.source.viewed_scenario_id,'viewed-a');assert.equal(r.artifact_hash,hash(stable(f.context.YODStoryboard.normalize(story))));
 assert.equal(f.files.size,2,'one record and the extension of the existing index');assert.equal(f.context.yodPresAdapter_().catalog().length,1);
 assert.equal(r.version.storyboard,undefined);assert.ok(r.receipt.id);assert.equal(f.permits.length,1);
 assert.deepEqual(f.permits[0].payload.proof,f.sign('presentationRegister',p));
 const again=f.call('presentationRegister',p);assert.equal(again.ok,true);assert.deepEqual(copy(again.receipt),copy(r.receipt));assert.equal(f.files.size,2);
 const list=f.call('presentationList',f.common);assert.equal(list.versions.length,1);assert.equal(list.versions[0].registry_revision,1);assert.equal(list.versions[0].storyboard,undefined);
 assert.equal(f.context.yodPresentacionesGet_({}).data.length,0);
});

test('missing, forged, modified, revoked or mismatched permits cannot create files',()=>{
 for(const action of ['forged','modified','revoked','wrong-hash']){
  const f=fixture(),p=f.makeRegister(),proof=f.sign('presentationRegister',p);
  if(action==='forged')proof.worker.signature='a'.repeat(64);
  if(action==='modified')proof.payload.registration.data.version.storyboard.title='Untrusted';
  if(action==='revoked')f.revoke();if(action==='wrong-hash')f.corruptPermit();
  assert.equal(f.context.yodPresentacionesPost_({proof}).ok,false,action);assert.equal(f.files.size,0);
 }
 const f=fixture(),p=f.makeRegister();assert.equal(f.context.yodPresentacionesPost_({presentation:{...p.registration,token:'synthetic-browser-owner-token'}}).error,'backend_not_ready');assert.equal(f.files.size,0);
});

test('registration validates source, lease and envelope identity even after Portero accepts the signed actor',()=>{
 for(const change of [p=>p.lease.lease_expires_at=new Date(Date.now()-1).toISOString(),p=>p.lease.source_hash='b'.repeat(64),p=>p.lease.lease_epoch=0,p=>p.registration.id='PRS-OTHER',p=>p.registration.requestId='register-other',p=>p.registration.data.version.source.ppp_id='PPP-OTHER',p=>p.registration.data.version.storyboard.javascript='execute()']){
  const f=fixture(),p=f.makeRegister();change(p);assert.equal(f.call('presentationRegister',p).ok,false);assert.equal(f.files.size,0);
 }
});

test('receipt lookup needs current signed authority but not the expired execution lease and never generates content',()=>{
 const f=fixture(),p=f.makeRegister();assert.equal(f.call('presentationReceipt',f.receipt(p)).found,false);assert.equal(f.files.size,0);
 const saved=f.call('presentationRegister',p);p.lease.lease_expires_at=new Date(Date.now()-10).toISOString();
 assert.equal(f.call('presentationRegister',p).error,'lease_expired');
 const recovered=f.call('presentationReceipt',f.receipt(p));assert.equal(recovered.ok,true);assert.equal(recovered.presentation_version_id,saved.presentation_version_id);assert.equal(f.files.size,2);
 assert.equal(f.call('presentationReceipt',{...f.receipt(p),source_hash:'b'.repeat(64)}).error,'request_id_reused');
 f.revoke();assert.equal(f.call('presentationReceipt',f.receipt(p)).error,'unauthorized');
});

test('ambiguous record creation and an interrupted index link are reconciled by receipt without a second presentation',()=>{
 for(const fault of ['failRecord','failIndex']){
  const f=fixture(),p=f.makeRegister();f[fault]();const first=f.call('presentationRegister',p);assert.equal(first.ok,false);
  assert.equal([...f.files.values()].filter(x=>x.name===`presentation-${presentationId}.json`).length,1);
  const result=f.call('presentationReceipt',f.receipt(p));assert.equal(result.ok,true,fault);assert.equal(result.found,true);assert.equal(result.presentation_version_id,'PV-QA-1');
  assert.equal(f.files.size,2);assert.equal(f.context.yodPresAdapter_().catalog().length,1);assert.equal(f.context.yodPresRead_(presentationId).content_versions.length,1);
 }
});

test('private storage permissions and case boundaries are checked before serving an artifact',()=>{
 const f=fixture(),p=f.makeRegister();f.call('presentationRegister',p);f.expose();
 assert.equal(f.call('presentationReceipt',f.receipt(p)).error,'private_folder_required');assert.equal(f.call('presentationList',f.common).ok,false);
 const other=fixture(),input=other.makeRegister();other.call('presentationRegister',input);
 assert.equal(other.call('presentationList',{...other.common,case_id:'FOREIGN-CASE'}).error,'unauthorized');
 assert.equal(other.call('presentationReceipt',{...other.receipt(input),board_case_id:'FOREIGN-PPP'}).error,'unauthorized');
});

test('same source can receive a second narrative version while stale registry revisions are rejected',()=>{
 const f=fixture(),p=f.makeRegister();f.call('presentationRegister',p);
 const next=copy(p);next.request_id=next.registration.requestId=next.lease.request_id='register-qa-2';next.registration.data.expectedRevision=1;
 const v=next.registration.data.version;v.parent_version_id='PV-QA-1';v.presentation_version_id='PV-QA-2';v.job_id=next.lease.job_id='JOB-QA-2';v.storyboard.title='Narrative revision';
 assert.equal(f.call('presentationRegister',next).ok,true);assert.equal(f.context.yodPresAdapter_().catalog()[0].title,'Narrative revision');
 const stale=copy(next);stale.request_id=stale.registration.requestId=stale.lease.request_id='register-qa-3';stale.registration.data.version.job_id=stale.lease.job_id='JOB-QA-3';stale.registration.data.version.presentation_version_id='PV-QA-3';
 assert.equal(f.call('presentationRegister',stale).error,'conflict');assert.equal(f.call('presentationList',f.common).versions.length,2);
});

test('production authorization is a saved owner event, not a signed worker assertion, and production preserves its exact parent',()=>{
 const f=fixture(),p=f.makeRegister();f.call('presentationRegister',p);
 const common={...f.common,presentation_id:presentationId,presentation_version_id:'PV-QA-1',authorization_id:'PA-UNKNOWN'};
 assert.equal(f.call('presentationAuthorization',common).error,'unauthorized');
 const record=f.context.yodPresRead_(presentationId),ownerId=hash(actor);
 const adapter=f.context.yodPresAdapter_();adapter.auth=()=>({ok:true,id:ownerId,owner:true});
 const permission=f.context.YODPresentationsDomain.createService(adapter).handle({op:'authorize_production',id:presentationId,token:'isolated-owner',requestId:'authorize-owner-qa',data:{expectedRevision:record.revision,presentation_version_id:'PV-QA-1',instruction:'produce_presentation'}});
 assert.equal(permission.ok,true);
 common.authorization_id=permission.receipt.production_authorization_id;
 const verified=f.call('presentationAuthorization',common);assert.equal(verified.ok,true);assert.equal(verified.authorization_id,common.authorization_id);assert.equal(verified.registry_revision,2);assert.equal(verified.latest,true);assert.equal(verified.version,undefined);
 const production=copy(p);production.request_id=production.registration.requestId=production.lease.request_id='register-production-qa';production.registration.data.expectedRevision=2;
 const v=production.registration.data.version;v.job_id=production.lease.job_id='JOB-PRODUCTION-QA';v.presentation_version_id='PV-PRODUCTION-QA';v.parent_version_id='PV-QA-1';v.stage='presentation';v.production_authorization_id=common.authorization_id;
 const saved=f.call('presentationRegister',production);assert.equal(saved.ok,true);assert.equal(saved.version.stage,'presentation');assert.equal(f.context.yodPresRead_(presentationId).releaseRevision,null);
 const projection=f.context.YODPresentationsDomain.createService(adapter).handle({op:'read_projection',id:presentationId,token:'isolated-owner'});assert.equal(projection.ok,true);assert.equal(JSON.stringify(projection).includes('"spoken"'),false);assert.equal(JSON.stringify(projection).includes('"source_ref"'),false);
});
