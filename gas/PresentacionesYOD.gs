/** Presentation hub adapter. Uses the EXISTING Sala deployment and Portero. */
var YOD_PRES_VERSION_='PMD-1.1.0';
var YOD_PRES_CATALOG_='https://yodesarrollomx.github.io/yodesarrollo-board/presentacion/catalogo.json';
var YOD_PRES_CRM_='https://script.google.com/macros/s/AKfycby5Nhozhfx6tTLw6f4w14U3fAx4y-bF2cO4aeIApaOQxgXsvonk8ZbTw2VEUnWGTLe8lw/exec';
var YOD_PRES_OWNER_='c27e8a6088a74a82ad2c14ef7ed0d2b4b69d80c4c7bb841c95822980a28c9bad';
function yodPresDigest_(value){return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,String(value),Utilities.Charset.UTF_8).map(function(x){return ('0'+((x+256)%256).toString(16)).slice(-2);}).join('');}
function yodPresUUID_(){return Utilities.getUuid().replace(/-/g,'');}
function yodPresBaseIndex_(){var value=PropertiesService.getScriptProperties().getProperty('YOD_PRES_INDEX_V1');if(!value)throw Error('backend_not_ready');var d=JSON.parse(value);if(d.schema!==1||!Array.isArray(d.records))throw Error('backend_not_ready');return d;}
function yodPresPrivateFile_(id){var f=DriveApp.getFileById(id);if(f.getSharingAccess()!==DriveApp.Access.PRIVATE)throw Error('private_folder_required');return f;}
function yodPresPrivateFolder_(){var id=PropertiesService.getScriptProperties().getProperty('YOD_PRES_FOLDER_V1');if(!id)throw Error('backend_not_ready');var folder=DriveApp.getFolderById(id);if(folder.getSharingAccess()!==DriveApp.Access.PRIVATE)throw Error('private_folder_required');return folder;}
function yodPresIndex_(){
 var base=yodPresBaseIndex_();
 if(base.extensionFileId){var extra=JSON.parse(yodPresPrivateFile_(base.extensionFileId).getBlob().getDataAsString('UTF-8'));if(extra.schema!==1||!Array.isArray(extra.records)||extra.records.length>500)throw Error('integrity');base.records=base.records.concat(extra.records);}
 var seen={};base.records.forEach(function(r){if(!r||typeof r.id!=='string'||typeof r.fileId!=='string'||seen[r.id])throw Error('integrity');seen[r.id]=true;});return base;
}
function yodPresRead_(id){yodPresPrivateFolder_();var row=yodPresIndex_().records.filter(function(x){return x.id===id;})[0];if(!row)throw Error('not_found');var r=JSON.parse(yodPresPrivateFile_(row.fileId).getBlob().getDataAsString('UTF-8'));if(r.id!==id)throw Error('integrity');return r;}
function yodPresWrite_(record){var row=yodPresIndex_().records.filter(function(x){return x.id===record.id;})[0];if(!row)throw Error('not_found');var f=yodPresPrivateFile_(row.fileId),data=JSON.stringify(record);if(Utilities.newBlob(data).getBytes().length>8000000)throw Error('record_too_large');f.setContent(data);if(yodPresDigest_(f.getBlob().getDataAsString('UTF-8'))!==yodPresDigest_(data))throw Error('integrity');}
function yodPresNamedFile_(folder,name){var files=folder.getFilesByName(name),f=files.hasNext()?files.next():null;if(files.hasNext())throw Error('integrity');if(f&&f.getSharingAccess()!==DriveApp.Access.PRIVATE)throw Error('private_folder_required');return f;}
function yodPresCreate_(record){
 // Runs under the registry lock. The extension is an index in the SAME private
 // folder, avoiding ScriptProperties' 9 KB value limit. It is not a second
 // catalogue. Legacy records and their existing index remain unchanged.
 var folder=yodPresPrivateFolder_(),base=yodPresBaseIndex_();
 if(yodPresIndex_().records.some(function(r){return r.id===record.id;}))throw Error('conflict');
 var f=yodPresNamedFile_(folder,'presentation-'+record.id+'.json');
 if(f){
  var prior=JSON.parse(f.getBlob().getDataAsString('UTF-8')),receipt=record.receipts[record.receipts.length-1],saved=(prior.receipts||[]).filter(function(r){return r.id===receipt.id&&r.actor===receipt.actor;})[0];
  if(prior.id!==record.id||prior.metadata?.adapter!=='ppp-storyboard-v1'||!saved||saved.hash!==receipt.hash||saved.presentation_version_id!==receipt.presentation_version_id||saved.job_id!==receipt.job_id)throw Error('integrity');record=prior;
 }else f=folder.createFile('presentation-'+record.id+'.json',JSON.stringify(record),MimeType.PLAIN_TEXT);
 if(f.getSharingAccess()!==DriveApp.Access.PRIVATE)throw Error('private_folder_required');
 var indexFile=base.extensionFileId?yodPresPrivateFile_(base.extensionFileId):yodPresNamedFile_(folder,'presentation-generated-index-v1.json');
 if(!indexFile)indexFile=folder.createFile('presentation-generated-index-v1.json',JSON.stringify({schema:1,records:[]}),MimeType.PLAIN_TEXT);
 if(indexFile.getSharingAccess()!==DriveApp.Access.PRIVATE)throw Error('private_folder_required');
 var extra=JSON.parse(indexFile.getBlob().getDataAsString('UTF-8'));if(extra.schema!==1||!Array.isArray(extra.records)||extra.records.length>500)throw Error('integrity');
 var row=extra.records.filter(function(r){return r.id===record.id;});if(row.length>1||row.length&&row[0].fileId!==f.getId())throw Error('integrity');
 if(!row.length){if(extra.records.length>=500)throw Error('integrity');extra.records.push({id:record.id,fileId:f.getId()});indexFile.setContent(JSON.stringify(extra));}
 if(!base.extensionFileId){base.extensionFileId=indexFile.getId();PropertiesService.getScriptProperties().setProperty('YOD_PRES_INDEX_V1',JSON.stringify(base));}
 var actual=yodPresRead_(record.id);if(YODPresentationsDomain.stable(actual)!==YODPresentationsDomain.stable(record))throw Error('integrity');return actual;
}
function yodPresCRM_(token){
 var res=UrlFetchApp.fetch(YOD_PRES_CRM_,{method:'post',contentType:'text/plain',payload:JSON.stringify({action:'brokers_snapshot',k:token}),muteHttpExceptions:true,followRedirects:true});
 if(res.getResponseCode()!==200)throw Error('service_unavailable');var d=JSON.parse(res.getContentText());if(d.ok!==true||!Array.isArray(d.data&&d.data.opportunities))throw Error('unauthorized');return d.data;
}
function yodPresActor_(token){
 // Fresh server verification, with expiry and revocation. Never trust a browser role.
 if(typeof token!=='string'||token.length<20||token.length>500)return null;
 var v=null,porteros=[PORTERO_EXEC,PORTERO_RESPALDO];
 for(var i=0;i<porteros.length;i++){
  try{var response=UrlFetchApp.fetch(porteros[i]+'?recurso=canje&t='+encodeURIComponent(token),{muteHttpExceptions:true,followRedirects:true});
   if(response.getResponseCode()!==200)continue;
   var candidate=JSON.parse(response.getContentText());if(!candidate||typeof candidate.ok!=='boolean')continue;
   // An authoritative denial is final. A transport failure may use the configured backup.
   if(candidate.ok!==true)return null;v=candidate;break;
  }catch(e){/* no credential, URL or response is logged */}
 }
 if(!v)throw Error('service_unavailable');if(typeof v.correo!=='string'||typeof v.rol!=='string')return null;
 var role=String(v.rol).toLowerCase(),boards=String(v.boards||'');
 if(role!=='admin'&&boards.trim()!=='*'&&boards.split(',').map(function(x){return x.trim().toUpperCase();}).indexOf(CODIGO_SALA)<0)return null;
 var email=String(v.correo).trim().toLowerCase(),owner=yodPresDigest_(email)===YOD_PRES_OWNER_&&String(v.rol).toLowerCase()==='admin';
 var actor={ok:true,id:yodPresDigest_(email),name:String(v.nombre||'YOD'),owner:owner,opportunityIds:[]};
 if(!owner){try{actor.opportunityIds=yodPresCRM_(token).opportunities.map(function(o){return o.id;});}catch(e){return null;}}
 return actor;
}
function yodPresPinRows_(meta){
 var urls=[meta.url].concat(meta.aliases||[]).map(function(u){return u.replace(/[?#].*$/,'').replace(/\/$/,'');});
 return filas('PRODUCCION').map(function(row){try{var d=typeof row.detalle==='string'?JSON.parse(row.detalle):row.detalle;if(!d||!/^CHN-\d{8}-\d{4}-[a-f0-9]{4}$/.test(d.id||''))return null;var revision=d.objeto&&d.objeto.revision,source=String(revision?revision.source:d.url||'').replace(/[?#].*$/,'').replace(/\/$/,'');if(urls.indexOf(source)<0)return null;if(meta.adapter==='ppp-storyboard-v1'&&(revision?revision.context?.presentation?.presentation_id!==meta.id:d.pantalla!=='ppp-'+meta.id))return null;if(revision&&d.kind==='yod-presentation-private-v1')return {row:row,detail:d,revision:revision,kind:'legacy'};if(d.kind==='chinche-secuencia-v1')return {row:row,detail:d,kind:'sequence'};return null;}catch(e){return null;}}).filter(function(x){return x!==null;});
}
function yodPresPins_(meta,cursor){var list=yodPresPinRows_(meta),seen={},all=[];list.reverse().forEach(function(x){if(!seen[x.detail.id]){seen[x.detail.id]=true;all.push(x);}});var start=Number(cursor||0);if(!isFinite(start)||start<0||Math.floor(start)!==start)throw Error('invalid_request');var slice=all.slice(start,start+100);return {items:slice.map(function(x){return {id:x.detail.id,hash:x.kind==='legacy'?x.detail.objeto.huella:x.detail.hash,kind:x.kind,comment:x.revision?String(x.revision.comment||''):'Explicación con voz, trazos y capturas',title:x.revision?String((x.revision.context||{}).titulo||meta.title):meta.title,version:x.revision?String((x.revision.context||{}).version||''):null,created:String(x.revision?x.revision.created||'':x.row.fecha||''),hasCapture:!!(x.revision&&x.revision.capture),hasSequence:x.kind==='sequence',state:'received'};}),nextCursor:start+slice.length<all.length?String(start+slice.length):null,complete:start+slice.length>=all.length,total:all.length};}
function yodPresPin_(meta,id){var rows=yodPresPinRows_(meta).filter(function(x){return x.detail.id===id;});if(!rows.length)throw Error('not_found');var x=rows[rows.length-1];if(rows.some(function(r){return (r.kind==='legacy'?r.detail.objeto.huella:r.detail.hash)!==(x.kind==='legacy'?x.detail.objeto.huella:x.detail.hash);}))throw Error('integrity');if(x.kind==='legacy'){if(yodPresDigest_(JSON.stringify(x.revision))!==x.detail.objeto.huella)throw Error('integrity');return {kind:'legacy',revision:x.revision,hash:x.detail.objeto.huella};}var canonical=chsRow_(id);if(!canonical||canonical.hash!==x.detail.hash)throw Error('integrity');var f=chsFile_(id);if(!f)throw Error('not_found');var data=f.getBlob().getDataAsString('UTF-8');if(yodPresDigest_(data)!==x.detail.hash)throw Error('integrity');var packet=JSON.parse(data);return {kind:'sequence',packet:packet,hash:x.detail.hash};}
// Personal board state shares the existing private folder; reads never create files.
function yodPresLayoutFile_(actor){
 if(!/^[a-f0-9]{64}$/.test(actor))throw Error('unauthorized');
 var folderId=PropertiesService.getScriptProperties().getProperty('YOD_PRES_FOLDER_V1');if(!folderId)throw Error('backend_not_ready');
 var folder=DriveApp.getFolderById(folderId);if(folder.getSharingAccess()!==DriveApp.Access.PRIVATE)throw Error('private_folder_required');
 var files=folder.getFilesByName('layout-'+actor+'.json');var file=files.hasNext()?files.next():null;
 if(files.hasNext())throw Error('integrity');if(file&&file.getSharingAccess()!==DriveApp.Access.PRIVATE)throw Error('private_folder_required');return {folder:folder,file:file};
}
function yodPresLayoutRead_(actor){var found=yodPresLayoutFile_(actor);return found.file?JSON.parse(found.file.getBlob().getDataAsString('UTF-8')):null;}
function yodPresLayoutWrite_(actor,data){var found=yodPresLayoutFile_(actor),text=JSON.stringify(data);if(Utilities.newBlob(text).getBytes().length>200000)throw Error('invalid_layout');if(found.file)found.file.setContent(text);else found.folder.createFile('layout-'+actor+'.json',text,MimeType.PLAIN_TEXT);}
function yodPresAdapter_(){var props=PropertiesService.getScriptProperties();return {
 now:function(){return Date.now();},uuid:yodPresUUID_,hash:yodPresDigest_,auth:yodPresActor_,pins:yodPresPins_,pin:yodPresPin_,
 readLayout:yodPresLayoutRead_,writeLayout:yodPresLayoutWrite_,
 catalog:function(){return yodPresIndex_().records.map(function(x){return x.metadata||JSON.parse(yodPresPrivateFile_(x.fileId).getBlob().getDataAsString('UTF-8')).metadata;});},read:yodPresRead_,write:yodPresWrite_,create:yodPresCreate_,normalizeStoryboard:function(value){if(typeof YODStoryboard==='undefined')throw Error('backend_not_ready');return YODStoryboard.normalize(value);},projectStoryboard:function(value){if(typeof YODStoryboard==='undefined'||typeof YODStoryboard.project!=='function')throw Error('backend_not_ready');return YODStoryboard.project(value);},
 lock:function(fn){var l=LockService.getScriptLock();if(!l.tryLock(5000))throw Error('busy');try{return fn();}finally{l.releaseLock();}},
 session:function(id){var s=props.getProperty('YOD_PRES_SESSION_'+id);return s?JSON.parse(s):null;},
 writeSession:function(id,s){var data=JSON.stringify(s);if(Utilities.newBlob(data).getBytes().length>8000)throw Error('invalid_request');props.setProperty('YOD_PRES_SESSION_'+id,data);},
 validateLinks:function(links,actor,token){var s=yodPresCRM_(token),opps=s.opportunities;return links.opportunityIds.every(function(id){return opps.some(function(o){return o.id===id;});})&&links.pppIds.every(function(id){return opps.some(function(o){return o.ppp_id===id;});})&&links.terrainIds.every(function(id){return opps.some(function(o){return o.terrain_id===id;});});}
};}
function yodPresentacionesPost_(body){if(body&&body.proof)return json(yodPresWorkerRequest_(body.proof));var p=body&&body.presentation;if(!p||typeof p!=='object')return json({ok:false,error:'invalid_request',version:YOD_PRES_VERSION_});return json(YODPresentationsDomain.createService(yodPresAdapter_()).handle(p));}
function yodPresentacionesGet_(p){
 var op=p.estado==='1'?'public_session':p.id?'public_release':'public_catalog';
 return json(YODPresentationsDomain.createService(yodPresAdapter_()).handle({op:op,id:p.id,release:p.release}));
}
function yodPresentacionesInstalar(){
 // Administrative initialization only. Creates private files, never business/test rows.
 var props=PropertiesService.getScriptProperties(),lock=LockService.getScriptLock();lock.waitLock(20000);
 try{
  var response=UrlFetchApp.fetch(YOD_PRES_CATALOG_,{muteHttpExceptions:true});if(response.getResponseCode()!==200)throw Error('catalog_unavailable');
  var catalog=YODPresentationsDomain.normalizeCatalog(JSON.parse(response.getContentText()));
  var old=props.getProperty('YOD_PRES_INDEX_V1'),index=old?JSON.parse(old):{schema:1,records:[]};
  var folderId=props.getProperty('YOD_PRES_FOLDER_V1'),folder=folderId?DriveApp.getFolderById(folderId):DriveApp.createFolder('YOD · Presentaciones · Control privado');
  if(folder.getSharingAccess()!==DriveApp.Access.PRIVATE)throw Error('private_folder_required');
  props.setProperty('YOD_PRES_FOLDER_V1',folder.getId());
  var added=0;catalog.presentations.forEach(function(meta){var prior=index.records.filter(function(r){return r.id===meta.id;})[0];if(prior){if(prior.metadata.baseVersion!==meta.baseVersion)throw Error('base_version_migration_required');return;}
   var record=YODPresentationsDomain.createRecord(meta,Date.now()),name='presentation-'+meta.id+'.json';
   var possible=folder.getFilesByName(name),file=possible.hasNext()?possible.next():folder.createFile(name,JSON.stringify(record),MimeType.PLAIN_TEXT);
   var restored=JSON.parse(file.getBlob().getDataAsString('UTF-8'));if(restored.id!==meta.id)throw Error('id_mismatch');index.records.push({id:meta.id,fileId:file.getId(),metadata:meta});added++;
  });
  props.setProperty('YOD_PRES_INDEX_V1',JSON.stringify(index));
  console.log(JSON.stringify({ok:true,version:YOD_PRES_VERSION_,presentations:index.records.length,added:added,private:true,source:'GitHub catalog approved'}));
 }finally{lock.releaseLock();}
}
