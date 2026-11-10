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
/* qué días de la semana sale algo según cuántas por semana (0 = domingo) */
const DIAS={1:[3],2:[2,4],3:[1,3,5],4:[1,2,4,5],5:[1,2,3,4,5],6:[1,2,3,4,5,6],7:[0,1,2,3,4,5,6]};

/* ── puro (sin pantalla): se prueba en Node ─────────────────────────────────────────────── */
function paquete(e){ return e&&typeof e==='object'&&e.paquete&&typeof e.paquete==='object'&&Array.isArray(e.paquete.imagenes)&&e.paquete.imagenes.length?e.paquete:null }
/* lo que venga de la hoja o del aparato, en una forma en la que se puede confiar */
function planLimpio(p){
  p=p&&typeof p==='object'&&!Array.isArray(p)?p:{};
  const orden=Array.isArray(p.orden)?[...new Set(p.orden.filter(x=>typeof x==='string'&&x.trim()).map(x=>x.trim().slice(0,160)))].slice(0,500):[];
  const ps=Math.round(Number(p.por_semana));
  return {v:1, orden, por_semana:ps>=1&&ps<=7?ps:3, arranque:/^\d{4}-\d{2}-\d{2}$/.test(String(p.arranque||''))?String(p.arranque):'',
    cuando:typeof p.cuando==='string'?p.cuando.slice(0,40):'', por:typeof p.por==='string'?p.por.slice(0,40):''};
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
/* lo mínimo de cada pieza lista para volver a pintarla al abrir, sin nada que parezca una llave */
function paraGuardar(lista){
  const secreto=/^(?:clave(?:_.*)?|token|access_token|refresh_token|authorization|password)$/i, out={};
  for(const x of lista){ const p=x.p, c=x.e.copy||{};
    out[x.nombre]={estado:x.e.estado||'lista', portada:x.e.portada||'',
      paquete:{orden:p.orden, formato:p.formato, nota_formato:p.nota_formato, url:p.url, sello:p.sello, imagenes:p.imagenes.map(i=>({src:i.src,dice:i.dice}))},
      copy:{texto:c.texto, instagram:c.instagram, facebook:c.facebook, comentario:c.comentario, revision:c.revision}} }
  return JSON.parse(JSON.stringify(out,(k,v)=>secreto.test(k)?undefined:v));
}
const puro={paquete,planLimpio,listas,mover,fechasDeSalida,alcance,partes,ligaValida,estado,cuantas,paraGuardar,PLAN_LLAVE};
if(typeof module==='object'&&module.exports){ module.exports=puro; return }

/* ── pantalla ───────────────────────────────────────────────────────────────────────────── */
const leer=(k,d)=>{ try{ const v=JSON.parse(localStorage.getItem(k)||'null'); return v&&typeof v==='object'?v:d }catch(e){ return d } };
const guardar=(k,v)=>{ try{ localStorage.setItem(k,JSON.stringify(v)); return true }catch(e){ return false } };
/* vivo: ya contestó la hoja en esta visita · GUARD: lo último que este aparato vio de ella */
let vivo=false, fallo=false, GUARD=null, PLAN=planLimpio((leer(PLAN_LOCAL,{})||{}).plan), ORDEN=null, _tPlan=0, _aviso='', _tAviso=0, _releyendo=false;
function publicadaAqui(n){ const m=leer(LLAVE,{}); return !!(m[n]&&m[n].fecha) }
/* de dónde se lee: la hoja si ya contestó; si no, lo guardado en el aparato; sin ninguna de las dos, lo que haya */
function exps(){ return !vivo&&GUARD?GUARD:(typeof EXP!=='undefined'?EXP:{}) }
function expDe(n){ return exps()[n]||null }
function paqueteDe(n){ return paquete(expDe(n)) }
function deHoy(){ return (typeof fecha!=='undefined'&&fecha)||new Date(Date.now()-7*36e5).toISOString().slice(0,10) }
function hoyHmo(){ return new Date(Date.now()-7*36e5).toISOString().slice(0,10) }
const miniatura=src=>typeof ligera==='function'?ligera(src):src;
function pendientes(){ return listas(exps(),n=>esPublicada(n),PLAN) }
function hay(){ try{ return ENTRADO()&&pendientes().length>0 }catch(e){ return false } }
function puedeOrdenar(){ return DECIDE()&&(vivo||!!GUARD) }
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
    <b>${esc(x.nombre)}</b><small>${esc(x.p.formato||'Publicación')} · ${cuantas(k,'imagen','imágenes')}</small><small class="sal-cuando">${esc(cuando(i,fechas))}</small>`;
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
function controles(n){
  if(!puedeOrdenar()||!n) return '';
  if(ORDEN) return `<div class="sal-plan"><span class="sal-ayuda">Mueve cada una con las flechas o elige su lugar.</span><button type="button" class="sal-b fuerte" data-orden-ok>Guardar el orden</button><button type="button" class="sal-b" data-orden-no>Cancelar</button></div>`;
  return `<div class="sal-plan" role="group" aria-label="Plan de salida">
    <span class="sal-ritmo"><button type="button" data-ritmo="-1" aria-label="Menos por semana" ${PLAN.por_semana>1?'':'disabled'}>−</button><span><b>${PLAN.por_semana}</b> por semana</span><button type="button" data-ritmo="1" aria-label="Más por semana" ${PLAN.por_semana<7?'':'disabled'}>+</button></span>
    <label class="sal-arr">Arranca <input type="date" id="salArranque" value="${esc(PLAN.arranque)}" aria-label="Día en que arranca la salida"></label>
    ${n>1?'<button type="button" class="sal-b" data-ordenar>Cambiar el orden</button>':''}</div>`;
}
let _hubo=null;
async function pintar(){
  const hoy=$('#salidaHoy'); if(!hoy) return;
  let html='';
  if(ENTRADO()){
    if(vivo) conciliar();
    const sabe=vivo||!!GUARD, l=sabe?pendientes():[], n=l.length, {espera,guardadas}=await sinPaquete();
    if(ORDEN&&!n) ORDEN=null;
    const vista=ORDEN?ORDEN.map(nombre=>l.find(x=>x.nombre===nombre)).filter(Boolean):l;
    const fechas=fechasDeSalida(n,PLAN.por_semana,desde());
    if(!sabe&&fallo) html=`<section class="sal sal-aviso" aria-label="Listas para publicar"><header><span class="bt-eyebrow">TU MONTÓN</span><h2>No pude leer lo que está listo</h2><p>El Sheet no contestó. Tus publicaciones siguen en Drive y en la hoja; sólo falta volver a preguntar.</p></header><div class="sal-plan"><button type="button" class="sal-b fuerte" data-releer>Reintentar</button></div></section>`;
    else if(sabe&&(n||espera||guardadas.length)) html=`<section class="sal${ORDEN?' en-orden':''}" aria-label="Listas para publicar">
    <div class="sal-cab"><header><span class="bt-eyebrow">TU MONTÓN</span>
      <h2>${n?cuantas(n,'lista para lanzar','listas para lanzar'):'Todavía no hay nada listo para lanzar'}</h2>
      <p>${n?(fechas[0]===hoyHmo()?`Hoy toca <b>«${esc(vista[0].nombre)}»</b>. `:'')+resumen(n,fechas)+' Nada sale solo: tú das el clic de publicar.':'En cuanto una pieza tenga sus imágenes aprobadas y su texto, aparece aquí.'}</p>
      ${!vivo?`<p class="sal-nota">${fallo?'El Sheet no contestó: ves lo último que este aparato guardó.':'Lo último que este aparato guardó; confirmando con el Sheet…'}${fallo?' <button type="button" class="sal-mini" data-releer>Reintentar</button>':''}</p>`:''}</header>
      ${controles(n)}</div>
    ${n?`<div class="sal-rejilla">${vista.map((x,i)=>tarjeta(x,i,fechas,n)).join('')}</div>`:''}
    <p class="sal-estado" role="status" aria-live="polite">${esc(_aviso)}</p>
    ${espera?`<p class="sal-pie"><b>${cuantas(espera,'pieza más','piezas más')}</b> ya ${espera===1?'tiene':'tienen'} sus imágenes aprobadas y ${espera===1?'espera':'esperan'} su texto. Es el paso del consejo; cuando lo escriba, ${espera===1?'aparece':'aparecen'} aquí.</p>`:''}
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
  const n=p.imagenes.length, puede=DECIDE()&&!esPublicada(nombre);
  const l=pendientes(), i=l.findIndex(x=>x.nombre===nombre), fechas=fechasDeSalida(l.length,PLAN.por_semana,desde());
  const v=hoja(`<div class="sal-hoja">
    <h3>${esc(nombre)}</h3>
    <p class="sal-sub">${esc(p.formato||'Publicación')} · ${cuantas(n,'imagen','imágenes')}${p.nota_formato?' · '+esc(p.nota_formato):''}${i>=0?` · sale en el lugar ${i+1} de ${l.length} (${esc(cuando(i,fechas))})`:''}</p>
    <div class="sal-tira" role="list">${p.imagenes.map((im,k)=>`<button type="button" role="listitem" class="sal-img" data-zoom="${esc(im.src)}" aria-label="Imagen ${k+1} de ${n}: ${esc(im.dice||'')}. Ampliar">${miniatura(im.src)?`<img src="${esc(miniatura(im.src))}" alt="" loading="lazy">`:''}<i>${k+1}</i></button>`).join('')}</div>
    ${c.revision.length?`<div class="sal-ojo"><b>Antes de publicar, mira esto</b><ul>${c.revision.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:''}
    <div class="sal-paso"><h4><i>1</i>Las imágenes</h4>
      <p>Están en Drive, numeradas en el orden en que van.</p>
      ${/^https:\/\/drive\.google\.com\//.test(p.url||'')?`<a class="secund sal-liga" href="${esc(p.url)}" target="_blank" rel="noopener">Abrir la carpeta en Drive ↗</a>`:''}</div>
    <div class="sal-paso"><h4><i>2</i>El texto</h4>
      <p>Cámbialo aquí si quieres; se copia tal como lo dejes.</p>
      <textarea id="salTexto" rows="9" spellcheck="true" aria-label="Texto de la publicación">${esc(mio||c.texto)}</textarea>
      ${mio&&mio!==c.texto?`<button type="button" class="sal-mini" id="salOriginal">Volver al texto del consejo</button>`:''}
      <div class="sal-botones"><button type="button" class="secund" id="salIg">Copiar para Instagram</button><button type="button" class="secund" id="salFb">Copiar para Facebook</button></div></div>
    <div class="sal-paso"><h4><i>3</i>La liga (primer comentario en Instagram)</h4>
      <p class="sal-url">${esc(c.comentario)}</p>
      <button type="button" class="secund" id="salCom">Copiar la liga</button></div>
    ${puede?`<div class="sal-paso fin"><h4><i>4</i>Cuando ya esté publicada</h4>
      <label class="sal-lab" for="salPost">Liga de la publicación (si la tienes a la mano)</label>
      <input id="salPost" type="url" inputmode="url" autocomplete="off" placeholder="https://www.instagram.com/p/…">
      <button type="button" class="listo" id="salYa">Ya la publiqué</button>
      <p class="aviso" id="salAviso" role="status" aria-live="polite"></p></div>`
      :`<p class="nota-pie">${esPublicada(nombre)?'Esta pieza ya está anotada como publicada.':'Publicar y anotar la publicación corresponde a los editores.'}</p>`}
  </div>`,'publicar-'+normSlug(nombre));
  const q=s=>v.querySelector(s), txt=q('#salTexto');
  v.querySelectorAll('[data-zoom]').forEach(b=>b.onclick=()=>{ if(typeof abrirZoom==='function') abrirZoom(b.dataset.zoom) });
  txt.oninput=()=>{ const b=leer(BORRADOR,{}); if(txt.value===c.texto) delete b[nombre]; else b[nombre]={sello,texto:txt.value}; guardar(BORRADOR,b) };
  const orig=q('#salOriginal'); if(orig) orig.onclick=()=>{ txt.value=c.texto; txt.oninput(); orig.remove() };
  q('#salIg').onclick=ev=>copiar(txt.value.trim()+c.ig,ev.currentTarget);
  q('#salFb').onclick=ev=>copiar(txt.value.trim()+c.fb,ev.currentTarget);
  q('#salCom').onclick=ev=>copiar(c.comentario,ev.currentTarget);
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
  try{ const l=pendientes(); localStorage.setItem(RESUMEN,JSON.stringify({listas:l.length,cuando:Date.now()}));
    const owner=await dueno(); if(!owner) return;
    const raw=JSON.stringify({schema:1,owner,savedAt:Date.now(),exp:paraGuardar(l)});
    if(raw.length<=TOPE_GUARDADA) localStorage.setItem(GUARDADA,raw) }catch(e){}
}
async function abrirGuardada(){
  if(vivo||GUARD) return;
  try{ const raw=localStorage.getItem(GUARDADA); if(!raw) return;
    const owner=await dueno(), x=JSON.parse(raw), ahora=Date.now();
    if(!owner||raw.length>TOPE_GUARDADA||!x||x.schema!==1||x.owner!==owner||!(ahora-x.savedAt<VIGENCIA)||x.savedAt>ahora+60000||!x.exp||typeof x.exp!=='object'){ olvidar(); return }
    if(vivo) return;   // la hoja contestó mientras se comprobaba de quién es la copia
    GUARD=x.exp; pintar();
  }catch(e){ olvidar() }
}
function olvidar(){ GUARD=null; try{ localStorage.removeItem(GUARDADA); localStorage.removeItem(RESUMEN) }catch(e){} }
/* la hoja contestó: `salida` trae las llaves `salida:` (hoy, el plan) */
function llegaron(salida){
  vivo=true; fallo=false; GUARD=null;
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
root.SalaSalida=Object.assign({pintar,abrir,publicadaAqui,paqueteDe,pendientes,conciliar,hay,llegaron,falla,abrirGuardada,olvidar,actualizar,plan:()=>PLAN},puro);
if(typeof arrancarSalida==='function') arrancarSalida();   // si la Sala ya arrancó antes de que cargara este archivo
})(globalThis);
