const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const test=require('node:test');
function backend() {
  const c=vm.createContext({});
  vm.runInContext(fs.readFileSync('gas/Code.gs','utf8'),c);
  c.validarContenidoEntrada_=()=>'';c.invalidarDia_=()=>{};c.hoy=()=> '2026-10-17';
  c.rolDe=()=> 'agente';c.json=x=>JSON.parse(JSON.stringify(x));
  return c;
}
test('upsert con IDs repetidos se rechaza antes de tocar la hoja, incluso separados por otro ID',()=>{
  for(const ids of [['x','x'],[' x ','y','x']]) {
    const c=backend();let reads=0;
    c.hoja=()=>{reads++;throw Error('no debe tocar Sheets');};
    const r=c.doPost({postData:{contents:JSON.stringify({accion:'cola',op:'upsert',filas:ids.map(id=>({id}))})}});
    assert.equal(r.error,'cola_id_duplicado_en_lote');assert.equal(reads,0);
  }
});
test('lote de identidad única alcanza la validación normal de la hoja',()=>{
  const c=backend();let reads=0;c.hoja=()=>{reads++;return null;};
  const r=c.doPost({postData:{contents:JSON.stringify({accion:'cola',op:'upsert',filas:[{id:'x'},{id:'y'}]})}});
  assert.match(r.error,/no existe la hoja/);assert.equal(reads,1);
});
