const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),crypto=require('node:crypto');
const source=fs.readFileSync('gas/VideoRevision.gs','utf8');
const bytes=[0,0,0,20,102,116,121,112,105,115,111,109,0,0,0,0,0,0,0,0];
const md5=crypto.createHash('md5').update(Buffer.from(bytes)).digest('hex');
const pid='pieza-corte-nube-'+md5.slice(0,12),video='https://drive.google.com/file/d/syntheticvideo123/preview';
function setup(role='editor',opts={}){
 let read=0;
 const saved=new Map();
 const ctx={rolDe:()=>role,json:x=>x,filas:()=>opts.rows||[{prop_id:pid,video,estado:'en revisión'}],
  PropertiesService:{getScriptProperties:()=>({getProperty:k=>saved.get(k)||null,setProperty:(k,v)=>saved.set(k,v)})},LockService:{getScriptLock:()=>({tryLock:()=>true,releaseLock:()=>{}})},
  DriveApp:{getFileById:()=>{read++;return {isTrashed:()=>false,getMimeType:()=>opts.mime||'video/mp4',getSize:()=>opts.size||bytes.length,getBlob:()=>({getBytes:()=>bytes})};}},
  Utilities:{DigestAlgorithm:{MD5:'md5',SHA_256:'sha256'},computeDigest:(alg,b)=>Array.from(crypto.createHash(alg).update(Buffer.from(b)).digest()),base64Encode:b=>Buffer.from(b).toString('base64')}};
 vm.runInNewContext(source,ctx);return {call:d=>ctx.videoRevision_({clave:'synthetic',prop_id:pid,video,...d}),reads:()=>read,context:ctx,saved};
}
test('only editors can obtain private bytes; rejection happens before Drive',()=>{
 for(const role of [null,'lector','agente']){const s=setup(role);assert.equal(s.call().error,'video_sin_acceso');assert.equal(s.reads(),0);}
 for(const role of ['editor','editor2']){const s=setup(role);assert.equal(s.call().ok,true);assert.equal(s.reads(),1);}
});
test('arbitrary files, missing or retired proposals and changed versions are rejected',()=>{
 for(const opts of [{rows:[]},{rows:[{prop_id:pid,video:'https://drive.google.com/file/d/othervideo123/preview'}]},{rows:[{prop_id:pid,video,estado:'retirada'}]}]){const s=setup('editor',opts);assert.equal(s.call().ok,false);assert.equal(s.reads(),0);}
 const s=setup();assert.equal(s.call({video:'https://example.org/private.mp4'}).ok,false);assert.equal(s.reads(),0);
 const changed=setup('editor',{rows:[{prop_id:'pieza-corte-nube-000000000000',video}]});assert.equal(changed.call({prop_id:'pieza-corte-nube-000000000000'}).error,'video_version_distinta');
});
test('bounded MP4 payload preserves its hash, identity and exact byte count',()=>{
 for(const opts of [{mime:'text/html'},{size:13*1024*1024},{size:bytes.length+1}])assert.equal(setup('editor',opts).call().ok,false);
 const j=setup().call();assert.equal(j.bytes,bytes.length);assert.equal(j.prop_id,pid);assert.equal(j.file_id,'syntheticvideo123');assert.equal(j.sha256,crypto.createHash('sha256').update(Buffer.from(bytes)).digest('hex'));
});
test('read handler precedes day-cache invalidation and never writes business records',()=>{
 const code=fs.readFileSync('gas/Code.gs','utf8'),post=code.slice(code.indexOf('function doPost(e)'));
 assert.ok(post.indexOf('video_revision(?:_preparar)?')<post.indexOf('invalidarDia_('));
 assert.doesNotMatch(source,/appendRow|setValue|setSharing|setTrashed|bitacora\(/);
});
test('encrypted lightweight copy keeps its key in private backend and is idempotent',()=>{
 const s=setup('agente'),copia={source_md5:md5,bytes:bytes.length,sha256:'a'.repeat(64),cipher_bytes:bytes.length+16,cipher_sha256:'b'.repeat(64),key:Buffer.alloc(32,1).toString('base64'),iv:Buffer.alloc(12,2).toString('base64'),url:'https://raw.githubusercontent.com/yodesarrollomx/sala-edicion/'+'c'.repeat(40)+'/video-revision-cifrado/'+'b'.repeat(64)+'.bin'};
 assert.equal(s.call({accion:'video_revision_preparar',op:'estado'}).preparado,false);
 const bad={...copia,url:'https://example.org/asset.bin'};assert.equal(s.call({accion:'video_revision_preparar',copia:bad}).ok,false);assert.equal(s.saved.size,0);
 const ack=s.call({accion:'video_revision_preparar',copia});assert.equal(ack.preparado,true);assert.equal(ack.key,undefined);
 assert.equal(s.call({accion:'video_revision_preparar',copia}).existente,true);assert.equal(s.reads(),0);
 s.context.rolDe=()=> 'editor';const j=s.call();assert.equal(j.cifrado.key,copia.key);assert.equal(j.base64,undefined);assert.equal(s.reads(),0);
 s.context.rolDe=()=> 'lector';assert.equal(s.call().ok,false);
});
