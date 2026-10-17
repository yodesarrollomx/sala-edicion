const {test}=require('node:test'),assert=require('node:assert/strict');
const {proyectarPublicacion,estado}=require('../tablero-sala.js');
test('Inventario aplica toma elegida sin mutar archivo ni publicar notas',()=>{
 const source={laminas:[{n:1,src:'vieja.jpg',dice:'viejo',candidatas:[{src:'a.jpg'},{src:'b.jpg',dice:'elegida'}]}]};
 const out=proyectarPublicacion(source,{laminas:[{n:1,estado:'aprobada',toma:2}]});
 assert.equal(out.laminas[0].src,'b.jpg');
 assert.equal(out.laminas[0].dice,'elegida');
 assert.equal(source.laminas[0].src,'vieja.jpg');
 assert.equal(estado(out.laminas[0],['no']),'rojo');
});
test('No acepta proyección incompleta o toma inexistente',()=>{
 const t={laminas:[{n:1,src:'a.jpg'}]};
 assert.throws(()=>proyectarPublicacion(t,{laminas:[]}));
 assert.throws(()=>proyectarPublicacion(t,{laminas:[{n:1,estado:'aprobada',toma:2}]}));
 assert.throws(()=>proyectarPublicacion(t,{laminas:[{n:1,estado:'inventado'}]}));
});
