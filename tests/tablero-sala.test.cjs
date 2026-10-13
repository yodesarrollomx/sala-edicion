const test=require("node:test"),assert=require("node:assert/strict");
const board=require("../tablero-sala.js");
test("el rechazo de cualquiera manda sobre un sí y sobre el estado histórico",()=>{
 assert.equal(board.estado({estado:"aprobada",src:"a.jpg"},["si","no"]),"rojo");
 assert.equal(board.estado({src:"a.jpg"},["si"]),"verde");
 assert.equal(board.estado({src:"a.jpg"},[]),"amarillo");
 assert.equal(board.estado({},[]),"produccion");
});
test("conteo conserva intentos y no duplica original PNG, miniatura JPG y candidata",()=>{
 const l={version:7,src:"laminas/v7/L2.jpg",versiones:Array.from({length:7},(_,i)=>({src:"laminas/v"+(i+1)+"/L2.png"})),candidatas:[{src:"laminas/v7/L2.jpg",original:"laminas/v7/L2.png"}]};
 assert.equal(board.intentos(l),7);
 assert.equal(board.intentos({src:"a.jpg",candidatas:[{src:"a.jpg",original:"a.png"},{src:"b.jpg",original:"b.png"}]}),2);
});
