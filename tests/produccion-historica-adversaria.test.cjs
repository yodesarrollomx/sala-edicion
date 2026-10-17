/* Contrato editorial: sólo datos sintéticos, sin servicios ni escrituras. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
for (const name of ['node:http','node:https']) {
  const transport=require(name);
  transport.request=transport.get=()=>{throw Error('red prohibida en fixtures sintéticas');};
}
global.fetch=()=>{throw Error('red prohibida en fixtures sintéticas');};

function backend() {
  const ctx = vm.createContext({});
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../gas/Code.gs'), 'utf8'), ctx);
  ctx.leerConfig = key => ({nombre_editor:'Editor A', nombre_editor2:'Editor B'}[key] || '');
  ctx.hoy = () => '2026-10-15';
  return ctx;
}
const plain = value => JSON.parse(JSON.stringify(value));
const stamp = hour => `2026-09-02T${hour}:00:00Z`;
function decision(mark, extra={}) {
  return {envio_id:'sobre-sintetico', quien:'editor', guardado:stamp('10'),
    fecha:'2026-09-02', prop_id:'fuente-sintetica', lamina:0, marca:mark,
    nota_propuesta:'', nota_dia:'', nota_estrategia:'', ...extra};
}
function proposal(extra={}) {
  return {fecha:'2026-09-01', prop_id:'fuente-sintetica', titulo:'Pieza sintética',
    tipo:'laminas', laminas_json:'["laminas/sintetica/L1.jpg"]', opciones_json:'[]',
    video:'', estado:'', origen:'', ...extra};
}
function permutations(rows) {
  if (rows.length < 2) return [rows];
  return rows.flatMap((value, i) => permutations(rows.filter((_, j) => i !== j)).map(tail => [value, ...tail]));
}

test('el sello de otra fila del mismo envío no promueve un sí viejo sobre un no reciente', () => {
  const ctx=backend(), rows=[decision('si'), decision('no', {envio_id:'otro-sobre', guardado:stamp('12')}),
    decision('si', {prop_id:'otra-fuente', guardado:stamp('14')})];
  for (const order of permutations(rows)) {
    const merged=plain(ctx.fusionProduccion_(order));
    assert.equal(merged.propuestas['fuente-sintetica'].laminas[0], 'no');
    assert.equal(merged.propuestas['fuente-sintetica'].firmas[0][0].guardado, stamp('12').replace('Z','.000Z'));
  }
});

test('fecha de presentación y orden físico no sustituyen el sello real de cada decisión', () => {
  const ctx=backend(), rows=[decision('si', {fecha:'2026-10-14'}),
    decision('no', {fecha:'2026-09-01', guardado:stamp('12')}),
    decision('pendiente', {fecha:'2026-10-15', guardado:'2026-10-15T12:00:00Z'})];
  for (const order of permutations(rows)) {
    const before=JSON.stringify(order), merged=plain(ctx.fusionProduccion_(order));
    assert.equal(merged.propuestas['fuente-sintetica'].laminas[0], 'no');
    assert.equal(JSON.stringify(order), before);
  }
});

test('borrar de un editor no borra el veto del otro y borrar ambos deja pendiente firmado', () => {
  const ctx=backend(), rows=[decision('si'),
    decision('no', {quien:'editor2', guardado:stamp('11')}),
    decision('borrar', {guardado:stamp('12')})];
  for (const order of permutations(rows)) {
    const card=plain(ctx.fusionProduccion_(order)).propuestas['fuente-sintetica'];
    assert.equal(card.laminas[0], 'no');
    assert.deepEqual(card.firmas[0].map(x=>[x.rol,x.marca]).sort((a,b)=>a[0].localeCompare(b[0])), [['editor',null],['editor2','no']]);
  }
  rows.push(decision('borrar', {quien:'editor2', guardado:stamp('13')}));
  const card=plain(ctx.fusionProduccion_(rows)).propuestas['fuente-sintetica'];
  assert.equal(card.laminas[0], null);
  assert.deepEqual(card.firmas[0].map(x=>x.marca), [null,null]);
});

test('un empate contradictorio de marca o nota cierra lectura, pero un reenvío idéntico no', () => {
  const ctx=backend();
  for (const conflict of [decision('no'), decision('si',{nota_propuesta:'Otra toma'})]) {
    for (const rows of [[decision('si'),conflict],[conflict,decision('si')]])
      assert.throws(()=>ctx.fusionProduccion_(rows), /ambiguo/);
  }
  const card=plain(ctx.fusionProduccion_([decision('si'),decision('si')])).propuestas['fuente-sintetica'];
  assert.equal(card.laminas[0], 'si');
  assert.equal(card.firmas[0].length, 1);
});

test('un conflicto antiguo reemplazado por un sello mayor no contamina la decisión vigente', () => {
  const ctx=backend(), rows=[decision('si'),decision('no'),decision('borrar',{guardado:stamp('12')})];
  for (const order of permutations(rows)) {
    const card=plain(ctx.fusionProduccion_(order)).propuestas['fuente-sintetica'];
    assert.equal(card.laminas[0], null);
    assert.equal(card.firmas[0][0].guardado, stamp('12').replace('Z','.000Z'));
  }
});

test('un sello de calendario imposible no puede normalizarse para sustituir un veto real', () => {
  const ctx=backend(), veto=decision('no',{fecha:'2026-03-01',guardado:'2026-03-01T12:00:00Z'});
  for (const invalid of ['2026-02-30T12:00Z','2026-02-30T12:00:00Z','2026-02-30']) {
    const yes=decision('si',{fecha:'2026-02-28',guardado:invalid});
    for (const rows of [[veto,yes],[yes,veto]])
      assert.throws(()=>ctx.fusionProduccion_(rows));
  }
});

test('una fuente anterior a 14 días sigue activa hasta un retiro genuino posterior', () => {
  const ctx=backend(), old=proposal(), retired=proposal({fecha:'2026-10-01',estado:'retirada-por-direccion'});
  const active=plain(ctx.produccionHistorica_('2026-10-15',[old],[decision('si')]));
  assert.equal(active.propuestas.length,1);
  assert.equal(active.propuestas[0].fecha_fuente,'2026-09-01');
  assert.equal(active.decisiones.propuestas['fuente-sintetica'].laminas[0],'si');
  for (const rows of [[old,retired],[retired,old]]) {
    const before=JSON.stringify(rows), r=plain(ctx.produccionHistorica_('2026-10-15',rows,[decision('si')]));
    assert.equal(r.propuestas.length,0);
    assert.equal(r.fuentes.retiradas,1);
    assert.equal(JSON.stringify(rows),before);
  }
});

test('dos versiones contradictorias con el mismo PID y fecha no se resuelven por orden físico', () => {
  const ctx=backend(), first=proposal(), conflict=proposal({laminas_json:'["laminas/sintetica/OTRA.jpg"]'});
  for (const rows of [[first,conflict],[conflict,first]])
    assert.throws(()=>ctx.produccionHistorica_('2026-10-15',rows,[decision('si')]));
});

test('un conflicto de fuentes antiguas reemplazado por versión única no depende del orden físico', () => {
  const ctx=backend(), rows=[proposal(),proposal({laminas_json:'["laminas/sintetica/OTRA.jpg"]'}),
    proposal({fecha:'2026-09-10',laminas_json:'["laminas/sintetica/VIGENTE.jpg"]'})];
  for (const order of permutations(rows)) {
    const value=plain(ctx.produccionHistorica_('2026-10-15',order,[decision('si')]));
    assert.equal(value.propuestas.length,1);
    assert.equal(value.propuestas[0].fecha_fuente,'2026-09-10');
    assert.deepEqual(value.propuestas[0].laminas,['laminas/sintetica/VIGENTE.jpg']);
  }
});

function endpoint(role, brokenHeader=false) {
  const ctx=backend(), reads=[], writes=[];
  const raw={PROPUESTAS:[proposal()],DECISIONES:[decision('si')]};
  ctx.rolDe=()=>role;
  ctx.json=value=>plain(value);
  ctx.SpreadsheetApp={getActive:()=>({getSheetByName:name=>{
    reads.push(name);
    const headers=Array.from(ctx.PESTANAS[name]);
    if (brokenHeader) headers[0]='cabecera-invalida';
    const values=[headers,...raw[name].map(row=>Array.from(ctx.PESTANAS[name],key=>row[key]??''))];
    return new Proxy({getLastRow:()=>values.length,
      getRange:(row, column, count, width)=>({getValues:()=>values.slice(row-1,row-1+count).map(line=>line.slice(column-1,column-1+width))}),
      getDataRange:()=>({getValues:()=>values})}, {get(target,key){
      if (key in target) return target[key];
      return ()=>{writes.push(String(key));throw Error('prohibida escritura');};
    }});
  }})};
  return {ctx,reads,writes};
}

test('el GET de historial sólo admite agente y no usa escrituras ni servicios externos', () => {
  for (const role of ['editor','editor2','lector',null]) {
    const {ctx,reads,writes}=endpoint(role);
    assert.ok(ctx.doGet({parameter:{recurso:'produccion',clave:'sintetica'}}).error);
    assert.equal(reads.length,0);assert.deepEqual(writes,[]);
  }
  const {ctx,reads,writes}=endpoint('agente');
  const result=ctx.doGet({parameter:{recurso:'produccion',clave:'sintetica',fresco:'1'}});
  assert.equal(result.ok,true);assert.equal(result.alcance,'historial_completo');
  assert.equal(result.propuestas.length,1);assert.ok(reads.length>0);assert.deepEqual(writes,[]);
});

test('cabecera ilegible no se convierte en historial vacío confirmado ni filtra detalles', () => {
  const {ctx,writes}=endpoint('agente',true);
  const result=ctx.doGet({parameter:{recurso:'produccion',clave:'sintetica'}});
  assert.equal(result.ok,false);assert.equal(result.error,'produccion_sin_lectura_confirmada');
  assert.equal('propuestas' in result,false);assert.deepEqual(writes,[]);
  assert.equal(JSON.stringify(result).includes('cabecera-invalida'),false);
});

test('retiro explícito domina copias de la misma fecha, incluso contenido contradictorio', () => {
  const ctx=backend();
  for (const retirement of [{estado:'retirada'}, {origen:'Retirada por dirección'}]) {
    const rows=[proposal(), proposal({titulo:'Otro contenido'}), proposal(retirement)];
    for (const order of permutations(rows)) {
      const before=JSON.stringify(order);
      const value=plain(ctx.produccionHistorica_('2026-10-15',order,[decision('no')]));
      assert.deepEqual(value.propuestas,[]);
      assert.equal(value.fuentes.retiradas,1);
      assert.equal(value.decisiones.propuestas['fuente-sintetica'].laminas[0],'no');
      assert.equal(JSON.stringify(order),before);
    }
  }
});

test('procedencias descriptivas se conservan sin duplicar ni cambiar contenido o firmas', () => {
  const ctx=backend(), rows=[proposal({origen:'rehecha-de base-z'}),
    proposal({origen:'rehecha-de base-a'}),proposal({origen:'rehecha-de base-z'})];
  for (const order of permutations(rows)) {
    const before=JSON.stringify(order);
    const value=plain(ctx.produccionHistorica_('2026-10-15',order,[decision('no')]));
    assert.equal(value.propuestas.length,1);
    assert.equal(value.propuestas[0].origen,'rehecha-de base-a | rehecha-de base-z');
    assert.deepEqual(value.propuestas[0].laminas,['laminas/sintetica/L1.jpg']);
    assert.equal(value.decisiones.propuestas['fuente-sintetica'].laminas[0],'no');
    assert.equal(JSON.stringify(order),before);
  }
});

test('procedencia distinta no oculta diferencias activas de título, tipo, opciones, vídeo o estado', () => {
  const ctx=backend();
  for (const difference of [{titulo:'Otro'}, {tipo:'video'}, {opciones_json:'["otra"]'},
    {video:'otro.mp4'}, {estado:'otro estado'}, {laminas_json:'["otra.jpg"]'}]) {
    for (const rows of permutations([proposal({origen:'base-a'}), proposal({origen:'base-z',...difference})]))
      assert.throws(()=>ctx.produccionHistorica_('2026-10-15',rows,[]),/produccion_fuente_duplicada/);
  }
});

test('retiro de una fecha anterior o futura no sustituye el grupo vigente', () => {
  const ctx=backend(), rows=[proposal({fecha:'2026-08-01',estado:'retirada'}),
    proposal(),proposal({fecha:'2026-11-01',estado:'retirada'})];
  for (const order of permutations(rows)) {
    const value=plain(ctx.produccionHistorica_('2026-10-15',order,[]));
    assert.equal(value.propuestas.length,1);
    assert.equal(value.propuestas[0].fecha_fuente,'2026-09-01');
    assert.equal(value.fuentes.retiradas,0);
  }
});
