/* Private recorded annotations. Install alongside Code.gs; never share the folder. */
var CHS_CONTRACT_ = 'chinche-secuencia-v1';
function chsHash_(s) {return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,s,Utilities.Charset.UTF_8).map(function(b){return ('0'+(b&255).toString(16)).slice(-2);}).join('');}
function chsId_(id){return /^CHN-\d{8}-\d{4}-[a-f0-9]{4}$/.test(String(id||''));}
function chsFolder_(){
 var id=PropertiesService.getScriptProperties().getProperty('CHINCHE_SECUENCIA_FOLDER');
 if(!id)throw new Error('storage_not_configured');
 return DriveApp.getFolderById(id);
}
/* Explicit owner setup in Apps Script. No new sharing, no automatic permission changes. */
function configurarChincheSecuencia(){
 var props=PropertiesService.getScriptProperties();if(props.getProperty('CHINCHE_SECUENCIA_FOLDER'))return;
 var f=DriveApp.createFolder('YOD · Chinches · secuencias privadas');props.setProperty('CHINCHE_SECUENCIA_FOLDER',f.getId());
}
function chsRow_(id){
 var rows=filas('PRODUCCION'),found=null;
 rows.forEach(function(r){var d;try{d=JSON.parse(r.detalle);}catch(_){return;}
  if(d&&d.id===id&&d.kind===CHS_CONTRACT_){if(found&&found.hash!==d.hash)throw new Error('conflict');found=d;}});return found;
}
function chsFile_(id){var it=chsFolder_().getFilesByName(id+'.json'),f=null;while(it.hasNext()){if(f)throw new Error('duplicate_file');f=it.next();}return f;}
function chsValidate_(d){
 if(!chsId_(d.id)||!/^[a-f0-9]{64}$/.test(d.hash)||typeof d.data!=='string'||d.data.length>12500000||chsHash_(d.data)!==d.hash)throw new Error('invalid_package');
 var p=JSON.parse(d.data),s=p.secuencia;
 if(p.v!==1||p.id!==d.id||typeof p.texto!=='string'||p.texto.length>12000||!s||s.v!==1||!isFinite(s.duration)||s.duration<0||s.duration>610000||!Array.isArray(s.events)||s.events.length>10000||!Array.isArray(s.frames)||s.frames.length>240||!/^data:image\/jpeg;base64,/.test(s.base)||!Number.isInteger(s.width)||s.width<1||s.width>2560||!Number.isInteger(s.height)||s.height<1||s.height>2560)throw new Error('invalid_sequence');
 if(s.audio&&(!/^audio\/(webm|mp4|ogg)(;codecs=[a-zA-Z0-9., -]+)?$/.test(s.audio.mime)||!/^data:audio\/(webm|mp4|ogg)(;codecs=[a-zA-Z0-9., -]+)?;base64,[A-Za-z0-9+/]+=*$/.test(s.audio.data)||!isFinite(s.audio.offset)||s.audio.offset<0||s.audio.offset>s.duration))throw new Error('invalid_audio');
 var prev=-1,count=0;s.events.forEach(function(e){if(!isFinite(e.t)||e.t<prev||e.t>s.duration||['stroke','undo','audio-start','audio-end'].indexOf(e.type)<0)throw new Error('invalid_clock');prev=e.t;if(e.type==='stroke'){if(['pen','marker','line','arrow','rect','ellipse'].indexOf(e.tool)<0||!/^#[a-f0-9]{6}$/i.test(e.color)||!isFinite(e.width)||e.width<1||e.width>80||!Array.isArray(e.points)||!e.points.length)throw new Error('invalid_stroke');var t=e.t;e.points.forEach(function(p){if(!Array.isArray(p)||p.length!==4||p.some(function(n){return typeof n!=='number'||!isFinite(n);})||p[0]<0||p[0]>s.width||p[1]<0||p[1]>s.height||p[2]<t||p[2]>s.duration||p[3]<0||p[3]>1)throw new Error('invalid_point');t=p[2];});count+=e.points.length;}});
 if(count>120000)throw new Error('too_many_points');prev=-1;s.frames.forEach(function(f){if(!isFinite(f.t)||f.t<prev||f.t>s.duration||!/^data:image\/jpeg;base64,[A-Za-z0-9+/]+=*$/.test(f.image))throw new Error('invalid_frame');prev=f.t;});
 if(!/^https:\/\/(yodesarrollomx\.github\.io|yodesarrollo\.github\.io|gaston-madrid-pintarron\.sayri-fraijo\.chatgpt\.site)\//.test(p.url)||!/^[-a-zA-Z0-9_.]{1,80}$/.test(p.repo))throw new Error('invalid_source');return p;
}
function chincheSecuencia_(d){
 var role=rolDe(d.clave);if(['editor','editor2','agente'].indexOf(role)<0)return json({ok:false,error:'not_authorized'});
 try{
  if(!chsId_(d.id))throw new Error('invalid_id');
  if(d.accion==='chinche_secuencia_recibo'){
   chsFolder_();var row=chsRow_(d.id);if(row){var stored=chsFile_(d.id);if(!stored||chsHash_(stored.getBlob().getDataAsString('UTF-8'))!==row.hash)throw new Error('integrity');}return json({ok:true,contrato:CHS_CONTRACT_,id:d.id,hash:row?row.hash:null});
  }
  if(d.accion==='chinche_secuencia_leer'){
   var r=chsRow_(d.id),file=chsFile_(d.id);if(!r||!file)throw new Error('not_found');var data=file.getBlob().getDataAsString('UTF-8');if(chsHash_(data)!==r.hash)throw new Error('integrity');
   return json({ok:true,contrato:CHS_CONTRACT_,id:d.id,hash:r.hash,data:data});
  }
  if(d.accion!=='chinche_secuencia_guardar')throw new Error('unknown_action');
  if(['editor','editor2'].indexOf(role)<0)throw new Error('read_only');
  var packet=chsValidate_(d),lock=LockService.getScriptLock();if(!lock.tryLock(15000))throw new Error('busy');
  try{
   var previous=chsRow_(d.id);if(previous&&previous.hash!==d.hash)throw new Error('conflict');
   var f=chsFile_(d.id);if(f){if(chsHash_(f.getBlob().getDataAsString('UTF-8'))!==d.hash)throw new Error('conflict');}
   else f=chsFolder_().createFile(Utilities.newBlob(d.data,'application/json',d.id+'.json'));
   if(!previous){
    var detail={kind:CHS_CONTRACT_,id:d.id,hash:d.hash,archivo:f.getId(),repo:packet.repo,pantalla:packet.pantalla||'',url:packet.url,vista:packet.repo+'/'+(packet.pantalla||''),texto:'Explicación con secuencia privada. Recuperar paquete autenticado por ID y comprobar SHA256 antes de revisar.',secuencia:{v:1,duracion:packet.secuencia.duration,audio:!!packet.secuencia.audio,fotogramas:packet.secuencia.frames.length},quien:nombreDe(role)||role};
    hoja('PRODUCCION').appendRow([hoy(),'ENCARGO · chinche · '+packet.repo,'pendiente',JSON.stringify(detail),packet.url]);
    SpreadsheetApp.flush();invalidarDia_(hoy());
   }
   var verified=chsRow_(d.id);if(!verified||verified.hash!==d.hash)throw new Error('receipt_missing');
   return json({ok:true,contrato:CHS_CONTRACT_,id:d.id,hash:d.hash});
  }finally{lock.releaseLock();}
 }catch(e){var allowed=['storage_not_configured','conflict','invalid_id','invalid_package','invalid_sequence','invalid_audio','invalid_clock','invalid_stroke','invalid_point','invalid_frame','invalid_source','too_many_points','read_only','busy','not_found','integrity','receipt_missing','duplicate_file'];return json({ok:false,contrato:CHS_CONTRACT_,error:allowed.indexOf(e.message)>=0?e.message:'storage_error'});}
}
