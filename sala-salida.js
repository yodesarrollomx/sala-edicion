/* Salida de la Sala corta (9-nov-2026).
   Dirección: «quiero el proceso de creación de inicio a final completo… sólo quiero orden para
   poderlas desatorar». Lo que faltaba al final de la línea: ver qué quedó LISTO PARA PUBLICAR,
   tener a un toque sus imágenes y su texto, y poder decir «ya la publiqué».

   El mismo día, ya con 24 listas: «no voy a publicar aún, quiero hacer montón para nunca quedarnos…
   que vayamos armando un paquete para ir lanzando». Por eso esto ya no es una fila que apura:
   es EL MONTÓN — lo listo, en el orden en que va a salir, con su ritmo y hasta cuándo alcanza.

   De dónde sale cada cosa:
   · el paquete (imágenes en orden + texto) lo arma la nube y lo anota en el expediente de la
     pieza (`nube/sala_salida.py` → EXPEDIENTES); aquí sólo se lee;
   · el PLAN DE SALIDA (orden, cuántas por semana, día de arranque) es de los editores: vive en
     EXPEDIENTES con la llave `salida:plan` y la nube nunca lo escribe;
   · la ORDEN DE CAMBIO («pedir cambio a una imagen ya aprobada») también es de los editores: vive
     en EXPEDIENTES con la llave `cambio:<slug>` y nombra la versión (tira) para la que se pidió.
     La nube sólo la lee: el montador rehace esa imagen con la nota y trae la carta nueva a la mesa.
     Mientras, la pieza sale del montón. La aprobación anterior no se borra;
   · «Ya la publiqué» agrega UNA fila a PRODUCCION con el transporte de siempre
     (`SalaCorrecciones`: se guarda en el aparato antes de mandar y no se repite). La nube cierra
     el expediente en su siguiente sesión; mientras, este aparato ya la da por publicada.
   Publicar es siempre el clic de Dirección: nada de aquí publica por su cuenta. */
