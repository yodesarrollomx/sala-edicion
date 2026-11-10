/* Salida de la Sala corta: la parte sin pantalla de sala-salida.js. */
const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');
const s=require('../sala-salida.js');
const paquete=(orden,n=2)=>({orden,sello:'a'.repeat(12),imagenes:Array.from({length:n},(_,i)=>({n:i+1,src:`laminas/x/L${i+1}.png`}))});

test('sólo cuenta como lista la pieza con paquete que no ha salido, en el orden de sus carpetas',()=>{
  const exp={'Tres':{paquete:paquete(3)},'Uno':{paquete:paquete(1)},'Sin paquete':{estado:'en camino'},'Ya salió':{paquete:paquete(2)},'Vacío':{paquete:{imagenes:[]}}};
  assert.deepEqual(s.listas(exp,n=>n==='Ya salió').map(x=>x.nombre),['Uno','Tres']);
  assert.deepEqual(s.listas({},()=>false),[]);
  assert.equal(s.paquete(null),null);assert.equal(s.paquete({paquete:'x'}),null);
});

test('el texto común se separa de lo que cada red agrega',()=>{
  const c={texto:'Hola.\nAdiós.',instagram:'Hola.\nAdiós.\n(la liga te espera en el primer comentario)',facebook:'Hola.\nAdiós.\nhttps://x.test/?a=1',comentario:'https://x.test/?b=2',revision:['Ojo con la 3','',5]};
  assert.deepEqual(s.partes(c),{texto:'Hola.\nAdiós.',ig:'\n(la liga te espera en el primer comentario)',fb:'\nhttps://x.test/?a=1',comentario:'https://x.test/?b=2',revision:['Ojo con la 3']});
  assert.deepEqual(s.partes({texto:'A',instagram:'otra cosa'}),{texto:'A',ig:'',fb:'',comentario:'',revision:[]});
  assert.deepEqual(s.partes(undefined),{texto:'',ig:'',fb:'',comentario:'',revision:[]});
});

test('la liga de la publicación es opcional, pero si viene es una dirección https completa',()=>{
  for(const ok of ['','  ','https://www.instagram.com/p/ABC123/','https://www.facebook.com/1/posts/2'])assert.equal(s.ligaValida(ok),true,ok);
  for(const mal of ['instagram.com/p/x','http://x.test/p','javascript:alert(1)','https://x.test/a b','https://x.test/"><script>','https://'])assert.equal(s.ligaValida(mal),false,mal);
});

test('el estado de una pieza en la línea',()=>{
  const carrusel=['guion','laminas','copy','publicada'],reel=['guion','laminas','voz','escenas','corte','copy','publicada'];
  const exp={'Con paquete':{paquete:paquete(1)}};
  assert.equal(s.estado('X',new Set(),carrusel,exp,false),'guion');
  assert.equal(s.estado('X',new Set(['guion']),carrusel,exp,false),'laminas');
  assert.equal(s.estado('X',new Set(['guion','laminas']),carrusel,exp,false),'texto');
  assert.equal(s.estado('X',new Set(['guion','laminas']),reel,exp,false),'video');
  assert.equal(s.estado('Con paquete',new Set(['guion','laminas']),carrusel,exp,false),'lista');
  assert.equal(s.estado('Con paquete',new Set(['guion']),carrusel,exp,false),'laminas','sin imágenes aprobadas un paquete viejo no la vuelve lista');
  assert.equal(s.estado('Con paquete',new Set(),carrusel,exp,true),'publicada');
});

test('la Sala nunca publica ni decide desde esta pantalla',()=>{
  const fuente=fs.readFileSync(require.resolve('../sala-salida.js'),'utf8');
  assert.equal((fuente.match(/accion:'([a-z_]+)'/g)||[]).join(),"accion:'produccion'");
  assert.ok(!/graph\.facebook|instagram\.com\/api|accion:'decidir'/.test(fuente));
  assert.ok(fuente.includes("correcciones().enviar("),'la anotación viaja por el transporte que no repite envíos');
});

test('el índice carga la salida y la mesa sólo se pinta en «Te toca»',()=>{
  const html=fs.readFileSync(require.resolve('../index.html'),'utf8'),css=fs.readFileSync(require.resolve('../tablero-sala.css'),'utf8');
  assert.ok(/<script src="sala-salida\.js\?v=[^"]+"><\/script>/.test(html));assert.ok(/href="sala-salida\.css\?v=[^"]+"/.test(html));
  assert.ok(html.indexOf('id="salidaHoy"')<html.indexOf('id="tableroHoy"'));
  assert.ok(css.includes('body.sala-tablero[data-vista="hoy"] #vHoy{display:block'));
  assert.ok(!/body\.sala-tablero #vHoy\{display:block/.test(css),'sin [data-vista] la mesa tapa «Cómo va» y Ajustes');
});
