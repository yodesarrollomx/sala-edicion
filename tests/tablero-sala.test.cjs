const test=require("node:test"),assert=require("node:assert/strict");
const board=require("../tablero-sala.js");
const fs=require("node:fs"),vm=require("node:vm");
test("el rechazo de cualquiera manda sobre un sí y sobre el estado histórico",()=>{
 assert.equal(board.estado({estado:"aprobada",src:"a.jpg"},["si","no"]),"rojo");
 assert.equal(board.estado({src:"a.jpg"},["si"]),"verde");
 assert.equal(board.estado({src:"a.jpg"},[]),"amarillo");
 assert.equal(board.estado({},[]),"produccion");
});
test("el tablero abre todas las tomas y sólo el clic explícito elige la opción visible",()=>{
 const source=fs.readFileSync(require.resolve("../tablero-sala.js"),"utf8");
 const start=source.indexOf("function ampliarOpciones(){"),end=source.indexOf("function vote(",start);
 assert.ok(start>=0&&end>start);
 let canWrite=true,opened,votes=[];
 const opts=[{src:"a.jpg",original:"a.png",indiceOriginal:1},{src:"b.jpg",original:"b.png",indiceOriginal:2}];
 const S={choice:{group:"synthetic",n:2,k:0},groups:[{id:"synthetic",pid:"synthetic",t:{laminas:[{n:2,estado:"rehecha"}]}}]};
 const ctx={S,dec:{synthetic:{}},options:()=>opts,markData:()=>({i:0}),eligible:()=>canWrite,fotoKey:board.fotoKey,
  abrirZoom:(src,opc)=>opened={src,...opc},vote:(mark,photo)=>votes.push({mark,photo,k:S.choice.k})};
 vm.runInNewContext(source.slice(start,end)+"\nthis.open=ampliarOpciones;",ctx);
 ctx.open();assert.equal(opened.src,"a.png");assert.equal(opened.galeria.length,2);assert.equal(votes.length,0);
 const photo={complete:true,naturalWidth:1080};opened.galeria[1].elegir(photo);
 assert.equal(votes.length,1);assert.equal(votes[0].mark,"si");assert.equal(votes[0].k,1);assert.equal(votes[0].photo,photo);
 canWrite=false;opened.galeria[0].elegir(photo);assert.equal(votes.length,1);
 ctx.open();assert.ok(opened.galeria.every(x=>typeof x.elegir!=="function"));
 canWrite=true;ctx.open();S.choice={group:"other",n:2,k:0};opened.galeria[0].elegir(photo);assert.equal(votes.length,1);
 assert.match(source,/\[data-full-photo\].*addEventListener\("click",ampliarOpciones\)/);
});
test("conteo conserva intentos y no duplica original PNG, miniatura JPG y candidata",()=>{
 const l={version:7,src:"laminas/v7/L2.jpg",versiones:Array.from({length:7},(_,i)=>({src:"laminas/v"+(i+1)+"/L2.png"})),candidatas:[{src:"laminas/v7/L2.jpg",original:"laminas/v7/L2.png"}]};
 assert.equal(board.intentos(l),7);
 assert.equal(board.intentos({src:"a.jpg",candidatas:[{src:"a.jpg",original:"a.png"},{src:"b.jpg",original:"b.png"}]}),2);
});
