/** Private worker bridge for the EXISTING Presentation registry and deployment.
 * Portero verifies the unchanged signed proof using its existing per-case key.
 * No browser role, caller URL or owner token substitutes for that permission.
 */
function yodPresProofId_(value){return typeof value==='string'&&/^[-A-Za-z0-9_.:]{1,200}$/.test(value);}
function yodPresPermit_(proof){
 var p=proof&&proof.payload,reply;
 if(!p||!proof.worker||!['presentationRegister','presentationReceipt','presentationList','presentationAuthorization'].includes(proof.operation))throw Error('invalid_request');
 try{
  var response=UrlFetchApp.fetch(PORTERO_EXEC,{method:'post',contentType:'text/plain',payload:JSON.stringify({tipo:'despacho-v1',operation:'presentationPermit',payload:{case_id:p.case_id,proof:proof},worker:proof.worker}),muteHttpExceptions:true,followRedirects:true});
  if(response.getResponseCode()!==200)throw Error('permission_unavailable');reply=JSON.parse(response.getContentText());
 }catch(_){throw Error('permission_unavailable');}
 var digest=yodPresDigest_(YODPresentationsDomain.stable(p));
 if(!reply||reply.ok!==true||reply.case_id!==p.case_id||reply.board_case_id!==p.board_case_id||reply.operation!==proof.operation||reply.payload_hash!==digest||reply.actor?.owner!==true||reply.actor.email!==p.actor_id)throw Error('unauthorized');
 return reply;
}
function yodPresWorkerSource_(source,p){return source&&source.case_id===p.case_id&&source.ppp_id===p.board_case_id;}
function yodPresWorkerLease_(lease,p,version){
 return !!lease&&lease.job_id===version.job_id&&lease.worker_id===p.worker_id&&lease.actor_id===p.actor_id&&lease.request_id===p.request_id&&lease.source_hash===version.source.snapshot_hash&&Number.isSafeInteger(lease.lease_epoch)&&lease.lease_epoch>0&&typeof lease.lease_expires_at==='string'&&Number.isFinite(Date.parse(lease.lease_expires_at))&&Date.parse(lease.lease_expires_at)>Date.now();
}
function yodPresArtifact_(version){if(!version||version.artifact_hash!==yodPresDigest_(YODPresentationsDomain.stable(YODStoryboard.normalize(version.storyboard))))throw Error('integrity');}
function yodPresWorkerResult_(record,version,receipt,p){
 yodPresArtifact_(version);
 return {ok:true,found:true,request_id:p.request_id,case_id:p.case_id,presentation_id:record.id,presentation_version_id:version.presentation_version_id,source:version.source,artifact_hash:version.artifact_hash,receipt:receipt,url:record.metadata.url,version:YODPresentationsDomain.privateView(record).content_versions.filter(function(v){return v.presentation_version_id===version.presentation_version_id;})[0]};
}
function yodPresWorkerRequest_(proof){
 var p=proof&&proof.payload,base={request_id:p?.request_id,case_id:p?.case_id};
 try{
  if(!p||!yodPresProofId_(p.case_id)||!yodPresProofId_(p.board_case_id)||!yodPresProofId_(p.worker_id)||typeof p.actor_id!=='string'||p.actor_id.length>200)throw Error('invalid_request');
  var permit=yodPresPermit_(proof),adapter=yodPresAdapter_(),actorId=yodPresDigest_(permit.actor.email),record,version,receipt;
  if(proof.operation==='presentationList'){
   if(Object.keys(p).sort().join('|')!=='actor_id|board_case_id|case_id|worker_id')throw Error('invalid_request');
   var versions=[];adapter.catalog().forEach(function(meta){if(meta.adapter!=='ppp-storyboard-v1')return;var r=adapter.read(meta.id);if(!r.content_versions?.length||!yodPresWorkerSource_(r.content_versions[0].source,p))return;
    YODPresentationsDomain.privateView(r).content_versions.forEach(function(v){versions.push(Object.assign({},v,{presentation_id:r.id,url:r.metadata.url,registry_revision:r.revision,latest:v.presentation_version_id===r.latest_presentation_version_id}));});
   });return {ok:true,case_id:p.case_id,versions:versions};
  }
  if(proof.operation==='presentationAuthorization'){
   if(Object.keys(p).sort().join('|')!=='actor_id|authorization_id|board_case_id|case_id|presentation_id|presentation_version_id|worker_id'||!yodPresProofId_(p.presentation_id)||!yodPresProofId_(p.presentation_version_id)||!yodPresProofId_(p.authorization_id))throw Error('invalid_request');
   record=adapter.read(p.presentation_id);version=(record.content_versions||[]).filter(function(v){return v.presentation_version_id===p.presentation_version_id;})[0];
   var authorization=(record.production_authorizations||[]).filter(function(a){return a.authorization_id===p.authorization_id&&a.presentation_version_id===p.presentation_version_id;})[0];
   if(record.metadata?.adapter!=='ppp-storyboard-v1'||!version||version.stage!=='storyboard'||!yodPresWorkerSource_(version.source,p)||!authorization||authorization.actor_id!==actorId||authorization.snapshot_hash!==version.source.snapshot_hash)throw Error('unauthorized');
   yodPresArtifact_(version);
   return {ok:true,case_id:p.case_id,presentation_id:record.id,presentation_version_id:version.presentation_version_id,authorization_id:authorization.authorization_id,source:version.source,artifact_hash:version.artifact_hash,registry_revision:record.revision,latest:record.latest_presentation_version_id===version.presentation_version_id,authorization:authorization};
  }
  if(!yodPresProofId_(p.presentation_id)||!yodPresProofId_(p.request_id))throw Error('invalid_request');
  if(proof.operation==='presentationRegister'){
   if(Object.keys(p).sort().join('|')!=='actor_id|board_case_id|case_id|lease|presentation_id|registration|request_id|worker_id')throw Error('invalid_request');
   var registration=p.registration,v=registration?.data?.version;
   if(!registration||registration.op!=='register_storyboard'||registration.id!==p.presentation_id||registration.requestId!==p.request_id||Object.keys(registration).sort().join('|')!=='data|id|op|requestId'||!v||!yodPresWorkerSource_(v.source,p))throw Error('invalid_request');
   if(!yodPresWorkerLease_(p.lease,p,v))throw Error('lease_expired');
   adapter.auth=function(){return {ok:true,id:actorId,owner:false};};
   // This validates the received lease's binding and expiry, NOT its current
   // epoch in the cloud journal. The worker fences that epoch before dispatch;
   // the registry additionally enforces revision, parent and idempotent IDs.
   adapter.authorizeGeneration=function(actor,request){return actor.id===actorId&&YODPresentationsDomain.stable({op:request.op,id:request.id,requestId:request.requestId,data:request.data})===YODPresentationsDomain.stable(registration)&&yodPresWorkerLease_(p.lease,p,v);};
   var result=YODPresentationsDomain.createService(adapter).handle(Object.assign({},registration,{token:'server-verified-proof'}));
   if(!result.ok)return Object.assign(base,{ok:false,error:result.error==='service_unavailable'?'presentation_outcome_unknown':result.error});
   // A successful write is not enough: reread the exact content and receipt.
   record=adapter.read(p.presentation_id);version=record.content_versions.filter(function(x){return x.presentation_version_id===v.presentation_version_id;})[0];receipt=record.receipts.filter(function(x){return x.id===p.request_id&&x.actor===actorId;})[0];
   if(!version||!receipt||receipt.presentation_version_id!==version.presentation_version_id||receipt.job_id!==v.job_id||version.job_id!==v.job_id||YODPresentationsDomain.stable(version.source)!==YODPresentationsDomain.stable(v.source)||version.artifact_hash!==yodPresDigest_(YODPresentationsDomain.stable(YODStoryboard.normalize(v.storyboard))))throw Error('integrity');
   return yodPresWorkerResult_(record,version,receipt,p);
  }
  if(proof.operation==='presentationReceipt'){
   if(Object.keys(p).sort().join('|')!=='actor_id|board_case_id|case_id|job_id|presentation_id|presentation_version_id|request_id|source_hash|worker_id'||!yodPresProofId_(p.job_id)||!yodPresProofId_(p.presentation_version_id)||!/^[a-f0-9]{64}$/.test(p.source_hash||''))throw Error('invalid_request');
   return adapter.lock(function(){
    var indexed=yodPresIndex_().records.some(function(r){return r.id===p.presentation_id;});
    if(indexed)record=adapter.read(p.presentation_id);
    else{var orphan=yodPresNamedFile_(yodPresPrivateFolder_(),'presentation-'+p.presentation_id+'.json');if(!orphan)return Object.assign(base,{ok:true,found:false});record=JSON.parse(orphan.getBlob().getDataAsString('UTF-8'));}
    if(record.id!==p.presentation_id||record.metadata?.adapter!=='ppp-storyboard-v1')throw Error('integrity');
    version=(record.content_versions||[]).filter(function(v){return v.presentation_version_id===p.presentation_version_id;})[0];
    receipt=(record.receipts||[]).filter(function(r){return r.id===p.request_id&&r.actor===actorId;})[0];
    if(!version||!receipt)return Object.assign(base,{ok:true,found:false});
    if(!yodPresWorkerSource_(version.source,p)||version.source.snapshot_hash!==p.source_hash||version.job_id!==p.job_id||receipt.job_id!==p.job_id||receipt.presentation_version_id!==p.presentation_version_id)throw Error('request_id_reused');
    yodPresArtifact_(version);
    if(!indexed)record=adapter.create(record); // Complete only the saved index link; never regenerate content.
    return yodPresWorkerResult_(record,version,receipt,p);
   });
  }
  throw Error('invalid_request');
 }catch(error){
  var known=['invalid_request','unauthorized','permission_unavailable','lease_expired','request_id_reused','not_found','integrity','private_folder_required','backend_not_ready','busy'];
  return Object.assign(base,{ok:false,error:known.indexOf(error.message)>=0?error.message:'presentation_outcome_unknown'});
 }
}
