/* Lectura privada del corte de una propuesta. No escribe ni invalida la mesa. */
function videoRevision_(d) {
  var rol = rolDe(d && d.clave);
  var preparar = d && d.accion === 'video_revision_preparar';
  if (preparar ? rol !== 'agente' : ['editor', 'editor2'].indexOf(rol) < 0) return json({ok:false, error:'video_sin_acceso'});
  var pid = String(d.prop_id || ''), src = String(d.video || '');
  if (!/^[a-zA-Z0-9_-]{1,240}$/.test(pid)) return json({ok:false, error:'video_propuesta_invalida'});
  var match = /^https:\/\/drive\.google\.com\/file\/d\/([A-Za-z0-9_-]{10,128})\/preview$/.exec(src);
  if (!match) return json({ok:false, error:'video_referencia_invalida'});
  // La credencial sólo da acceso a medios que la propia Sala presentó a los editores.
  var rows = filas('PROPUESTAS').filter(function(p) { return String(p.prop_id) === pid; });
  if (!rows.length || rows.some(function(p) { return String(p.video || '') !== src; }) ||
      rows.every(function(p) { return /^(retirada|retirado|obsoleta|obsoleto)$/i.test(String(p.estado || '')); }))
    return json({ok:false, error:'video_fuera_de_propuesta'});
  var props = PropertiesService.getScriptProperties(), cacheKey = 'sala_video_v1_' + pid;
  var guardado = props.getProperty(cacheKey), copia = null;
  try { if (guardado) copia = JSON.parse(guardado); } catch(e) { return json({ok:false,error:'video_copia_invalida'}); }
  if (preparar) {
    if (d.op === 'estado') return json({ok:true,preparado:!!copia});
    var nueva = d.copia, hashOrigen = /-corte-nube-([a-f0-9]{12})$/.exec(pid);
    if (!nueva || !hashOrigen || !/^[a-f0-9]{32}$/.test(String(nueva.source_md5||'')) || nueva.source_md5.slice(0,12)!==hashOrigen[1] ||
        !/^[a-f0-9]{64}$/.test(String(nueva.sha256||'')) || !/^[a-f0-9]{64}$/.test(String(nueva.cipher_sha256||'')) ||
        !Number.isInteger(nueva.bytes) || nueva.bytes<12 || nueva.bytes>4*1024*1024 || nueva.cipher_bytes!==nueva.bytes+16 ||
        !/^[A-Za-z0-9+/]{43}=$/.test(String(nueva.key||'')) || !/^[A-Za-z0-9+/]{16}$/.test(String(nueva.iv||'')) ||
        !(new RegExp('^https://raw\\.githubusercontent\\.com/yodesarrollomx/sala-edicion/[a-f0-9]{40}/video-revision-cifrado/'+nueva.cipher_sha256+'\\.bin$')).test(String(nueva.url||'')))
      return json({ok:false,error:'video_copia_invalida'});
    var lock = LockService.getScriptLock();
    if (!lock.tryLock(5000)) return json({ok:false,error:'video_copia_ocupada'});
    try {
      var actual = props.getProperty(cacheKey);
      if (actual) return json({ok:true,preparado:true,existente:true});
      props.setProperty(cacheKey, JSON.stringify({prop_id:pid,video:src,copia:nueva}));
      if (props.getProperty(cacheKey)!==JSON.stringify({prop_id:pid,video:src,copia:nueva}))return json({ok:false,error:'video_copia_sin_acuse'});
      return json({ok:true,preparado:true});
    } finally { lock.releaseLock(); }
  }
  if (copia) {
    if(copia.prop_id!==pid || copia.video!==src)return json({ok:false,error:'video_copia_invalida'});
    var c=copia.copia;
    return json({ok:true,version:'video-privado-v1',prop_id:pid,file_id:match[1],mime:'video/mp4',bytes:c.bytes,sha256:c.sha256,
      cifrado:{url:c.url,sha256:c.cipher_sha256,bytes:c.cipher_bytes,key:c.key,iv:c.iv}});
  }
  try {
    var file = DriveApp.getFileById(match[1]), max = 12 * 1024 * 1024;
    if (file.isTrashed() || file.getMimeType() !== 'video/mp4') return json({ok:false, error:'video_formato_invalido'});
    if (file.getSize() <= 0 || file.getSize() > max) return json({ok:false, error:'video_requiere_copia_ligera'});
    var bytes = file.getBlob().getBytes();
    if (bytes.length !== file.getSize() || bytes.length > max) return json({ok:false, error:'video_incompleto'});
    function hex(a) { return a.map(function(n) { return ('0' + ((n + 256) % 256).toString(16)).slice(-2); }).join(''); }
    var huella = /-corte-nube-([a-f0-9]{12})$/.exec(pid);
    if (huella && hex(Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, bytes)).slice(0,12) !== huella[1])
      return json({ok:false, error:'video_version_distinta'});
    return json({ok:true, version:'video-privado-v1', prop_id:pid, file_id:match[1], mime:'video/mp4',
      bytes:bytes.length, sha256:hex(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, bytes)),
      base64:Utilities.base64Encode(bytes)});
  } catch (err) { return json({ok:false, error:'video_no_disponible'}); }
}

// Diagnóstico manual del propietario: sólo lecturas, sin bytes privados en el registro.
function comprobarVideoRevision() {
  var seen = {}, rows = filas('PROPUESTAS').filter(function(p) {
    var src = String(p.video || ''), m = /^https:\/\/drive\.google\.com\/file\/d\/([A-Za-z0-9_-]{10,128})\/preview$/.exec(src);
    if (!m || seen[m[1]] || /^(retirada|retirado|obsoleta|obsoleto)$/i.test(String(p.estado || ''))) return false;
    seen[m[1]] = true; return true;
  }).slice(-5);
  var result = rows.map(function(p) {
    var t = Date.now();
    try { var f = DriveApp.getFileById(String(p.video).split('/')[5]), b = f.getBlob().getBytes();
      return {ok:!f.isTrashed() && f.getMimeType()==='video/mp4' && b.length===f.getSize(), bytes:b.length, ms:Date.now()-t};
    } catch(e) { return {ok:false, error:'video_no_disponible', ms:Date.now()-t}; }
  });
  console.log(JSON.stringify({version:'video-privado-v1', cortes:result}));
}
