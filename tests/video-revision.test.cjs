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
const fs=require('node:fs'),vm=require('node:vm');
test('background rendering leaves an open cut review untouched',()=>{
 const source=fs.readFileSync('tablero-sala.js','utf8');
 const start=source.indexOf('function render(){'),end=source.indexOf('\nfunction ',start+1);
 assert.ok(start>=0&&end>start);
 let changed=false;
 const ctx={document:{body:{classList:{contains:c=>c==='sala-turno',add:()=>{changed=true;}}}}};
 vm.runInNewContext(source.slice(start,end)+'\nrender();',ctx);
 assert.equal(changed,false);
});
test('normalizing review choices keeps the question and visual reference',()=>{
 const source=fs.readFileSync('index.html','utf8');
 const start=source.indexOf('function normalizarDia('),end=source.indexOf('\nfunction ',start+1);
 const ctx={localStorage:{getItem:()=>null},CANDIDATAS:p=>Array.isArray(p.opciones)?p.opciones:p.opciones.candidatas};
 vm.runInNewContext(source.slice(start,end)+'\nthis.normalize=normalizarDia;',ctx);
 const prop={id:'sintetica',tipo:'eje',laminas:[],opciones:{porque:'Revisa imagen y voz',referencia:'referencia.png',candidatas:[{titulo:'Conservar'}]}};
 const result=ctx.normalize({fecha:'2026-10-17',propuestas:[prop],decisiones:{propuestas:{}}});
 assert.equal(result.propuestas[0].porque,'Revisa imagen y voz');assert.equal(result.propuestas[0].referencia,'referencia.png');
});
