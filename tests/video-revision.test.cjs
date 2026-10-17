const {test}=require('node:test');const assert=require('node:assert/strict');const v=require('../video-revision.js');
test('authenticated Drive preview preserves identity and opens original view',()=>{
 const src='https://drive.google.com/file/d/abc123def456/preview';
 assert.equal(v.resolver(src).enlace,'https://drive.google.com/file/d/abc123def456/view');
 assert.match(v.html(src),/<iframe/);assert.match(v.html(src),/title="Corte completo para revisar"/);
});
test('arbitrary iframe origins, scripts, attributes and traversal never render',()=>{
 for(const src of ['https://evil.example/preview','javascript:alert(1)','//evil.example/a.mp4','https://drive.google.com.evil/file/d/abc123def456/preview','https://drive.google.com/file/d/abc123def456/preview?x=1','a/../x.mp4','a/%2e%2e/x.mp4','x.mp4" onload="bad','http://example.org/x.mp4'])assert.equal(v.html(src),'');
});
test('existing local and https video files retain video controls',()=>{
 for(const src of ['laminas/apodo.mp4','https://example.org/video.mp4'])assert.match(v.html(src),/<video.*controls/);
});