(function(root){
'use strict';
const LLAVE='sala_publicadas_v1', BORRADOR='sala_salida_texto_v1', GUARDADA='sala_salida_local_v1', PLAN_LOCAL='sala_salida_plan_v1';
/* lo único que YOD OS lee de aquí (mismo origen): cuántas hay listas y cuándo se vio. Sin títulos ni textos. */
const RESUMEN='sala_resumen_v1';
const PLAN_LLAVE='salida:plan', DIA_MS=864e5, VIGENCIA=7*DIA_MS, TOPE_GUARDADA=1500000;
/* órdenes de cambio: una llave por pieza; la nota es lo que lee Producción (mismo tope que en la nube) */
const CAMBIO_LLAVE='cambio:', NOTA_MAX=600, ID_TIRA=/^[A-Za-z0-9_-][A-Za-z0-9._-]{0,199}$/, SLUG_OK=/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/;
/* qué días de la semana sale algo según cuántas por semana (0 = domingo) */
const DIAS={1:[3],2:[2,4],3:[1,3,5],4:[1,2,4,5],5:[1,2,3,4,5],6:[1,2,3,4,5,6],7:[0,1,2,3,4,5,6]};

/* ── puro (sin pantalla): se prueba en Node ─────────────────────────────────────────────── */
function paquete(e){ return e&&typeof e==='object'&&e.paquete&&typeof e.paquete==='object'&&Array.isArray(e.paquete.imagenes)&&e.paquete.imagenes.length?e.paquete:null }
/* lo que venga de la hoja o del aparato, en una forma en la que se puede confiar */
/* el libro: lo que cada editor dijo de una pieza lista. `m` = 'va' | 'no'; `sello` = el paquete que vio
   (si la nube arma un paquete nuevo, la marca ya no vale y la pieza vuelve al libro) */
function vistoLimpio(v){
  const out={}; if(!v||typeof v!=='object'||Array.isArray(v)) return out;
  for(const [n,x] of Object.entries(v).slice(0,500)){ const k=String(n).trim().slice(0,160);
    if(!k||k==='__proto__'||!x||typeof x!=='object'||(x.m!=='va'&&x.m!=='no')) continue;
    out[k]={m:x.m, sello:typeof x.sello==='string'?x.sello.slice(0,80):'', por:typeof x.por==='string'?x.por.slice(0,40):'', cuando:typeof x.cuando==='string'?x.cuando.slice(0,40):''} }
  return out;
}
function marcaLibro(plan,nombre,sello){ const v=plan&&plan.visto, x=v&&Object.prototype.hasOwnProperty.call(v,nombre)?v[nombre]:null; return x&&x.sello===String(sello||'')?x.m:'' }
/* poner o quitar (m='') la marca de una pieza sin tocar las demás */
function conMarca(visto,nombre,m,sello,quien,ahora){
  const out=vistoLimpio(visto); delete out[nombre];
  if(m==='va'||m==='no') out[nombre]={m, sello:String(sello||'').slice(0,80), por:String(quien||'').slice(0,40), cuando:String(ahora||'').slice(0,40)};
  return out;
}
/* del montón: cuáles faltan por decidir, cuáles van y cuáles no van */
function libro(lista,plan){
  const r={porVer:[],van:[],fuera:[]};
  for(const x of lista||[]){ const m=marcaLibro(plan,x.nombre,x.p&&x.p.sello); (m==='va'?r.van:m==='no'?r.fuera:r.porVer).push(x) }
  return r;
}
function planLimpio(p){
  p=p&&typeof p==='object'&&!Array.isArray(p)?p:{};
  const orden=Array.isArray(p.orden)?[...new Set(p.orden.filter(x=>typeof x==='string'&&x.trim()).map(x=>x.trim().slice(0,160)))].slice(0,500):[];
  const ps=Math.round(Number(p.por_semana));
  return {v:1, orden, por_semana:ps>=1&&ps<=7?ps:3, arranque:/^\d{4}-\d{2}-\d{2}$/.test(String(p.arranque||''))?String(p.arranque):'',
    cuando:typeof p.cuando==='string'?p.cuando.slice(0,40):'', por:typeof p.por==='string'?p.por.slice(0,40):'', visto:vistoLimpio(p.visto)};
}
/* las piezas con paquete que todavía no salen. Con plan, en el orden que fijó el editor; las que el
   plan no nombra (recién empacadas) van al final, por el número de su carpeta */
function listas(expedientes,publicada,plan){
  const lugar=new Map(((plan&&plan.orden)||[]).map((n,i)=>[n,i])), sin=1e9;
  return Object.entries(expedientes||{}).filter(([n,e])=>paquete(e)&&!publicada(n))
    .map(([nombre,e])=>({nombre,e,p:e.paquete}))
    .sort((a,b)=>{ const x=lugar.has(a.nombre)?lugar.get(a.nombre):sin, y=lugar.has(b.nombre)?lugar.get(b.nombre):sin;
      return x-y||(a.p.orden||sin)-(b.p.orden||sin)||a.nombre.localeCompare(b.nombre) });
}
/* poner una pieza en el lugar `lugar` (1 = primera) sin tocar el orden de las demás */
function mover(nombres,nombre,lugar){
  const l=nombres.filter(x=>x!==nombre); if(l.length===nombres.length) return nombres.slice();
  l.splice(Math.max(0,Math.min(l.length,Math.round(Number(lugar)||1)-1)),0,nombre); return l;
}
/* `n` fechas de salida (AAAA-MM-DD) desde `desde`, con el ritmo `porSemana` */
function fechasDeSalida(n,porSemana,desde){
  const dias=DIAS[porSemana]||DIAS[3], out=[]; if(!/^\d{4}-\d{2}-\d{2}$/.test(String(desde||''))) return out;
  const d=new Date(desde+'T12:00:00Z'); if(isNaN(d)) return out;
  for(let k=0;out.length<n&&k<n*7+14;k++){ if(dias.includes(d.getUTCDay())) out.push(d.toISOString().slice(0,10)); d.setUTCDate(d.getUTCDate()+1) }
  return out;
}
/* para cuántas semanas alcanza lo listo */
function alcance(n,porSemana){ const ps=DIAS[porSemana]?porSemana:3; return n>0?Math.ceil(n/ps):0 }
/* el texto común y lo que va después en cada red (el cierre de IG, la liga de FB) */
function partes(copy){
  const c=copy||{}, t=String(c.texto||''), cola=x=>{ x=String(x||''); return t&&x.startsWith(t)?x.slice(t.length):'' };
  return {texto:t, ig:cola(c.instagram), fb:cola(c.facebook), comentario:String(c.comentario||''), revision:Array.isArray(c.revision)?c.revision.filter(x=>typeof x==='string'&&x.trim()):[]};
}
function ligaValida(v){ v=String(v||'').trim(); return !v||/^https:\/\/[^\s"<>]{4,300}$/.test(v) }
/* en qué va una pieza de la línea: publicada · lista (paquete hecho) · texto (imágenes aprobadas,
   falta el texto) · video (le faltan etapas de video) · laminas · guion */
function estado(nombre,hechas,etapas,expedientes,publicada){
  if(publicada) return 'publicada';
  if(!hechas.has('laminas')) return hechas.has('guion')?'laminas':'guion';
  if(paquete((expedientes||{})[nombre])) return 'lista';
  return (etapas||[]).some(k=>['voz','escenas','corte'].includes(k)&&!hechas.has(k))?'video':'texto';
}
function cuantas(n,uno,varios){ return n+' '+(n===1?uno:varios) }
/* una orden de cambio como venga de la hoja o del aparato, en una forma en la que se puede confiar
   (las mismas reglas que nube/sala_cambios.py: una nota por imagen, en una línea, con tope) */
const idOk=x=>typeof x==='string'&&ID_TIRA.test(x)?x:'';
function cambioLimpio(c){
  c=c&&typeof c==='object'&&!Array.isArray(c)?c:{};
  const tira=typeof c.tira==='string'&&ID_TIRA.test(c.tira)?c.tira:'', porN=new Map();
  for(const o of Array.isArray(c.ordenes)?c.ordenes.slice(0,20):[]){
    const n=o&&o.n, nota=o&&typeof o.nota==='string'?o.nota.replace(/\s+/g,' ').trim().slice(0,NOTA_MAX):'';
    if(!Number.isInteger(n)||n<1||n>99||!nota) continue;
    porN.set(n,{n,nota,cuando:typeof o.cuando==='string'?o.cuando.slice(0,40):'',por:typeof o.por==='string'?o.por.slice(0,40):''});
  }
  return {v:1, pieza:typeof c.pieza==='string'?c.pieza.trim().slice(0,160):'', tira, paquete:idOk(c.paquete), ordenes:tira?[...porN.values()].sort((a,b)=>a.n-b.n):[],
    cuando:typeof c.cuando==='string'?c.cuando.slice(0,40):'', por:typeof c.por==='string'?c.por.slice(0,40):''};
}
/* las órdenes que siguen vivas para la versión `tira` de la pieza: cuando la mesa la rehace nace otra
   tira y la orden queda como historia, sin que nadie tenga que limpiarla */
function ordenesVigentes(cambio,tira){ const c=cambioLimpio(cambio); return tira&&c.tira===tira?c.ordenes:[] }
/* la orden nueva sobre lo que ya hubiera: una por imagen; si la pieza cambió de versión se empieza de cero */
function conOrden(previo,pedido){
  const c=cambioLimpio(previo), n=Number(pedido.n), mismo=c.tira===pedido.tira, base=mismo?c.ordenes.filter(o=>o.n!==n):[];
  /* `paquete`: la versión empacada cuando se pidió; en la segunda vuelta (misma tira) se conserva la primera */
  return cambioLimpio({pieza:pedido.pieza||c.pieza, tira:pedido.tira, paquete:mismo?(c.paquete||idOk(pedido.paquete)):idOk(pedido.paquete), ordenes:[...base,{n,nota:pedido.nota,cuando:pedido.ahora,por:pedido.quien}], cuando:pedido.ahora, por:pedido.quien});
}
function sinOrden(previo,n,quien,ahora){ const c=cambioLimpio(previo); return cambioLimpio({...c, ordenes:c.ordenes.filter(o=>o.n!==Number(n)), cuando:ahora, por:quien}) }
/* qué pasa con una pieza frente a su orden de cambio: '' (nada: puede estar en el montón) · 'pedido' (orden viva que
   Producción aún no atiende: se puede quitar) · 'volvio' (ya se rehízo o viene otra versión: el paquete viejo no se
   ofrece y se decide en la mesa). `empacada` = versión del paquete vigente ('' si no hay); `enMesa` = versión que la
   mesa enseña hoy ('' si no se sabe). Una orden que ya no corresponde a nada vigente es historia. */
function retiro(cambio,empacada,enMesa){
  const c=cambioLimpio(cambio); empacada=String(empacada||''); enMesa=String(enMesa||''); if(!c.tira) return '';
  const vivo=c.ordenes.length>0, nueva=!!enMesa&&enMesa!==c.tira;
  if(empacada&&c.tira===empacada) return nueva?'volvio':vivo?'pedido':'';   // quitada pero la mesa ya trae otra: no se ofrece el paquete viejo
  if(empacada&&c.paquete===empacada) return vivo&&!nueva?'pedido':'volvio';
  if(!empacada) return vivo&&!nueva?'pedido':'';
  return '';
}
/* lo mínimo de cada pieza lista para volver a pintarla al abrir, sin nada que parezca una llave */
function paraGuardar(lista){
  const secreto=/^(?:clave(?:_.*)?|token|access_token|refresh_token|authorization|password)$/i, out={};
  for(const x of lista){ const p=x.p, c=x.e.copy||{};
    out[x.nombre]={estado:x.e.estado||'lista', portada:x.e.portada||'',
      paquete:{orden:p.orden, formato:p.formato, nota_formato:p.nota_formato, url:p.url, sello:p.sello, id:p.id, slug:p.slug, imagenes:p.imagenes.map(i=>({n:i.n,src:i.src,dice:i.dice}))},
      copy:{texto:c.texto, instagram:c.instagram, facebook:c.facebook, comentario:c.comentario, revision:c.revision}} }
  return JSON.parse(JSON.stringify(out,(k,v)=>secreto.test(k)?undefined:v));
}
const puro={paquete,planLimpio,vistoLimpio,marcaLibro,conMarca,libro,listas,mover,fechasDeSalida,alcance,partes,ligaValida,estado,cuantas,paraGuardar,PLAN_LLAVE,
  cambioLimpio,ordenesVigentes,conOrden,sinOrden,retiro,CAMBIO_LLAVE,NOTA_MAX};
if(typeof module==='object'&&module.exports){ module.exports=puro; return }

/* ── pantalla ───────────────────────────────────────────────────────────────────────────── */
const leer=(k,d)=>{ try{ const v=JSON.parse(localStorage.getItem(k)||'null'); return v&&typeof v==='object'?v:d }catch(e){ return d } };
const guardar=(k,v)=>{ try{ localStorage.setItem(k,JSON.stringify(v)); return true }catch(e){ return false } };
/* vivo: ya contestó la hoja en esta visita · GUARD: lo último que este aparato vio de ella */
let vivo=false, fallo=false, GUARD=null, PLAN=planLimpio((leer(PLAN_LOCAL,{})||{}).plan), ORDEN=null, MODO='', PAGINA='', _tPlan=0, _aviso='', _tAviso=0, _releyendo=false;
/* slug → orden de cambio vigente o no; viene de la hoja y se recuerda en el aparato junto con lo listo */
let CAMBIOS={};
function publicadaAqui(n){ const m=leer(LLAVE,{}); return !!(m[n]&&m[n].fecha) }
/* de dónde se lee: la hoja si ya contestó; si no, lo guardado en el aparato; sin ninguna de las dos, lo que haya */
function exps(){ return !vivo&&GUARD?GUARD:(typeof EXP!=='undefined'?EXP:{}) }
function expDe(n){ return exps()[n]||null }
function paqueteDe(n){ return paquete(expDe(n)) }
function deHoy(){ return (typeof fecha!=='undefined'&&fecha)||new Date(Date.now()-7*36e5).toISOString().slice(0,10) }
function hoyHmo(){ return new Date(Date.now()-7*36e5).toISOString().slice(0,10) }
const miniatura=src=>typeof ligera==='function'?ligera(src):src;
/* todo lo que tiene paquete y no ha salido; de ahí, lo que tiene una orden de cambio sale del montón */
function conPaquete(){ return listas(exps(),n=>esPublicada(n),PLAN) }
function cambiosDeTira(pid){ if(!pid) return []; for(const c of Object.values(CAMBIOS)){ const o=ordenesVigentes(c,pid); if(o.length) return o } return [] }
function llaveDeTira(pid){ return Object.keys(CAMBIOS).find(s=>ordenesVigentes(CAMBIOS[s],pid).length)||'' }
/* la versión que la mesa enseña hoy para esa pieza; '' si la mesa no existe todavía o no lo sabe */
function enMesaDe(slug){ try{ const f=root.SalaTablero&&root.SalaTablero.pidDe, v=typeof f==='function'&&slug?f(slug):null; return typeof v==='string'?v:'' }catch(e){ return '' } }
/* el paquete vigente de una pieza: por su nombre o, si no, por la carpeta (slug) */
function paqueteVigente(nombre,slug){ let p=nombre?paqueteDe(nombre):null; if(!p&&slug) for(const e of Object.values(exps())){ const q=paquete(e); if(q&&q.slug===slug){ p=q; break } } return p }
/* UNA sola cuenta para el montón, el pie y «Cómo va». Evalúa todos los registros de la pieza (la llave pedida, la de su
   carpeta, o los que la nombran) y manda el primero que la retira. `mesa` = versión que enseña la mesa (de la primera
   llave que la sepa). Devuelve {estado, ordenes, slug, c, mesa, quitable}; quitable = se puede quitar con confirmación
   POSITIVA de la mesa (enseña justo la versión de la orden). */
function estadoDe(nombre,slug){
  const p=paqueteVigente(nombre,slug), emp=p&&ID_TIRA.test(String(p.id||''))?String(p.id):'';
  const claves=[...new Set([slug,p&&p.slug,...Object.keys(CAMBIOS).filter(k=>nombre&&CAMBIOS[k].pieza===nombre)].filter(k=>k&&CAMBIOS[k]))];
  const mesa=[slug,p&&p.slug,...claves].map(k=>k?enMesaDe(k):'').find(Boolean)||'', pub=!!nombre&&esPublicada(nombre);
  let gana=null;
  for(const k of claves){ const c=CAMBIOS[k], e=pub?'':retiro(c,emp,mesa); if(e){ gana={estado:e,ordenes:c.ordenes,slug:k,c,mesa,quitable:e==='pedido'&&mesa===c.tira}; break } }
  return gana||{estado:'',ordenes:[],slug:claves[0]||slug||'',c:claves[0]?CAMBIOS[claves[0]]:null,mesa,quitable:false};
}
function sinCambio(){ return conPaquete().filter(x=>!estadoDe(x.nombre,x.p.slug).estado) }
function pendientes(){ return sinCambio().filter(x=>marcaLibro(PLAN,x.nombre,x.p.sello)!=='no') }
/* las que un editor sacó del montón con «No va»: siguen con su paquete; nada se borra */
function vetadas(){ return libro(sinCambio(),PLAN).fuera }
function marcar(nombre,m){
  if(!puedeOrdenar()) return;
  const x=sinCambio().find(z=>z.nombre===nombre); if(!x) return;
  const l=pendientes(), i=l.findIndex(z=>z.nombre===nombre), resto=l.filter(z=>z.nombre!==nombre);
  if(m){ const sig=[...resto.slice(Math.max(i,0)),...resto.slice(0,Math.max(i,0))].find(z=>!marcaLibro(PLAN,z.nombre,z.p.sello)); PAGINA=sig?sig.nombre:(m==='va'?nombre:''); }
  else PAGINA=nombre;
  if(m&&MODO==='libro'&&!resto.some(z=>!marcaLibro(PLAN,z.nombre,z.p.sello))) MODO='';
  avisar(m==='va'?'«'+nombre+'» va: se queda en tu montón.':m==='no'?'«'+nombre+'» no va: salió del montón. Nada se borra; puedes regresarla abajo.':'«'+nombre+'» volvió al libro.');
  cambiarPlan({visto:conMarca(PLAN.visto,nombre,m,x.p.sello,ROL(),new Date().toISOString())},true);
}
/* el pie del montón: toda pieza con paquete que no está en el montón (y no publicada) está aquí, más las que piden cambio y
   todavía no tienen paquete */
function enCambio(){
  const out=[], vistas=new Set();
  for(const x of conPaquete()){ const r=estadoDe(x.nombre,x.p.slug); if(r.estado){ vistas.add(x.nombre); out.push({slug:r.slug,nombre:x.nombre,estado:r.estado,ordenes:r.ordenes,quitable:r.quitable}) } }
  for(const [slug,c] of Object.entries(CAMBIOS)){ const nombre=c.pieza||slug;
    if(vistas.has(nombre)||esPublicada(nombre)||paqueteVigente(nombre,slug)) continue;
    const r=estadoDe(nombre,slug); if(r.estado==='pedido'){ vistas.add(nombre); out.push({slug:r.slug,nombre,estado:'pedido',ordenes:r.ordenes,quitable:r.quitable}) } }
  return out;
}
function hay(){ try{ return ENTRADO()&&pendientes().length>0 }catch(e){ return false } }
function puedeOrdenar(){ return DECIDE()&&(vivo||!!GUARD) }
/* quien entró como editor ve el libro desde el primer instante; decidir se habilita cuando la mesa vigente confirma */
function editorAqui(){ try{ return ENTRADO()&&/^editor2?$/.test(ROL()) }catch(e){ return false } }
async function dueno(){
  if(typeof SalaMesaLocal==='undefined'||typeof identidadMesaLocal!=='function') return null;
  try{ return await SalaMesaLocal.scope(identidadMesaLocal(),window.crypto) }catch(e){ return null }
}

/* las que tienen todas sus imágenes aprobadas y todavía no tienen paquete: unas esperan su texto y
   otras están guardadas por regla (REGLAS salida_excluir) hasta que Dirección decida */
async function sinPaquete(){
  // Sólo con la Línea ya calculada: abrir la Sala no debe bajar todas las tiras para pintar este aviso.
  try{ const piezas=(typeof LINEA_PIEZAS!=='undefined'&&LINEA_PIEZAS)||null; if(!piezas||!vivo) return {espera:0,guardadas:[]};
    const l=piezas.filter(z=>z.tira&&!esPublicada(z.nombre)&&!paqueteDe(z.nombre)&&hechasDe(z,false).has('laminas'));
    const guardada=z=>typeof salidaGuardada==='function'&&salidaGuardada(z.slug);
    return {espera:l.filter(z=>!guardada(z)).length, guardadas:l.filter(guardada).map(z=>z.nombre)} }catch(e){ return {espera:0,guardadas:[]} }
}
const corta=f=>{ try{ return new Date(f+'T12:00:00').toLocaleDateString('es-MX',{weekday:'short',day:'numeric',month:'short'}).replace(/[.,]/g,'').replace(' de ',' ') }catch(e){ return f } };
const larga=f=>{ try{ return new Date(f+'T12:00:00').toLocaleDateString('es-MX',{weekday:'long',day:'numeric',month:'long'}).replace(',','') }catch(e){ return f } };
/* desde cuándo corre el calendario: el arranque que fijó el editor, o hoy si ese día ya pasó */
function desde(){ return PLAN.arranque?(PLAN.arranque>hoyHmo()?PLAN.arranque:hoyHmo()):'' }
function cuando(i,fechas){ return fechas[i]?(fechas[i]===hoyHmo()?'Hoy · ':'')+corta(fechas[i]):'Semana '+(Math.floor(i/PLAN.por_semana)+1) }
function tarjeta(x,i,fechas,n){
  const img=x.e.portada||(x.p.imagenes[0]||{}).src||'', k=x.p.imagenes.length, foto=miniatura(img);
  const dentro=`<span class="sal-foto">${foto?`<img src="${esc(foto)}" alt="" loading="lazy" decoding="async">`:''}<span class="sal-n">${i+1}</span></span>
    <b>${esc(x.nombre)}</b><small>${esc(x.p.formato||'Publicación')} · ${cuantas(k,'imagen','imágenes')}</small><small class="sal-cuando">${esc(cuando(i,fechas))}${marcaLibro(PLAN,x.nombre,x.p.sello)==='va'?' · ✓ va':''}</small>`;
  if(ORDEN) return `<div class="sal-carta ordenando" data-pieza="${esc(x.nombre)}">${dentro}
    <span class="sal-mueve"><button type="button" data-paso="-1" aria-label="Sale antes: ${esc(x.nombre)}" ${i?'':'disabled'}>◀</button>
      <select data-lugar aria-label="Lugar de salida de ${esc(x.nombre)}">${Array.from({length:n},(_,j)=>`<option value="${j+1}"${j===i?' selected':''}>${j+1}</option>`).join('')}</select>
      <button type="button" data-paso="1" aria-label="Sale después: ${esc(x.nombre)}" ${i<n-1?'':'disabled'}>▶</button></span></div>`;
  return `<button class="sal-carta${fechas[i]===hoyHmo()?' hoy':''}" type="button" data-publicar="${esc(x.nombre)}">${dentro}<span class="sal-ir">Abrir →</span></button>`;
}
function resumen(n,fechas){
  const sem=alcance(n,PLAN.por_semana), ritmo=`A ${PLAN.por_semana} por semana`;
  if(fechas.length===n&&n) return `${ritmo}, desde el ${larga(fechas[0])}, alcanza hasta el <b>${larga(fechas[n-1])}</b>.`;
  return `${ritmo} alcanza para <b>${cuantas(sem,'semana','semanas')}</b>.`;
}
function controles(n,porVer){
  if(!puedeOrdenar()||!n) return '';
  if(ORDEN) return `<div class="sal-plan"><span class="sal-ayuda">Mueve cada una con las flechas o elige su lugar.</span><button type="button" class="sal-b fuerte" data-orden-ok>Guardar el orden</button><button type="button" class="sal-b" data-orden-no>Cancelar</button></div>`;
  return `<div class="sal-plan" role="group" aria-label="Plan de salida">
    <span class="sal-ritmo"><button type="button" data-ritmo="-1" aria-label="Menos por semana" ${PLAN.por_semana>1?'':'disabled'}>−</button><span><b>${PLAN.por_semana}</b> por semana</span><button type="button" data-ritmo="1" aria-label="Más por semana" ${PLAN.por_semana<7?'':'disabled'}>+</button></span>
    <label class="sal-arr">Arranca <input type="date" id="salArranque" value="${esc(PLAN.arranque)}" aria-label="Día en que arranca la salida"></label>
    ${n>1?'<button type="button" class="sal-b" data-ordenar>Cambiar el orden</button>':''}
    <button type="button" class="sal-b${porVer?' fuerte':''}" data-lista="0">${porVer?'Volver al libro · '+porVer+' por decidir':'Abrir el libro'}</button></div>`;
}
/* EL LIBRO (12-nov, chinche CHN-20261112-0840-a2f9): «hasta arriba quiero la decisión de cada una de las
   propuestas… no todas juntas… un libro». Una publicación por página, con su decisión; la lista queda a un toque. */
function pagina(l,fechas){
  let i=l.findIndex(x=>x.nombre===PAGINA);
  if(i<0){ i=l.findIndex(x=>!marcaLibro(PLAN,x.nombre,x.p.sello)); if(i<0) i=0; PAGINA=l[i].nombre }
  const x=l[i], p=x.p, n=l.length, k=p.imagenes.length, c=partes(x.e.copy), m=marcaLibro(PLAN,x.nombre,p.sello), decide=puedeOrdenar(), cambio=decide&&puedePedirCambio(x.nombre)&&ID_TIRA.test(String(p.id||''))&&SLUG_OK.test(String(p.slug||''));
  return `<article class="sal-libro" data-libro="${esc(x.nombre)}" aria-label="Página ${i+1} de ${n}: ${esc(x.nombre)}">
    <div class="sal-lib-cab"><span class="sal-lib-pag">Página ${i+1} de ${n}</span>${m==='va'?'<span class="sal-lib-ya">✓ Dijiste «va»</span>':''}</div>
    <h3>${esc(x.nombre)}</h3>
    <p class="sal-sub">${esc(p.formato||'Publicación')} · ${cuantas(k,'imagen','imágenes')} · sale: ${esc(cuando(i,fechas))}</p>
    <div class="sal-lib-tira" role="list" tabindex="0" aria-label="Imágenes de ${esc(x.nombre)}">${p.imagenes.map((im,j)=>`<button type="button" role="listitem" class="sal-lib-img" data-zoom="${esc(im.src)}" aria-label="Imagen ${Number(im.n)||j+1} de ${k}: ${esc(im.dice||'')}. Ampliar">${miniatura(im.src)?`<img src="${esc(miniatura(im.src))}" alt="" loading="${j?'lazy':'eager'}" decoding="async">`:''}<i>${Number(im.n)||j+1}</i></button>`).join('')}</div>
    ${c.revision.length?`<div class="sal-ojo"><b>Antes de decidir, mira esto</b><ul>${c.revision.map(t=>`<li>${esc(t)}</li>`).join('')}</ul></div>`:''}
    ${c.texto?`<details class="sal-lib-texto"><summary>El texto que la acompaña</summary><p>${esc(c.texto)}</p></details>`:''}
    <div class="sal-lib-dec" role="group" aria-label="Decidir esta publicación">
      <button type="button" class="va" data-lib="va"${m==='va'?' aria-pressed="true"':''}${decide?'':' disabled'}><span aria-hidden="true">✓</span>Va</button>
      <button type="button" data-lib="cambio"${cambio?'':' disabled title="Se habilita cuando el Sheet confirma"'}><span aria-hidden="true">✎</span>Pedir cambio</button>
      <button type="button" class="no" data-lib="no"${decide?'':' disabled'}><span aria-hidden="true">✕</span>No va</button>
    </div>${decide?'':'<p class="sal-lib-nota">Puedes ir leyendo; las decisiones se habilitan cuando el Sheet confirma tu entrada.</p>'}
    <div class="sal-lib-nav"><button type="button" data-lib-ir="-1" ${i?'':'disabled'}>← Anterior</button><button type="button" class="sal-mini" data-publicar="${esc(x.nombre)}">Abrir para publicar</button><button type="button" data-lib-ir="1" ${i<n-1?'':'disabled'}>Siguiente →</button></div>
  </article>`;
}
let _hubo=null;
async function pintar(){
  const hoy=$('#salidaHoy'); if(!hoy) return;
  let html='';
  if(ENTRADO()){
    if(vivo) conciliar();
    const sabe=vivo||!!GUARD, l=sabe?pendientes():[], n=l.length, {espera,guardadas}=await sinPaquete(), cambios=sabe?enCambio():[];
    if(ORDEN&&!n) ORDEN=null;
    const lib=libro(l,PLAN), fuera=sabe?vetadas():[], enLibro=editorAqui()&&n>0&&!ORDEN&&(MODO==='libro'||(MODO===''&&lib.porVer.length>0));
    const vista=ORDEN?ORDEN.map(nombre=>l.find(x=>x.nombre===nombre)).filter(Boolean):l;
    const fechas=fechasDeSalida(n,PLAN.por_semana,desde());
    if(!sabe&&fallo) html=`<section class="sal sal-aviso" aria-label="Listas para publicar"><header><span class="bt-eyebrow">TU MONTÓN</span><h2>No pude leer lo que está listo</h2><p>El Sheet no contestó. Tus publicaciones siguen en Drive y en la hoja; sólo falta volver a preguntar.</p></header><div class="sal-plan"><button type="button" class="sal-b fuerte" data-releer>Reintentar</button></div></section>`;
    else if(sabe&&(n||espera||guardadas.length||cambios.length||fuera.length)) html=`<section class="sal${ORDEN?' en-orden':''}${enLibro?' en-libro':''}" aria-label="Listas para publicar">
    <div class="sal-cab"><header><span class="bt-eyebrow">${enLibro?'TU LIBRO':'TU MONTÓN'}</span>
      <h2>${enLibro?(lib.porVer.length?cuantas(lib.porVer.length,'publicación por decidir','publicaciones por decidir'):'Tu libro, ya revisado'):n?cuantas(n,'lista para lanzar','listas para lanzar'):'Todavía no hay nada listo para lanzar'}</h2>
      <p>${enLibro?`Una a la vez: <b>va</b>, <b>pide un cambio</b> o <b>no va</b>.${lib.van.length?` Ya dijiste «va» a ${lib.van.length} de ${n}.`:''} Nada sale solo: tú das el clic de publicar.`:n?(fechas[0]===hoyHmo()?`Hoy toca <b>«${esc(vista[0].nombre)}»</b>. `:'')+resumen(n,fechas)+' Nada sale solo: tú das el clic de publicar.':'En cuanto una pieza tenga sus imágenes aprobadas y su texto, aparece aquí.'}</p>
      ${!vivo?`<p class="sal-nota">${fallo?'El Sheet no contestó: ves lo último que este aparato guardó.':'Lo último que este aparato guardó; confirmando con el Sheet…'}${fallo?' <button type="button" class="sal-mini" data-releer>Reintentar</button>':''}</p>`:''}</header>
      ${enLibro?`<div class="sal-plan"><button type="button" class="sal-b" data-lista="1">Ver las ${n} en lista</button></div>`:controles(n,lib.porVer.length)||(editorAqui()&&n&&!ORDEN?`<div class="sal-plan"><button type="button" class="sal-b" data-lista="0">${lib.porVer.length?'Volver al libro · '+lib.porVer.length+' por decidir':'Abrir el libro'}</button></div>`:'')}</div>
    ${enLibro?pagina(l,fechas):n?`<div class="sal-rejilla">${vista.map((x,i)=>tarjeta(x,i,fechas,n)).join('')}</div>`:''}
    <p class="sal-estado" role="status" aria-live="polite">${esc(_aviso)}</p>
    ${espera?`<p class="sal-pie"><b>${cuantas(espera,'pieza más','piezas más')}</b> ya ${espera===1?'tiene':'tienen'} sus imágenes aprobadas y ${espera===1?'espera':'esperan'} su texto. Es el paso del consejo; cuando lo escriba, ${espera===1?'aparece':'aparecen'} aquí.</p>`:''}
    ${cambios.length?`<div class="sal-pie sal-cambios"><p><b>${cuantas(cambios.length,'pieza fuera del montón por un cambio','piezas fuera del montón por un cambio')}</b>:</p>
      <ul>${cambios.map(x=>{ const notas=x.ordenes.map(o=>` · imagen ${o.n}: «${esc(o.nota)}»`).join(''), uno=x.ordenes.length===1;
        const quitar=x.estado==='pedido'&&x.quitable&&puedePedirCambio(x.nombre)?x.ordenes.map(o=>` <button type="button" class="sal-mini" data-quitar-cambio="${esc(x.slug)}" data-n="${o.n}">${uno?'Quitar la petición':'Quitar la de la imagen '+o.n}</button>`).join(''):'';
        return `<li><span><b>${esc(x.nombre)}</b>${notas}. ${x.estado==='volvio'?'Hay una versión nueva: cuando esté aprobada y con su paquete nuevo, vuelve aquí.':'Pedido a Producción con la nota del editor; suele tardar varias horas.'}</span>${quitar}</li>` }).join('')}</ul></div>`:''}
    ${fuera.length?`<div class="sal-pie sal-cambios"><p><b>${cuantas(fuera.length,'publicación con «No va»','publicaciones con «No va»')}</b> (fuera del montón; nada se borra):</p>
      <ul>${fuera.map(x=>`<li><span><b>${esc(x.nombre)}</b></span>${puedeOrdenar()?` <button type="button" class="sal-mini" data-lib-volver="${esc(x.nombre)}">Regresarla al libro</button>`:''}</li>`).join('')}</ul></div>`:''}
    ${guardadas.length?`<p class="sal-pie"><b>${cuantas(guardadas.length,'pieza guardada','piezas guardadas')}</b> (no ${guardadas.length===1?'sale':'salen'} hasta que tú digas; nada se borra): ${esc(guardadas.join(' · '))}.</p>`:''}
  </section>`;
  }
  if(hoy._html!==html){ hoy._html=html; hoy.innerHTML=html; enlazar(hoy) }   // sin cambios no se repinta: no se pierde el desplazamiento
  // La mesa se pliega cuando hay montón y nada por revisar: se le avisa sólo si eso cambió.
  const hubo=hay(); if(hubo!==_hubo){ _hubo=hubo; if(root.SalaTablero&&typeof root.SalaTablero.render==='function'){ try{ root.SalaTablero.render() }catch(e){} } }
}
function enlazar(hoy){
  hoy.querySelectorAll('[data-publicar]').forEach(b=>b.onclick=()=>abrir(b.dataset.publicar));
  hoy.querySelectorAll('[data-releer]').forEach(b=>b.onclick=()=>actualizar());
  hoy.querySelectorAll('[data-lista]').forEach(b=>b.onclick=()=>{ MODO=b.dataset.lista==='1'?'lista':'libro'; avisar(''); pintar() });
  hoy.querySelectorAll('[data-lib-volver]').forEach(b=>b.onclick=()=>{ MODO=''; marcar(b.dataset.libVolver,'') });
  const hojaLibro=hoy.querySelector('.sal-libro');
  if(hojaLibro){ const nombre=hojaLibro.dataset.libro;
    hojaLibro.querySelectorAll('[data-zoom]').forEach(b=>b.onclick=()=>{ if(typeof abrirZoom==='function') abrirZoom(b.dataset.zoom) });
    hojaLibro.querySelectorAll('[data-lib-ir]').forEach(b=>b.onclick=()=>{ const l=pendientes(), i=l.findIndex(x=>x.nombre===nombre)+Number(b.dataset.libIr); if(l[i]){ PAGINA=l[i].nombre; avisar(''); pintar().then(()=>{ const h=document.querySelector('#salidaHoy .sal-libro h3'); if(h) h.scrollIntoView({block:'nearest'}) }) } });
    hojaLibro.querySelectorAll('[data-lib]').forEach(b=>b.onclick=()=>{ const m=b.dataset.lib;
      if(m==='cambio'){ abrir(nombre); const c=document.getElementById('salCambio'); if(c) c.click(); return }
      marcar(nombre,m) });
  }
  hoy.querySelectorAll('[data-quitar-cambio]').forEach(b=>b.onclick=async()=>{ b.disabled=true; avisar('Quitando la petición…'); pintar();
    const r=await quitarCambio(b.dataset.quitarCambio,Number(b.dataset.n)); avisar(r.ok?'Petición quitada.':r.motivo); pintar() });
  hoy.querySelectorAll('[data-ritmo]').forEach(b=>b.onclick=()=>cambiarPlan({por_semana:Math.max(1,Math.min(7,PLAN.por_semana+Number(b.dataset.ritmo)))}));
  const arr=hoy.querySelector('#salArranque'); if(arr) arr.onchange=()=>cambiarPlan({arranque:arr.value||''});
  const ord=hoy.querySelector('[data-ordenar]'); if(ord) ord.onclick=()=>{ ORDEN=pendientes().map(x=>x.nombre); avisar(''); pintar() };
  const no=hoy.querySelector('[data-orden-no]'); if(no) no.onclick=()=>{ ORDEN=null; pintar() };
  const ok=hoy.querySelector('[data-orden-ok]'); if(ok) ok.onclick=()=>{ const orden=ORDEN; ORDEN=null; cambiarPlan({orden},true) };
  hoy.querySelectorAll('.sal-carta.ordenando').forEach(c=>{ const nombre=c.dataset.pieza, i=ORDEN?ORDEN.indexOf(nombre):-1; if(i<0) return;
    c.querySelectorAll('[data-paso]').forEach(b=>b.onclick=()=>recolocar(nombre,i+1+Number(b.dataset.paso)));
    const s=c.querySelector('[data-lugar]'); if(s) s.onchange=()=>recolocar(nombre,Number(s.value)) });
}
async function recolocar(nombre,lugar){
  if(!ORDEN) return; ORDEN=mover(ORDEN,nombre,lugar); await pintar();
  const c=[...document.querySelectorAll('#salidaHoy .sal-carta.ordenando')].find(x=>x.dataset.pieza===nombre);
  if(c){ const s=c.querySelector('[data-lugar]'); if(s) s.focus({preventScroll:true}); c.scrollIntoView({block:'nearest',inline:'nearest'}) }
}
function avisar(t){ _aviso=t||''; clearTimeout(_tAviso); if(_aviso) _tAviso=setTimeout(()=>{ _aviso=''; pintar() },6000) }
/* MODO: '' = el libro mientras falte decidir y, ya decidido todo, la lista · 'lista' · 'libro' (abiertos a mano) */
/* el plan cambia aquí al instante y sube a la hoja; si no sube, se queda en el aparato y se reintenta al abrir */
function cambiarPlan(cambio,ya){
  if(!DECIDE()) return;
  PLAN=planLimpio({...PLAN,...cambio,cuando:new Date().toISOString(),por:ROL()});
  guardar(PLAN_LOCAL,{plan:PLAN,pendiente:true}); pintar();
  clearTimeout(_tPlan); _tPlan=setTimeout(subirPlan,ya?0:900);   // varios toques seguidos al ritmo son UNA escritura
}
async function subirPlan(){
  const plan=PLAN, sello=plan.cuando;
  try{
    const r=await fetch(GAS(),{method:'POST',headers:{'Content-Type':'text/plain'},body:JSON.stringify({accion:'expediente',clave:CLAVE(),pieza:PLAN_LLAVE,expediente:plan})});
    const j=await leerJSON(r); if(!r.ok||!j||j.ok!==true) throw Error((j&&j.error)||'sin confirmación');
    if(PLAN.cuando===sello){ guardar(PLAN_LOCAL,{plan,pendiente:false}); avisar('Plan guardado en el Sheet.') }
  }catch(e){ if(PLAN.cuando===sello) avisar(/solo el agente|solo lee|rol/i.test(String(e&&e.message||e))?'Tu llave todavía no puede guardar el plan en el Sheet; quedó en este aparato.':'El plan no subió al Sheet; quedó en este aparato y se reintenta al abrir.') }
  pintar();
}
/* ── órdenes de cambio: no se dan por pedidas hasta que la hoja las confirma ─────────────── */
function puedePedirCambio(nombre){ return !!(DECIDE()&&vivo&&!(nombre&&esPublicada(nombre))) }
async function subirCambio(slug,registro){
  const r=await fetch(GAS(),{method:'POST',headers:{'Content-Type':'text/plain'},body:JSON.stringify({accion:'expediente',clave:CLAVE(),pieza:CAMBIO_LLAVE+slug,expediente:registro})});
  const j=await leerJSON(r); if(!r.ok||!j||j.ok!==true) throw Error((j&&j.error)||'sin confirmación');
}
const sinPermiso=e=>/solo el agente|solo lee|rol/i.test(String(e&&e.message||e));
async function trasCambio(){
  await pintar(); recordar();
  try{ if(root.SalaTablero&&typeof root.SalaTablero.render==='function') root.SalaTablero.render() }catch(e){}
  if(typeof LINEA_PIEZAS!=='undefined') _lineaHoyT=0;
  if(document.body.dataset.vista==='prod'&&typeof pintarProduccion==='function') pintarProduccion();
}
async function pedirCambio(pedido){
  pedido=pedido||{}; const slug=String(pedido.slug||''), tira=String(pedido.tira||''), n=Number(pedido.n), pieza=String(pedido.pieza||''), no=motivo=>({ok:false,motivo});
  if(!DECIDE()) return no('Pedir cambios es de los editores.');
  if(!vivo) return no('Todavía no se puede pedir el cambio: falta que conteste el Sheet.');
  if(pieza&&esPublicada(pieza)) return no('Esta pieza ya está publicada: no se rehace.');
  if(!SLUG_OK.test(slug)||!ID_TIRA.test(tira)) return no('No pude identificar la pieza o su versión. Actualiza la página e inténtalo otra vez.');
  if(!Number.isInteger(n)||n<1||n>99) return no('No pude identificar la imagen.');
  if(!String(pedido.nota||'').trim()) return no('Escribe qué debe cambiar.');
  const mesa=enMesaDe(slug); if(mesa&&mesa!==tira) return no('Esa versión ya no es la vigente: la versión nueva está en tu mesa.');
  const r=estadoDe(pieza,slug); if(r.estado&&r.c&&r.c.tira!==tira&&mesa!==tira) return no('Esta pieza ya tiene un cambio pedido sobre otra versión. Pídelo desde tu mesa, en la versión que está ahí.');
  const p=paqueteVigente(pieza,slug), nuevo=conOrden(CAMBIOS[slug],{pieza,tira,paquete:p?p.id:'',n,nota:pedido.nota,quien:ROL(),ahora:new Date().toISOString()});
  if(!nuevo.ordenes.some(o=>o.n===n)) return no('Escribe qué debe cambiar.');
  try{ await subirCambio(slug,nuevo) }
  catch(e){ return no(sinPermiso(e)?'Tu llave todavía no puede pedir cambios desde la Sala. No se pidió nada.':'El Sheet no contestó. No se pidió nada: inténtalo otra vez.') }
  CAMBIOS[slug]=nuevo; await trasCambio(); return {ok:true};
}
async function quitarCambio(slug,n){
  slug=String(slug||''); const previo=CAMBIOS[slug], no=motivo=>({ok:false,motivo});
  if(!DECIDE()) return no('Pedir cambios es de los editores.');
  if(!vivo) return no('Todavía no se puede quitar la petición: falta que conteste el Sheet.');
  if(!SLUG_OK.test(slug)||!previo||!previo.ordenes.some(o=>o.n===Number(n))) return no('Esa petición ya no está.');
  const nombre=previo.pieza||slug;
  if(esPublicada(nombre)) return no('Esta pieza ya está publicada: no se rehace.');
  const r=estadoDe(nombre,slug);
  if(!r.mesa) return no('No pude confirmar con tu mesa si Producción ya la rehízo. Actualiza e inténtalo otra vez.');
  if(r.mesa!==previo.tira||retiro(previo,(paqueteVigente(nombre,slug)||{}).id,r.mesa)!=='pedido') return no('Producción ya la rehízo: decide la versión nueva en tu mesa.');
  const nuevo=sinOrden(previo,n,ROL(),new Date().toISOString());
  try{ await subirCambio(slug,nuevo) }
  catch(e){ return no(sinPermiso(e)?'Tu llave todavía no puede quitar peticiones desde la Sala. No se quitó nada.':'El Sheet no contestó. No se quitó nada: inténtalo otra vez.') }
  CAMBIOS[slug]=nuevo;   // se conserva aunque quede sin órdenes: 'volvio' necesita saber la tira y el paquete
  await trasCambio(); return {ok:true};
}
function quitarCambioDeTira(pid,n){ return quitarCambio(llaveDeTira(pid),n) }
/* para la mesa y «Cómo va»: la orden viva de una imagen de esa versión, y el estado de una pieza frente a su orden */
function cambioDe(pid,n){ return cambiosDeTira(pid).find(o=>o.n===Number(n))||null }
function cambioDePieza(nombre,slug){ const r=estadoDe(nombre,slug); return {estado:r.estado,ordenes:r.ordenes} }
function cargarCambios(crudo){
  const out={};
  for(const [slug,v] of Object.entries(crudo&&typeof crudo==='object'&&!Array.isArray(crudo)?crudo:{})){ const c=cambioLimpio(v); if(SLUG_OK.test(slug)&&c.tira) out[slug]=c }
  return out;
}
async function copiar(texto,boton){
  let ok=false;
  try{ await navigator.clipboard.writeText(texto); ok=true }catch(e){
    try{ const t=document.createElement('textarea'); t.value=texto; t.setAttribute('readonly',''); t.style.cssText='position:fixed;opacity:0'; document.body.appendChild(t); t.select(); ok=document.execCommand('copy'); t.remove() }catch(_){ ok=false } }
  if(boton){ const antes=boton.dataset.txt||boton.textContent; boton.dataset.txt=antes; boton.textContent=ok?'Copiado ✓':'No se pudo copiar: selecciónalo a mano'; boton.classList.toggle('ok',ok);
    clearTimeout(boton._t); boton._t=setTimeout(()=>{ boton.textContent=antes; boton.classList.remove('ok') },2200) }
  return ok;
}
function abrir(nombre){
  const e=expDe(nombre), p=paquete(e); if(!p) return;
  const c=partes(e.copy), borr=leer(BORRADOR,{}), sello=String(p.sello||''), mio=borr[nombre]&&borr[nombre].sello===sello?String(borr[nombre].texto||''):'';
  const n=p.imagenes.length, puede=DECIDE()&&!esPublicada(nombre), cambio=cambioDePieza(nombre,p.slug).estado, fuera=cambio!=='';
  const nImg=(im,k)=>Number(im.n)||k+1;   // la misma numeración que se manda y que sale en el pie
  const l=pendientes(), i=l.findIndex(x=>x.nombre===nombre), fechas=fechasDeSalida(l.length,PLAN.por_semana,desde());
  const v=hoja(`<div class="sal-hoja">
    <h3>${esc(nombre)}</h3>
    <p class="sal-sub">${esc(p.formato||'Publicación')} · ${cuantas(n,'imagen','imágenes')}${p.nota_formato?' · '+esc(p.nota_formato):''}${i>=0?` · sale en el lugar ${i+1} de ${l.length} (${esc(cuando(i,fechas))})`:''}</p>
    ${fuera?`<div class="sal-ojo sal-fuera" role="status"><b>${cambio==='pedido'?'Esta pieza tiene un cambio pedido: este paquete ya no es el que va a salir.':'Hay una versión nueva de esta pieza: este paquete ya no es el que va a salir.'}</b></div>`:''}
    <div class="sal-tira" role="list">${p.imagenes.map((im,k)=>`<button type="button" role="listitem" class="sal-img" data-zoom="${esc(im.src)}" aria-label="Imagen ${nImg(im,k)} de ${n}: ${esc(im.dice||'')}. Ampliar">${miniatura(im.src)?`<img src="${esc(miniatura(im.src))}" alt="" loading="lazy">`:''}<i>${nImg(im,k)}</i></button>`).join('')}</div>
    ${c.revision.length?`<div class="sal-ojo"><b>Antes de publicar, mira esto</b><ul>${c.revision.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:''}
    <div class="sal-paso"><h4><i>1</i>Las imágenes</h4>
      <p>Están en Drive, numeradas en el orden en que van.</p>
      ${/^https:\/\/drive\.google\.com\//.test(p.url||'')?`<a class="secund sal-liga" href="${esc(p.url)}" target="_blank" rel="noopener">Abrir la carpeta en Drive ↗</a>`:''}
      ${puede&&!fuera&&puedePedirCambio(nombre)&&ID_TIRA.test(String(p.id||''))&&SLUG_OK.test(String(p.slug||''))?`<button type="button" class="sal-mini" id="salCambio" aria-expanded="false" aria-controls="salCambioCaja">Pedir cambio a una imagen</button>
      <div class="sal-cambio" id="salCambioCaja" hidden>
        ${n>1?`<label class="sal-lab" for="salCambioN">¿Cuál imagen?</label>
        <select id="salCambioN">${p.imagenes.map((im,k)=>`<option value="${nImg(im,k)}">Imagen ${nImg(im,k)}${im.dice?' · '+esc(String(im.dice).slice(0,48)):''}</option>`).join('')}</select>`:''}
        <label class="sal-lab" for="salCambioNota">Qué debe cambiar</label>
        <textarea id="salCambioNota" rows="3" maxlength="${NOTA_MAX}" placeholder="Una línea basta. Producción la toma como orden de trabajo."></textarea>
        <button type="button" class="secund" id="salCambioOk">Enviar a Producción</button>
        <p class="aviso" id="salCambioAviso" role="status" aria-live="polite">La pieza sale de tu montón y vuelve cuando apruebes su versión nueva.</p>
      </div>`:''}</div>
    <div class="sal-paso"><h4><i>2</i>El texto</h4>
      <p>Cámbialo aquí si quieres; se copia tal como lo dejes.</p>
      <textarea id="salTexto" rows="9" spellcheck="true" aria-label="Texto de la publicación">${esc(mio||c.texto)}</textarea>
      ${mio&&mio!==c.texto?`<button type="button" class="sal-mini" id="salOriginal">Volver al texto del consejo</button>`:''}
      <div class="sal-botones"><button type="button" class="secund" id="salIg">Copiar para Instagram</button><button type="button" class="secund" id="salFb">Copiar para Facebook</button></div></div>
    <div class="sal-paso"><h4><i>3</i>La liga (primer comentario en Instagram)</h4>
      <p class="sal-url">${esc(c.comentario)}</p>
      <button type="button" class="secund" id="salCom">Copiar la liga</button></div>
    ${puede&&!fuera?`<div class="sal-paso fin"><h4><i>4</i>Cuando ya esté publicada</h4>
      <label class="sal-lab" for="salPost">Liga de la publicación (si la tienes a la mano)</label>
      <input id="salPost" type="url" inputmode="url" autocomplete="off" placeholder="https://www.instagram.com/p/…">
      <button type="button" class="listo" id="salYa">Ya la publiqué</button>
      <p class="aviso" id="salAviso" role="status" aria-live="polite"></p></div>`
      :`<p class="nota-pie">${esPublicada(nombre)?'Esta pieza ya está anotada como publicada.':fuera?'Este paquete no se publica: espera la versión nueva.':'Publicar y anotar la publicación corresponde a los editores.'}</p>`}
  </div>`,'publicar-'+normSlug(nombre));
  const q=s=>v.querySelector(s), txt=q('#salTexto');
  v.querySelectorAll('[data-zoom]').forEach(b=>b.onclick=()=>{ if(typeof abrirZoom==='function') abrirZoom(b.dataset.zoom) });
  txt.oninput=()=>{ const b=leer(BORRADOR,{}); if(txt.value===c.texto) delete b[nombre]; else b[nombre]={sello,texto:txt.value}; guardar(BORRADOR,b) };
  const orig=q('#salOriginal'); if(orig) orig.onclick=()=>{ txt.value=c.texto; txt.oninput(); orig.remove() };
  q('#salIg').onclick=ev=>copiar(txt.value.trim()+c.ig,ev.currentTarget);
  q('#salFb').onclick=ev=>copiar(txt.value.trim()+c.fb,ev.currentTarget);
  q('#salCom').onclick=ev=>copiar(c.comentario,ev.currentTarget);
  const pide=q('#salCambio');
  if(pide){ const caja=q('#salCambioCaja'), nota=q('#salCambioNota'), dice=q('#salCambioAviso'), manda=q('#salCambioOk');
    pide.onclick=()=>{ caja.hidden=!caja.hidden; pide.setAttribute('aria-expanded',String(!caja.hidden)); if(!caja.hidden) nota.focus() };
    manda.onclick=async()=>{
      const texto=nota.value.trim(); if(!texto){ dice.textContent='Escribe qué debe cambiar: sin una línea, Producción no sabe qué hacer.'; nota.focus(); return }
      const cual=q('#salCambioN'), num=cual?Number(cual.value):Number(p.imagenes[0].n)||1;
      manda.disabled=true; dice.textContent='Enviando…';
      const r=await pedirCambio({slug:p.slug,pieza:nombre,tira:p.id,n:num,nota:texto});
      if(!r.ok){ manda.disabled=false; dice.textContent=r.motivo; return }
      cerrarCapa('publicar-'+normSlug(nombre)); avisar('Cambio pedido. «'+nombre+'» sale de tu montón; Producción lo toma en su siguiente vuelta (puede tardar varias horas) y vuelve cuando apruebes su versión nueva.'); pintar();
    } }
  const ya=q('#salYa'); if(!ya) return;
  ya.onclick=async()=>{
    const av=q('#salAviso'), liga=q('#salPost').value.trim();
    if(!ligaValida(liga)){ av.textContent='Esa liga no parece una dirección completa (empieza con https://). Corrígela o déjala vacía.'; return }
    ya.disabled=true; av.textContent='Anotando…';
    const final=txt.value.trim(), det={texto:'Publicada desde la Sala'}; if(final&&final!==c.texto) det.texto_final=final.slice(0,2200);
    let r; try{ r=await correcciones().enviar({accion:'produccion',fecha:deHoy(),pieza:nombre,estado:'publicada',detalle:JSON.stringify(det),enlace:liga,quien:ROL()}) }catch(err){ r={estado:'local'} }
    if(r.estado==='rechazado'||r.estado==='local'){ ya.disabled=false; av.textContent=r.estado==='rechazado'?'La Sala no aceptó la anotación con tu acceso. No se anotó nada.':'No se pudo guardar en este aparato. Inténtalo otra vez.'; return }
    const m=leer(LLAVE,{}); m[nombre]={fecha:deHoy(),liga,sello}; guardar(LLAVE,m);
    if(typeof D!=='undefined'&&D&&Array.isArray(D.produccion)) D.produccion.unshift({fecha:deHoy(),pieza:nombre,estado:'publicada',detalle:'',enlace:liga});
    const b=leer(BORRADOR,{}); delete b[nombre]; guardar(BORRADOR,b);
    cerrarCapa('publicar-'+normSlug(nombre));
    if(typeof LINEA_PIEZAS!=='undefined') _lineaHoyT=0;
    await pintar(); recordar();
    if(document.body.dataset.vista==='prod'&&typeof pintarProduccion==='function') pintarProduccion();
    hoja(`<h3>Anotada como publicada</h3><p><b>${esc(nombre)}</b> sale de tu montón.${r.estado==='recibido'?'':' Se guardó en este aparato y sube sola en cuanto haya conexión.'}</p>
      <p>Su paquete se guarda en «_PUBLICADAS» y su historia queda en la Sala.</p><button class="listo" type="button" id="salOk">Entendido</button>`,'publicada-ok');
    const ok=document.getElementById('salOk'); if(ok) ok.onclick=()=>cerrarCapa('publicada-ok');
  };
}
/* lo anotado aquí deja de recordarse cuando el expediente ya lo trae como publicado */
function conciliar(){
  const m=leer(LLAVE,{}); let cambio=false;
  for(const n of Object.keys(m)){ const e=EXP[n]; if(e&&e.estado==='publicada'){ delete m[n]; cambio=true } }
  if(cambio) guardar(LLAVE,m);
}
/* ── lo último que este aparato vio: se pinta al abrir, mientras contesta la hoja ───────── */
async function recordar(){
  if(!vivo) return;
  try{ localStorage.setItem(RESUMEN,JSON.stringify({listas:pendientes().length,cuando:Date.now()}));
    const owner=await dueno(); if(!owner) return;
    const raw=JSON.stringify({schema:1,owner,savedAt:Date.now(),exp:paraGuardar(conPaquete()),cambios:CAMBIOS});
    if(raw.length<=TOPE_GUARDADA) localStorage.setItem(GUARDADA,raw) }catch(e){}
}
async function abrirGuardada(){
  if(vivo||GUARD) return;
  try{ const raw=localStorage.getItem(GUARDADA); if(!raw) return;
    const owner=await dueno(), x=JSON.parse(raw), ahora=Date.now();
    if(!owner||raw.length>TOPE_GUARDADA||!x||x.schema!==1||x.owner!==owner||!(ahora-x.savedAt<VIGENCIA)||x.savedAt>ahora+60000||!x.exp||typeof x.exp!=='object'){ olvidar(); return }
    if(vivo) return;   // la hoja contestó mientras se comprobaba de quién es la copia
    GUARD=x.exp; CAMBIOS=cargarCambios(x.cambios); pintar();
  }catch(e){ olvidar() }
}
function olvidar(){ GUARD=null; if(!vivo) CAMBIOS={}; try{ localStorage.removeItem(GUARDADA); localStorage.removeItem(RESUMEN) }catch(e){} }
/* la hoja contestó: `salida` trae las llaves `salida:` (el plan) y `cambio:` (las órdenes de cambio) */
function llegaron(salida){
  vivo=true; fallo=false; GUARD=null;
  CAMBIOS=cargarCambios(Object.fromEntries(Object.entries(salida||{}).filter(([k])=>k.startsWith(CAMBIO_LLAVE)).map(([k,v])=>[k.slice(CAMBIO_LLAVE.length),v])));
  const remoto=salida&&salida[PLAN_LLAVE]?planLimpio(salida[PLAN_LLAVE]):null, loc=leer(PLAN_LOCAL,null), mio=loc&&loc.plan?planLimpio(loc.plan):null;
  if(mio&&loc.pendiente&&(!remoto||mio.cuando>remoto.cuando)){ PLAN=mio; if(DECIDE()){ clearTimeout(_tPlan); _tPlan=setTimeout(subirPlan,0) } }
  else if(remoto){ PLAN=remoto; guardar(PLAN_LOCAL,{plan:remoto,pendiente:false}) }
  else if(mio) PLAN=mio;
  pintar().then(recordar);
}
function falla(){ if(!vivo){ fallo=true; pintar() } }
async function actualizar(){
  if(_releyendo||typeof releerExpedientes!=='function') return; _releyendo=true; fallo=false; avisar('Preguntando al Sheet…'); pintar();
  try{ const ok=await releerExpedientes(); if(!ok){ if(!vivo) fallo=true; avisar('El Sheet no contestó. Sigues viendo lo último guardado.') } else avisar('') }
  finally{ _releyendo=false; pintar() }
}
root.SalaSalida=Object.assign({pintar,abrir,publicadaAqui,paqueteDe,pendientes,conciliar,hay,llegaron,falla,abrirGuardada,olvidar,actualizar,plan:()=>PLAN,
  puedePedirCambio,pedirCambio,quitarCambio,quitarCambioDeTira,cambioDe,cambioDePieza,enCambio},puro);
if(typeof arrancarSalida==='function') arrancarSalida();   // si la Sala ya arrancó antes de que cargara este archivo
})(globalThis);
