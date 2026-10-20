/** Presentation hub adapter. Uses the EXISTING Sala deployment and Portero. */
var YOD_PRES_VERSION_='PMD-1.0.0';
var YOD_PRES_CATALOG_='https://yodesarrollomx.github.io/yodesarrollo-board/presentacion/catalogo.json';
var YOD_PRES_CRM_='https://script.google.com/macros/s/AKfycby5Nhozhfx6tTLw6f4w14U3fAx4y-bF2cO4aeIApaOQxgXsvonk8ZbTw2VEUnWGTLe8lw/exec';
var YOD_PRES_OWNER_='c27e8a6088a74a82ad2c14ef7ed0d2b4b69d80c4c7bb841c95822980a28c9bad';
function yodPresDigest_(value){return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,String(value),Utilities.Charset.UTF_8).map(function(x){return ('0'+((x+256)%256).toString(16)).slice(-2);}).join('');}
function yodPresUUID_(){return Utilities.getUuid().replace(/-/g,'');}
function yodPresIndex_(){var value=PropertiesService.getScriptProperties().getProperty('YOD_PRES_INDEX_V1');if(!value)throw Error('backend_not_ready');var d=JSON.parse(value);if(d.schema!==1||!Array.isArray(d.records))throw Error('backend_not_ready');return d;}
function yodPresRead_(id){var row=yodPresIndex_().records.filter(function(x){return x.id===id;})[0];if(!row)throw Error('not_found');return JSON.parse(DriveApp.getFileById(row.fileId).getBlob().getDataAsString('UTF-8'));}
function yodPresWrite_(record){var row=yodPresIndex_().records.filter(function(x){return x.id===record.id;})[0];if(!row)throw Error('not_found');DriveApp.getFileById(row.fileId).setContent(JSON.stringify(record));}
function yodPresCRM_(token){
 var res=UrlFetchApp.fetch(YOD_PRES_CRM_,{method:'post',contentType:'text/plain',payload:JSON.stringify({action:'brokers_snapshot',k:token}),muteHttpExceptions:true,followRedirects:true});
 if(res.getResponseCode()!==200)throw Error('service_unavailable');var d=JSON.parse(res.getContentText());if(d.ok!==true||!Array.isArray(d.data&&d.data.opportunities))throw Error('unauthorized');return d.data;
}
function yodPresActor_(token){
 // Fresh server verification, with expiry and revocation. Never trust a browser role.
 if(typeof token!=='string'||token.length<20||token.length>500)return null;
 var v=validarEnHojaDelPortero_(token);if(!v||v.ok!==true||!v.correo)return null;
 var email=String(v.correo).trim().toLowerCase(),owner=yodPresDigest_(email)===YOD_PRES_OWNER_&&String(v.rol).toLowerCase()==='admin';
 var actor={ok:true,id:yodPresDigest_(email),name:String(v.nombre||'YOD'),owner:owner,opportunityIds:[]};
 if(!owner){try{actor.opportunityIds=yodPresCRM_(token).opportunities.map(function(o){return o.id;});}catch(e){return null;}}
 return actor;
}
function yodPresPinRows_(meta){
 var urls=[meta.url].concat(meta.aliases||[]).map(function(u){return u.replace(/[?#].*$/,'').replace(/\/$/,'');});
 return filas('PRODUCCION').map(function(row){try{var d=typeof row.detalle==='string'?JSON.parse(row.detalle):row.detalle;if(!d||!/^CHN-\d{8}-\d{4}-[a-f0-9]{4}$/.test(d.id||''))return null;var revision=d.objeto&&d.objeto.revision,source=String(revision?revision.source:d.url||'').replace(/[?#].*$/,'').replace(/\/$/,'');if(urls.indexOf(source)<0)return null;if(revision&&d.kind==='yod-presentation-private-v1')return {row:row,detail:d,revision:revision,kind:'legacy'};if(d.kind==='chinche-secuencia-v1')return {row:row,detail:d,kind:'sequence'};return null;}catch(e){return null;}}).filter(function(x){return x!==null;});
}
function yodPresPins_(meta,cursor){var list=yodPresPinRows_(meta),seen={},all=[];list.reverse().forEach(function(x){if(!seen[x.detail.id]){seen[x.detail.id]=true;all.push(x);}});var start=Number(cursor||0);if(!isFinite(start)||start<0||Math.floor(start)!==start)throw Error('invalid_request');var slice=all.slice(start,start+100);return {items:slice.map(function(x){return {id:x.detail.id,hash:x.kind==='legacy'?x.detail.objeto.huella:x.detail.hash,kind:x.kind,comment:x.revision?String(x.revision.comment||''):'Explicación con voz, trazos y capturas',title:x.revision?String((x.revision.context||{}).titulo||meta.title):meta.title,version:x.revision?String((x.revision.context||{}).version||''):null,created:String(x.revision?x.revision.created||'':x.row.fecha||''),hasCapture:!!(x.revision&&x.revision.capture),hasSequence:x.kind==='sequence',state:'received'};}),nextCursor:start+slice.length<all.length?String(start+slice.length):null,complete:start+slice.length>=all.length,total:all.length};}
function yodPresPin_(meta,id){var rows=yodPresPinRows_(meta).filter(function(x){return x.detail.id===id;});if(!rows.length)throw Error('not_found');var x=rows[rows.length-1];if(rows.some(function(r){return (r.kind==='legacy'?r.detail.objeto.huella:r.detail.hash)!==(x.kind==='legacy'?x.detail.objeto.huella:x.detail.hash);}))throw Error('integrity');if(x.kind==='legacy'){if(yodPresDigest_(JSON.stringify(x.revision))!==x.detail.objeto.huella)throw Error('integrity');return {kind:'legacy',revision:x.revision,hash:x.detail.objeto.huella};}var canonical=chsRow_(id);if(!canonical||canonical.hash!==x.detail.hash)throw Error('integrity');var f=chsFile_(id);if(!f)throw Error('not_found');var data=f.getBlob().getDataAsString('UTF-8');if(yodPresDigest_(data)!==x.detail.hash)throw Error('integrity');var packet=JSON.parse(data);return {kind:'sequence',packet:packet,hash:x.detail.hash};}
function yodPresAdapter_(){var props=PropertiesService.getScriptProperties();return {
 now:function(){return Date.now();},uuid:yodPresUUID_,hash:yodPresDigest_,auth:yodPresActor_,pins:yodPresPins_,pin:yodPresPin_,
 catalog:function(){return yodPresIndex_().records.map(function(x){return x.metadata;});},read:yodPresRead_,write:yodPresWrite_,
 lock:function(fn){var l=LockService.getScriptLock();if(!l.tryLock(5000))throw Error('busy');try{return fn();}finally{l.releaseLock();}},
 session:function(id){var s=props.getProperty('YOD_PRES_SESSION_'+id);return s?JSON.parse(s):null;},
 writeSession:function(id,s){var data=JSON.stringify(s);if(Utilities.newBlob(data).getBytes().length>8000)throw Error('invalid_request');props.setProperty('YOD_PRES_SESSION_'+id,data);},
 validateLinks:function(links,actor,token){var s=yodPresCRM_(token),opps=s.opportunities;return links.opportunityIds.every(function(id){return opps.some(function(o){return o.id===id;});})&&links.pppIds.every(function(id){return opps.some(function(o){return o.ppp_id===id;});})&&links.terrainIds.every(function(id){return opps.some(function(o){return o.terrain_id===id;});});}
};}
function yodPresentacionesPost_(body){var p=body&&body.presentation;if(!p||typeof p!=='object')return json({ok:false,error:'invalid_request',version:YOD_PRES_VERSION_});return json(YODPresentationsDomain.createService(yodPresAdapter_()).handle(p));}
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
